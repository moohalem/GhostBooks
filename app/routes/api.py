#!/usr/bin/env python3
"""
API routes for Calibre Library Monitor
All API endpoints for the SPA
"""

import os

from flask import Blueprint, current_app, jsonify, request

from app.services.database import (
    find_calibre_metadata_db,
    get_author_books,
    get_authors,
    get_database_stats,
    get_metadata_db_info,
    get_missing_books,
    search_authors,
    update_missing_books,
    verify_calibre_database,
)
from app.services.irc import get_search_status, start_irc_search
from app.services.openlibrary import compare_author_books

api_bp = Blueprint("api", __name__)


@api_bp.route("/authors")
def get_all_authors():
    """API endpoint to get all authors with stats."""
    try:
        authors = get_authors(current_app.config["DB_PATH"])
        authors_with_stats = []

        for author in authors:
            books = get_author_books(current_app.config["DB_PATH"], author)
            missing_count = sum(1 for book in books if book["missing"])
            authors_with_stats.append(
                {
                    "name": author,
                    "total_books": len(books),
                    "missing_books": missing_count,
                }
            )

        return jsonify(authors_with_stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/author/<author_name>")
def get_author_detail(author_name):
    """API endpoint to get books for a specific author."""
    try:
        books = get_author_books(current_app.config["DB_PATH"], author_name)
        missing_books = [book for book in books if book["missing"]]

        return jsonify(
            {
                "author": author_name,
                "books": books,
                "missing_books": missing_books,
                "total_books": len(books),
                "missing_count": len(missing_books),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/missing_books")
def get_all_missing_books():
    """API endpoint to get all missing books grouped by author."""
    try:
        missing_books = get_missing_books(current_app.config["DB_PATH"])

        # Group by author
        authors_missing = {}
        for book in missing_books:
            author = book["author"]
            if author not in authors_missing:
                authors_missing[author] = []
            authors_missing[author].append(book)

        return jsonify(authors_missing)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/stats")
def get_stats():
    """API endpoint for dashboard statistics."""
    try:
        db_path = current_app.config["DB_PATH"]
        # Check if database file exists and has data
        exists = os.path.exists(db_path) and os.path.getsize(db_path) > 0

        if exists:
            stats = get_database_stats(db_path)
            # Get database file modification time
            db_mtime = os.path.getmtime(db_path)
            from datetime import datetime

            db_modified = datetime.fromtimestamp(db_mtime).strftime("%Y-%m-%d %H:%M:%S")
            return jsonify(
                {"exists": True, "stats": stats, "last_modified": db_modified}
            )
        else:
            return jsonify({"exists": False})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/search_authors")
def search_authors_endpoint():
    """API endpoint to search for authors by name pattern."""
    try:
        query = request.args.get("q", "").strip()
        if not query:
            return jsonify({"error": "Query parameter required"}), 400

        authors = search_authors(current_app.config["DB_PATH"], query)
        return jsonify(authors)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/author/<author_name>/compare")
def compare_author(author_name):
    """API endpoint to compare author's books with OpenLibrary."""
    try:
        # Get local books
        local_books = get_author_books(current_app.config["DB_PATH"], author_name)
        local_titles = [book["title"] for book in local_books]

        # Compare with OpenLibrary
        result = compare_author_books(author_name, local_titles, verbose=False)

        if result["success"]:
            # Update missing books in database
            update_missing_books(
                current_app.config["DB_PATH"], author_name, result["missing_books"]
            )

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/search_author_irc", methods=["POST"])
def search_author_irc():
    """API endpoint to start IRC search for an author."""
    try:
        data = request.get_json()
        author = data.get("author")

        if not author:
            return jsonify({"error": "Author name required"}), 400

        search_id = start_irc_search(author)
        return jsonify(
            {"search_id": search_id, "message": f"IRC search started for {author}"}
        ), 202
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/search_status/<search_id>")
def get_search_status_endpoint(search_id):
    """API endpoint to get IRC search status."""
    try:
        status = get_search_status(search_id)
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/initialize_database", methods=["POST"])
def initialize_database_endpoint():
    """API endpoint to initialize database from Calibre metadata."""
    try:
        from app.services.database import find_calibre_metadata_db, initialize_database

        # Get request data
        data = request.get_json() or {}
        calibre_db_path = data.get("calibre_db_path")
        force_reinit = data.get("force_reinit", False)

        # If no path provided, try to auto-detect
        if not calibre_db_path:
            calibre_db_path = find_calibre_metadata_db()
            if not calibre_db_path:
                return jsonify(
                    {
                        "success": False,
                        "error": "No Calibre database path provided and auto-detection failed",
                    }
                ), 400

        result = initialize_database(
            current_app.config["DB_PATH"], calibre_db_path, force_reinit
        )

        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/database_info")
def get_database_info():
    """API endpoint to get detailed database information."""
    try:
        if not os.path.exists(current_app.config["DB_PATH"]):
            return jsonify(
                {
                    "exists": False,
                    "message": "Database not found. Please initialize first.",
                }
            )

        stats = get_database_stats(current_app.config["DB_PATH"])
        missing_books = get_missing_books(current_app.config["DB_PATH"])

        # Get database file modification time
        db_mtime = os.path.getmtime(current_app.config["DB_PATH"])
        from datetime import datetime

        db_modified = datetime.fromtimestamp(db_mtime).strftime("%Y-%m-%d %H:%M:%S")

        # Group missing books by author
        missing_by_author = {}
        for book in missing_books:
            author = book["author"]
            if author not in missing_by_author:
                missing_by_author[author] = []
            missing_by_author[author].append(book["title"])

        return jsonify(
            {
                "exists": True,
                "stats": stats,
                "missing_authors": len(missing_by_author),
                "missing_by_author": missing_by_author,
                "last_modified": db_modified,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/metadata/locate")
def locate_metadata_db():
    """API endpoint to locate Calibre metadata.db file."""
    try:
        found_path = find_calibre_metadata_db()
        if found_path:
            # Get information about the found database
            db_info = get_metadata_db_info(found_path)
            return jsonify(
                {
                    "success": True,
                    "found": True,
                    "path": found_path,
                    "info": db_info,
                }
            )
        else:
            return jsonify(
                {
                    "success": True,
                    "found": False,
                    "message": "Calibre metadata.db not found in common locations",
                }
            )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/metadata/verify", methods=["POST"])
def verify_metadata_db():
    """API endpoint to verify if a given path is a valid Calibre metadata.db."""
    try:
        data = request.get_json()
        if not data or "path" not in data:
            return jsonify({"error": "Path is required"}), 400

        db_path = data["path"]

        if not os.path.exists(db_path):
            return jsonify(
                {"success": True, "valid": False, "message": "File does not exist"}
            )

        is_valid = verify_calibre_database(db_path)

        if is_valid:
            db_info = get_metadata_db_info(db_path)
            return jsonify({"success": True, "valid": True, "info": db_info})
        else:
            return jsonify(
                {
                    "success": True,
                    "valid": False,
                    "message": "Not a valid Calibre database",
                }
            )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/metadata/info")
def get_current_metadata_info():
    """API endpoint to get information about the currently configured metadata.db."""
    try:
        calibre_db_path = current_app.config.get("CALIBRE_DB_PATH", "metadata.db")

        if not os.path.exists(calibre_db_path):
            return jsonify(
                {
                    "success": True,
                    "exists": False,
                    "configured_path": calibre_db_path,
                    "message": "Configured metadata.db not found",
                }
            )

        db_info = get_metadata_db_info(calibre_db_path)
        return jsonify(
            {
                "success": True,
                "exists": True,
                "configured_path": calibre_db_path,
                "info": db_info,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
