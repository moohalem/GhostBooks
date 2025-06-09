#!/usr/bin/env python3
"""
API routes for Calibre Library Monitor
All API endpoints for the SPA
"""

import os

from flask import Blueprint, current_app, jsonify, request

from app.services.database import (
    clear_author_olid_cache,
    ensure_author_olid_table,
    find_calibre_metadata_db,
    get_author_books,
    get_author_olid_stats,
    get_authors_with_olid,
    get_authors_without_olid,
    get_database_connection,
    get_database_stats,
    get_metadata_db_info,
    get_missing_books,
    get_recently_processed_authors,
    migrate_database_schema,
    search_authors,
    sync_with_calibre_metadata,
    update_author_processing_time,
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
        # Get pagination parameters
        page = int(request.args.get("page", 1))
        per_page = int(
            request.args.get("per_page", 100)
        )  # Default to 100 authors per page
        search = request.args.get("search", "").strip()

        # Get authors from database with optional search filter
        db_path = current_app.config["DB_PATH"]
        conn = get_database_connection(db_path)
        cursor = conn.cursor()

        # Build query with search filter
        base_query = """
            SELECT DISTINCT author, 
                   COUNT(*) as total_books,
                   SUM(CASE WHEN missing = 1 THEN 1 ELSE 0 END) as missing_books
            FROM author_book 
        """

        if search:
            base_query += "WHERE author LIKE ? "
            params = (f"%{search}%",)
        else:
            params = ()

        base_query += "GROUP BY author ORDER BY author "

        # Get total count for pagination
        count_query = f"SELECT COUNT(*) FROM ({base_query}) as subquery"
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()[0]

        # Add pagination
        offset = (page - 1) * per_page
        paginated_query = base_query + f"LIMIT {per_page} OFFSET {offset}"

        cursor.execute(paginated_query, params)
        rows = cursor.fetchall()

        authors_with_stats = []
        for row in rows:
            authors_with_stats.append(
                {
                    "author": row[0],
                    "total_books": row[1],
                    "missing_books": row[2] or 0,
                }
            )

        conn.close()

        return jsonify(
            {
                "authors": authors_with_stats,
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": total_count,
                    "pages": (total_count + per_page - 1) // per_page,
                },
            }
        )
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

        # Compare with OpenLibrary (with OLID caching)
        result = compare_author_books(
            author_name,
            local_titles,
            verbose=False,
            db_path=current_app.config["DB_PATH"],
        )

        if result["success"]:
            # Update missing books in database
            update_missing_books(
                current_app.config["DB_PATH"], author_name, result["missing_books"]
            )
            # Record that this author was processed
            update_author_processing_time(current_app.config["DB_PATH"], author_name)

            # Create enhanced book data with status information
            missing_titles_set = {
                title.lower().strip() for title in result["missing_books"]
            }
            enhanced_books = []

            for book in local_books:
                book_title_lower = book["title"].lower().strip()
                if book_title_lower in missing_titles_set:
                    # This book is missing from local library but exists in OpenLibrary
                    status = "missing_local"
                    status_info = "Missing from local library"
                elif book["missing"]:
                    # This book was already marked as missing
                    status = "missing_local"
                    status_info = "Missing from local library"
                else:
                    # This book exists in both local and OpenLibrary
                    status = "exists_both"
                    status_info = "Available in library"

                enhanced_books.append(
                    {
                        "id": book.get("id"),
                        "title": book["title"],
                        "missing": book["missing"],
                        "status": status,
                        "status_info": status_info,
                    }
                )

            # Add missing books that are in OpenLibrary but not in local library
            for missing_title in result["missing_books"]:
                # Check if this book is already in our local books list
                if not any(
                    book["title"].lower().strip() == missing_title.lower().strip()
                    for book in local_books
                ):
                    enhanced_books.append(
                        {
                            "id": None,
                            "title": missing_title,
                            "missing": True,
                            "status": "missing_local",
                            "status_info": "Missing from local library",
                        }
                    )

            return jsonify(
                {
                    "success": True,
                    "author": author_name,
                    "books": enhanced_books,
                    "local_count": result["local_count"],
                    "openlibrary_count": result["openlibrary_count"],
                    "missing_count": result["missing_count"],
                    "missing_books": result["missing_books"],
                }
            )
        else:
            # If comparison failed, still return local books with basic status
            enhanced_books = []
            for book in local_books:
                status = "missing_api" if book["missing"] else "exists_both"
                status_info = (
                    "Could not verify with OpenLibrary"
                    if book["missing"]
                    else "Available in library"
                )

                enhanced_books.append(
                    {
                        "id": book.get("id"),
                        "title": book["title"],
                        "missing": book["missing"],
                        "status": status,
                        "status_info": status_info,
                    }
                )

            return jsonify(
                {
                    "success": False,
                    "author": author_name,
                    "books": enhanced_books,
                    "message": result.get("message", "Comparison failed"),
                    "local_count": len(local_books),
                    "openlibrary_count": 0,
                    "missing_count": len([b for b in local_books if b["missing"]]),
                    "missing_books": [],
                }
            )

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

        # Ensure OLID table is created and migrate schema after database initialization
        if result["success"]:
            ensure_author_olid_table(current_app.config["DB_PATH"])
            migration_result = migrate_database_schema(current_app.config["DB_PATH"])
            if migration_result["migrations_applied"]:
                result["migrations"] = migration_result["migrations_applied"]

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


@api_bp.route("/recently_processed_authors")
def get_recently_processed_authors_endpoint():
    """API endpoint for recently processed authors."""
    try:
        db_path = current_app.config["DB_PATH"]
        # Check if database file exists and has data
        exists = os.path.exists(db_path) and os.path.getsize(db_path) > 0

        if exists:
            authors = get_recently_processed_authors(db_path, limit=10)
            return jsonify(authors)
        else:
            return jsonify([])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/cache/olid/stats")
def get_olid_cache_stats():
    """API endpoint to get OLID cache statistics."""
    try:
        db_path = current_app.config["DB_PATH"]

        # Ensure the OLID table exists
        ensure_author_olid_table(db_path)

        stats = get_author_olid_stats(db_path)
        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/cache/olid/clear", methods=["POST"])
def clear_olid_cache():
    """API endpoint to clear the OLID cache."""
    try:
        db_path = current_app.config["DB_PATH"]

        # Clear the cache
        cleared_count = clear_author_olid_cache(db_path)

        return jsonify(
            {
                "success": True,
                "message": f"Cleared {cleared_count} cached OLID entries",
                "cleared_count": cleared_count,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/cache/olid/status")
def get_olid_cache_status():
    """API endpoint to get OLID cache status and recent entries."""
    try:
        db_path = current_app.config["DB_PATH"]

        # Ensure the OLID table exists
        ensure_author_olid_table(db_path)

        # Get basic stats
        stats = get_author_olid_stats(db_path)

        # Get recent cache entries
        conn = get_database_connection(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT author, olid, last_updated, created_at
            FROM author_olid
            ORDER BY last_updated DESC
            LIMIT 20
        """)

        recent_entries = []
        for row in cursor.fetchall():
            recent_entries.append(
                {
                    "author_name": row[0],
                    "olid": row[1],
                    "last_updated": row[2],
                    "created_at": row[3],
                }
            )

        conn.close()

        return jsonify(
            {"success": True, "stats": stats, "recent_entries": recent_entries}
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/authors/with-olid")
def get_authors_with_olid_endpoint():
    """API endpoint to get authors that have OLID stored."""
    try:
        db_path = current_app.config["DB_PATH"]
        authors = get_authors_with_olid(db_path)
        return jsonify({"success": True, "authors": authors, "count": len(authors)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/authors/without-olid")
def get_authors_without_olid_endpoint():
    """API endpoint to get authors that don't have OLID stored."""
    try:
        db_path = current_app.config["DB_PATH"]
        authors = get_authors_without_olid(db_path)
        return jsonify({"success": True, "authors": authors, "count": len(authors)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/database/migrate", methods=["POST"])
def migrate_database_endpoint():
    """API endpoint to migrate database schema."""
    try:
        db_path = current_app.config["DB_PATH"]
        result = migrate_database_schema(db_path)

        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/database/sync", methods=["POST"])
def sync_database_endpoint():
    """API endpoint to synchronize the database with latest Calibre metadata."""
    try:
        db_path = current_app.config["DB_PATH"]
        calibre_db_path = current_app.config.get("CALIBRE_DB_PATH")

        if not calibre_db_path:
            return jsonify(
                {"success": False, "error": "Calibre database path not configured"}
            ), 400

        # Check if application database exists
        if not os.path.exists(db_path):
            return jsonify(
                {
                    "success": False,
                    "error": "Application database not initialized. Please initialize first.",
                }
            ), 400

        result = sync_with_calibre_metadata(db_path, calibre_db_path)

        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
