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
    get_missing_book_stats,
    get_missing_books,
    get_recently_processed_authors,
    migrate_database_schema,
    search_authors,
    sync_with_calibre_metadata,
    update_author_processing_time,
    update_missing_books,
    verify_calibre_database,
)
from app.services.irc import (
    close_session,
    create_irc_session,
    download_epub_only,
    get_session_status,
    list_active_sessions,
    search_and_download,
)
from app.services.openlibrary import compare_author_books
from config.config_manager import config_manager

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
        from app.services.database import get_all_missing_books as get_db_missing_books

        db_path = current_app.config["DB_PATH"]

        # Get data from both sources
        legacy_missing_books = get_missing_books(db_path)  # From author_book table
        new_missing_books = get_db_missing_books(db_path)  # From missing_book table

        # Group legacy books by author
        authors_missing = {}
        for book in legacy_missing_books:
            author = book["author"]
            if author not in authors_missing:
                authors_missing[author] = []
            authors_missing[author].append(
                {"title": book["title"], "source": "legacy", "discovered_at": None}
            )

        # Add new database books (avoiding duplicates)
        for book in new_missing_books:
            author = book["author"]
            if author not in authors_missing:
                authors_missing[author] = []

            # Check for duplicates
            existing_titles = {b["title"].lower() for b in authors_missing[author]}
            if book["title"].lower() not in existing_titles:
                authors_missing[author].append(
                    {
                        "title": book["title"],
                        "source": book["source"],
                        "discovered_at": book["discovered_at"],
                    }
                )

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
            # Get legacy stats
            stats = get_database_stats(db_path)

            # Get enhanced missing books stats from new database
            try:
                missing_stats = get_missing_book_stats(db_path)
                # Merge stats with priority to new database if available
                stats.update(
                    {
                        "total_missing": missing_stats["total_missing"]
                        if missing_stats["total_missing"] > 0
                        else stats.get("missing_books", 0),
                        "authors_with_missing": missing_stats["authors_with_missing"]
                        if missing_stats["authors_with_missing"] > 0
                        else stats.get("authors_with_missing", 0),
                        "missing_book_stats": missing_stats,  # Include detailed stats
                    }
                )
            except Exception as e:
                # Fallback to legacy stats if new database has issues
                print(f"Warning: Could not get enhanced missing book stats: {e}")

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


@api_bp.route("/search_authors/autocomplete")
def search_authors_autocomplete():
    """API endpoint for autocomplete search suggestions with stats."""
    try:
        query = request.args.get("q", "").strip()
        limit = int(request.args.get("limit", 10))

        if not query:
            # Return popular authors when no query
            from app.services.database import get_popular_authors

            authors = get_popular_authors(current_app.config["DB_PATH"], limit)
            return jsonify(
                {
                    "suggestions": authors,
                    "query": "",
                    "type": "popular",
                    "message": "Popular authors",
                }
            )

        if len(query) < 2:
            return jsonify({"suggestions": [], "query": query, "type": "too_short"})

        from app.services.database import search_authors_with_stats

        authors = search_authors_with_stats(current_app.config["DB_PATH"], query, limit)

        return jsonify(
            {
                "suggestions": authors,
                "query": query,
                "type": "search_results",
                "count": len(authors),
                "message": f"Found {len(authors)} author{'s' if len(authors) != 1 else ''}",
            }
        )
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

        # Check if configuration is persistent
        has_persistent_config = config_manager.has_calibre_db_path()
        persistent_path = config_manager.get_calibre_db_path()

        if not os.path.exists(calibre_db_path):
            return jsonify(
                {
                    "success": True,
                    "exists": False,
                    "configured_path": calibre_db_path,
                    "has_persistent_config": has_persistent_config,
                    "persistent_path": persistent_path,
                    "message": "Configured metadata.db not found",
                }
            )

        db_info = get_metadata_db_info(calibre_db_path)
        return jsonify(
            {
                "success": True,
                "exists": True,
                "configured_path": calibre_db_path,
                "has_persistent_config": has_persistent_config,
                "persistent_path": persistent_path,
                "info": db_info,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/metadata/update_path", methods=["POST"])
def update_metadata_path():
    """API endpoint to update the metadata database path configuration."""
    try:
        data = request.get_json()
        if not data or "path" not in data:
            return jsonify({"error": "Path is required"}), 400

        new_path = data["path"]

        # Verify the path exists and is a valid Calibre database
        if not os.path.exists(new_path):
            return jsonify({"success": False, "error": "File does not exist"}), 400

        if not verify_calibre_database(new_path):
            return jsonify(
                {"success": False, "error": "Not a valid Calibre database"}
            ), 400

        # Update the application configuration
        current_app.config["CALIBRE_DB_PATH"] = new_path

        # Save the configuration persistently
        if not config_manager.set_calibre_db_path(new_path):
            return jsonify(
                {
                    "success": False,
                    "error": "Failed to save configuration persistently",
                }
            ), 500

        # Get database info for confirmation
        db_info = get_metadata_db_info(new_path)

        return jsonify(
            {
                "success": True,
                "message": f"Metadata database path updated and saved persistently: {new_path}",
                "path": new_path,
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


@api_bp.route("/missing_books")
def get_missing_books_api():
    """API endpoint to get all missing books."""
    try:
        from app.services.database import get_all_missing_books

        limit = request.args.get("limit", type=int)
        db_path = current_app.config["DB_PATH"]

        missing_books = get_all_missing_books(db_path, limit)

        return jsonify(
            {
                "success": True,
                "missing_books": missing_books,
                "count": len(missing_books),
            }
        )
    except Exception as e:
        return jsonify(
            {"success": False, "error": f"Error fetching missing books: {str(e)}"}
        ), 500


@api_bp.route("/missing_books/stats")
def get_missing_books_stats_api():
    """API endpoint to get missing books statistics."""
    try:
        db_path = current_app.config["DB_PATH"]
        stats = get_missing_book_stats(db_path)

        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        return jsonify(
            {"success": False, "error": f"Error fetching missing books stats: {str(e)}"}
        ), 500


@api_bp.route("/missing_books/author/<author_name>")
def get_missing_books_by_author_api(author_name):
    """API endpoint to get missing books for a specific author."""
    try:
        from app.services.database import get_missing_books_by_author

        db_path = current_app.config["DB_PATH"]
        missing_books = get_missing_books_by_author(db_path, author_name)

        return jsonify(
            {
                "success": True,
                "author": author_name,
                "missing_books": missing_books,
                "count": len(missing_books),
            }
        )
    except Exception as e:
        return jsonify(
            {
                "success": False,
                "error": f"Error fetching missing books for {author_name}: {str(e)}",
            }
        ), 500


@api_bp.route("/missing_books/populate", methods=["POST"])
def populate_missing_books_api():
    """API endpoint to populate missing books database from OpenLibrary."""
    try:
        from app.services.openlibrary import populate_missing_books_database

        data = request.get_json() or {}
        limit_authors = data.get("limit_authors")
        verbose = data.get("verbose", False)

        db_path = current_app.config["DB_PATH"]

        result = populate_missing_books_database(db_path, limit_authors, verbose)

        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:
        return jsonify(
            {
                "success": False,
                "error": f"Error populating missing books database: {str(e)}",
            }
        ), 500


# Global variable to track population progress
populate_progress = {
    "active": False,
    "cancelled": False,
    "paused": False,
    "current_author": "",
    "processed": 0,
    "total": 0,
    "missing_found": 0,
    "errors": [],
    "status": "idle",
}


@api_bp.route("/missing_books/populate/stream", methods=["GET"])
def populate_missing_books_stream():
    """API endpoint to populate missing books database with progress streaming."""
    import json

    from flask import Response

    # Extract request data and config BEFORE creating generator
    data = request.args.to_dict() or {}
    limit_authors = data.get("limit_authors")
    verbose = data.get("verbose", "false").lower() == "true"
    db_path = current_app.config["DB_PATH"]

    def generate_progress():
        try:
            import os
            import time

            from app.services.database import (
                clear_missing_books,
                get_author_books,
                get_authors,
            )
            from app.services.openlibrary import compare_author_books

            global populate_progress

            # Reset progress
            populate_progress.update(
                {
                    "active": True,
                    "cancelled": False,
                    "current_author": "",
                    "processed": 0,
                    "total": 0,
                    "missing_found": 0,
                    "errors": [],
                    "status": "starting",
                }
            )

            print(f"DEBUG: DB path is: {db_path}")
            print(f"DEBUG: Current working directory: {os.getcwd()}")

            # Send initial status
            yield f"data: {json.dumps(populate_progress)}\n\n"

            # Clear existing missing books data
            populate_progress.update(
                {
                    "status": "clearing",
                    "message": "Clearing existing missing books data...",
                }
            )
            yield f"data: {json.dumps(populate_progress)}\n\n"

            print("DEBUG: About to clear missing books")
            clear_missing_books(db_path)
            print("DEBUG: Cleared missing books successfully")

            # Get all authors
            populate_progress.update(
                {
                    "status": "loading_authors",
                    "message": "Loading authors from database...",
                }
            )
            yield f"data: {json.dumps(populate_progress)}\n\n"

            print("DEBUG: About to get authors")
            authors = get_authors(db_path)
            print(f"DEBUG: Got {len(authors)} authors")

            original_count = len(authors)
            if limit_authors:
                authors = authors[:limit_authors]

            populate_progress.update(
                {
                    "total": len(authors),
                    "status": "processing",
                    "message": f"Found {original_count} authors in database{f', processing first {len(authors)}' if limit_authors else f', processing all {len(authors)}'}",
                }
            )
            yield f"data: {json.dumps(populate_progress)}\n\n"

            total_missing_books_found = 0
            total_new_books_added = 0

            for i, author in enumerate(authors, 1):
                # Check for cancellation
                if populate_progress["cancelled"]:
                    populate_progress.update(
                        {
                            "status": "cancelled",
                            "message": "Population cancelled by user",
                        }
                    )
                    yield f"data: {json.dumps(populate_progress)}\n\n"
                    break

                # Check for pause - wait until resumed or cancelled
                if populate_progress["paused"] and not populate_progress["cancelled"]:
                    # Send pause notification once
                    pause_message = populate_progress.copy()
                    pause_message.update(
                        {
                            "status": "paused",
                            "message": f"Population paused at author {i}/{len(authors)}: {author}",
                        }
                    )
                    yield f"data: {json.dumps(pause_message)}\n\n"

                    # Wait for resume or cancellation without spamming the stream
                    while (
                        populate_progress["paused"]
                        and not populate_progress["cancelled"]
                    ):
                        time.sleep(1)  # Check every second but don't send data

                    # Send resume notification if not cancelled
                    if (
                        not populate_progress["cancelled"]
                        and not populate_progress["paused"]
                    ):
                        resume_message = populate_progress.copy()
                        resume_message.update(
                            {
                                "status": "processing",
                                "message": f"Population resumed at author {i}/{len(authors)}: {author}",
                            }
                        )
                        yield f"data: {json.dumps(resume_message)}\n\n"

                # Check again for cancellation after potential pause
                if populate_progress["cancelled"]:
                    populate_progress.update(
                        {
                            "status": "cancelled",
                            "message": "Population cancelled by user",
                        }
                    )
                    yield f"data: {json.dumps(populate_progress)}\n\n"
                    break

                # Update current author progress
                populate_progress.update(
                    {
                        "current_author": author,
                        "processed": i,
                        "message": f"Processing author {i}/{len(authors)}: {author}",
                    }
                )
                yield f"data: {json.dumps(populate_progress)}\n\n"

                try:
                    # Get local books for this author
                    local_books_data = get_author_books(db_path, author)
                    local_books = [book["title"] for book in local_books_data]

                    populate_progress.update(
                        {
                            "message": f"Found {len(local_books)} local books for {author}, querying OpenLibrary..."
                        }
                    )
                    yield f"data: {json.dumps(populate_progress)}\n\n"

                    # Compare with OpenLibrary
                    result = compare_author_books(author, local_books, db_path, verbose)

                    if result["success"]:
                        missing_count = result.get("missing_count", 0)
                        new_added = result.get("new_missing_books_added", 0)

                        total_missing_books_found += missing_count
                        total_new_books_added += new_added
                        populate_progress["missing_found"] = total_missing_books_found

                        # More detailed success message
                        if missing_count > 0:
                            populate_progress.update(
                                {
                                    "message": f"✓ {author}: Found {missing_count} missing books ({new_added} newly added to database)"
                                }
                            )
                        else:
                            populate_progress.update(
                                {
                                    "message": f"✓ {author}: No missing books found (all {len(local_books)} books are available)"
                                }
                            )
                        yield f"data: {json.dumps(populate_progress)}\n\n"
                    else:
                        error_msg = result.get("message", "Unknown error")
                        populate_progress["errors"].append(
                            {"author": author, "error": error_msg}
                        )
                        populate_progress.update(
                            {"message": f"✗ {author}: Error - {error_msg}"}
                        )
                        yield f"data: {json.dumps(populate_progress)}\n\n"

                    # Small delay to be respectful to OpenLibrary API
                    time.sleep(0.5)

                except Exception as e:
                    error_msg = str(e)
                    populate_progress["errors"].append(
                        {"author": author, "error": error_msg}
                    )
                    populate_progress.update(
                        {"message": f"✗ {author}: Exception - {error_msg}"}
                    )
                    yield f"data: {json.dumps(populate_progress)}\n\n"

            # Final status
            if not populate_progress["cancelled"]:
                populate_progress.update(
                    {
                        "status": "completed",
                        "active": False,
                        "message": f"Population completed! Processed {len(authors)} authors, found {total_missing_books_found} missing books total ({total_new_books_added} newly added). {len(populate_progress['errors'])} errors occurred.",
                    }
                )
            else:
                populate_progress.update(
                    {
                        "active": False,
                        "message": f"Population cancelled after processing {populate_progress['processed']}/{len(authors)} authors",
                    }
                )

            yield f"data: {json.dumps(populate_progress)}\n\n"

        except Exception as e:
            print(f"DEBUG: Exception occurred: {str(e)}")
            print(f"DEBUG: Exception type: {type(e)}")
            import traceback

            print(f"DEBUG: Traceback: {traceback.format_exc()}")
            populate_progress.update(
                {"status": "error", "active": False, "message": str(e)}
            )
            yield f"data: {json.dumps(populate_progress)}\n\n"

    return Response(
        generate_progress(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@api_bp.route("/missing_books/populate/cancel", methods=["POST"])
def cancel_populate_missing_books():
    """API endpoint to cancel ongoing missing books population."""
    global populate_progress
    populate_progress["cancelled"] = True
    return jsonify({"success": True, "message": "Cancellation requested"})


@api_bp.route("/missing_books/populate/pause", methods=["POST"])
def pause_populate_missing_books():
    """API endpoint to pause ongoing missing books population."""
    global populate_progress
    if populate_progress["active"] and not populate_progress["cancelled"]:
        populate_progress["paused"] = True
        populate_progress["status"] = "paused"
        return jsonify({"success": True, "message": "Population paused"})
    else:
        return jsonify({"success": False, "message": "No active population to pause"})


@api_bp.route("/missing_books/populate/resume", methods=["POST"])
def resume_populate_missing_books():
    """API endpoint to resume paused missing books population."""
    global populate_progress
    if populate_progress["active"] and populate_progress["paused"]:
        populate_progress["paused"] = False
        populate_progress["status"] = "processing"
        return jsonify({"success": True, "message": "Population resumed"})
    else:
        return jsonify({"success": False, "message": "No paused population to resume"})


@api_bp.route("/missing_books/populate/status")
def get_populate_status():
    """API endpoint to get current population status."""
    global populate_progress
    return jsonify(populate_progress)


# ============== IGNORE BOOKS FUNCTIONALITY ==============


@api_bp.route("/book/ignore", methods=["POST"])
def ignore_book_api():
    """API endpoint to ignore a missing book."""
    try:
        from app.services.database import ignore_book

        data = request.get_json()
        if not data or "author" not in data or "title" not in data:
            return jsonify(
                {"success": False, "error": "Author and title are required"}
            ), 400

        author = data["author"]
        title = data["title"]
        db_path = current_app.config["DB_PATH"]

        success = ignore_book(db_path, author, title)

        if success:
            return jsonify(
                {
                    "success": True,
                    "message": f"Successfully ignored '{title}' by {author}",
                }
            )
        else:
            return jsonify(
                {
                    "success": False,
                    "error": "Failed to ignore book",
                }
            ), 500

    except Exception as e:
        return jsonify(
            {"success": False, "error": f"Error ignoring book: {str(e)}"}
        ), 500


@api_bp.route("/book/unignore", methods=["POST"])
def unignore_book_api():
    """API endpoint to unignore a book."""
    try:
        from app.services.database import unignore_book

        data = request.get_json()
        if not data or "author" not in data or "title" not in data:
            return jsonify(
                {"success": False, "error": "Author and title are required"}
            ), 400

        author = data["author"]
        title = data["title"]
        db_path = current_app.config["DB_PATH"]

        success = unignore_book(db_path, author, title)

        if success:
            return jsonify(
                {
                    "success": True,
                    "message": f"Successfully unignored '{title}' by {author}",
                }
            )
        else:
            return jsonify(
                {
                    "success": False,
                    "error": "Book was not in ignored list",
                }
            ), 404

    except Exception as e:
        return jsonify(
            {"success": False, "error": f"Error unignoring book: {str(e)}"}
        ), 500


@api_bp.route("/book/ignore_status")
def check_ignore_status_api():
    """API endpoint to check if a book is ignored."""
    try:
        from app.services.database import is_book_ignored

        author = request.args.get("author")
        title = request.args.get("title")

        if not author or not title:
            return jsonify(
                {"success": False, "error": "Author and title parameters are required"}
            ), 400

        db_path = current_app.config["DB_PATH"]
        is_ignored = is_book_ignored(db_path, author, title)

        return jsonify(
            {
                "success": True,
                "author": author,
                "title": title,
                "is_ignored": is_ignored,
            }
        )

    except Exception as e:
        return jsonify(
            {"success": False, "error": f"Error checking ignore status: {str(e)}"}
        ), 500


@api_bp.route("/ignored_books")
def get_ignored_books_api():
    """API endpoint to get all ignored books."""
    try:
        from app.services.database import get_ignored_books

        author = request.args.get("author")
        db_path = current_app.config["DB_PATH"]

        ignored_books = get_ignored_books(db_path, author)

        # Group by author if no specific author requested
        if not author:
            authors_ignored = {}
            for book in ignored_books:
                book_author = book["author"]
                if book_author not in authors_ignored:
                    authors_ignored[book_author] = []
                authors_ignored[book_author].append(
                    {
                        "title": book["title"],
                        "ignored_at": book["ignored_at"],
                    }
                )
            return jsonify(
                {
                    "success": True,
                    "ignored_books": authors_ignored,
                    "total_count": len(ignored_books),
                }
            )
        else:
            return jsonify(
                {
                    "success": True,
                    "author": author,
                    "ignored_books": ignored_books,
                    "count": len(ignored_books),
                }
            )

    except Exception as e:
        return jsonify(
            {"success": False, "error": f"Error fetching ignored books: {str(e)}"}
        ), 500


@api_bp.route("/ignored_books/stats")
def get_ignored_books_stats_api():
    """API endpoint to get ignored books statistics."""
    try:
        from app.services.database import get_ignored_books_stats

        db_path = current_app.config["DB_PATH"]
        stats = get_ignored_books_stats(db_path)

        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        return jsonify(
            {"success": False, "error": f"Error fetching ignored books stats: {str(e)}"}
        ), 500


@api_bp.route("/missing_books/clear", methods=["POST"])
def clear_missing_books_api():
    """API endpoint to clear missing books database."""
    try:
        from app.services.database import clear_missing_books

        data = request.get_json() or {}
        author = data.get("author")
        db_path = current_app.config["DB_PATH"]

        deleted_count = clear_missing_books(db_path, author)

        if author:
            message = f"Cleared {deleted_count} missing books for {author}"
        else:
            message = f"Cleared {deleted_count} missing books from database"

        return jsonify(
            {
                "success": True,
                "message": message,
                "deleted_count": deleted_count,
            }
        )

    except Exception as e:
        return jsonify(
            {"success": False, "error": f"Error clearing missing books: {str(e)}"}
        ), 500


@api_bp.route("/irc/sessions", methods=["POST"])
def create_irc_session_endpoint():
    """API endpoint to create a new IRC session."""
    try:
        # Create IRC session
        session_id = create_irc_session()

        return jsonify(
            {
                "success": True,
                "message": "IRC session created",
                "session_id": session_id,
            }
        ), 201
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/irc/sessions/<session_id>", methods=["GET"])
def get_irc_session_status_endpoint(session_id):
    """API endpoint to get the status of an IRC session."""
    try:
        status = get_session_status(session_id)
        return jsonify({"success": True, "session_id": session_id, "status": status})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/irc/sessions/active", methods=["GET"])
def list_active_irc_sessions_endpoint():
    """API endpoint to list all active IRC sessions."""
    try:
        sessions = list_active_sessions()
        return jsonify({"success": True, "active_sessions": sessions})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/irc/sessions/<session_id>/close", methods=["POST"])
def close_irc_session_endpoint(session_id):
    """API endpoint to close an IRC session."""
    try:
        success = close_session(session_id)

        if success:
            return jsonify(
                {"success": True, "message": f"IRC session {session_id} closed"}
            )
        else:
            return jsonify({"success": False, "error": "Session not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/irc/search", methods=["POST"])
def search_and_download_endpoint():
    """API endpoint to perform search and download in IRC."""
    try:
        data = request.get_json() or {}
        session_id = data.get("session_id")
        author = data.get("author")
        title = data.get("title")  # optional

        if not session_id or not author:
            return jsonify(
                {"success": False, "error": "Session ID and author are required"}
            ), 400

        # Perform search
        result = search_and_download(session_id, author, title)

        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/irc/search/author-level", methods=["POST"])
def search_author_level_endpoint():
    """API endpoint to perform author-level search (find unique books by author)."""
    try:
        data = request.get_json() or {}
        session_id = data.get("session_id")
        author = data.get("author")
        max_results = data.get("max_results", 50)
        timeout_minutes = data.get("timeout_minutes", 3)

        if not session_id or not author:
            return jsonify(
                {"success": False, "error": "Session ID and author are required"}
            ), 400

        # Get the IRC session
        from app.services.irc import get_session

        session = get_session(session_id)
        if not session:
            return jsonify({"success": False, "error": "Session not found"}), 404

        # Perform author-level search
        unique_books = session.search_author_level(author, max_results, timeout_minutes)

        return jsonify(
            {
                "success": True,
                "search_type": "author_level",
                "author": author,
                "unique_books": unique_books,
                "total_found": len(unique_books),
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/irc/search/title-level", methods=["POST"])
def search_title_level_endpoint():
    """API endpoint to perform title-level search (find specific book with server options)."""
    try:
        data = request.get_json() or {}
        session_id = data.get("session_id")
        author = data.get("author")
        title = data.get("title")
        max_results = data.get("max_results", 20)
        timeout_minutes = data.get("timeout_minutes", 3)

        if not session_id or not author or not title:
            return jsonify(
                {
                    "success": False,
                    "error": "Session ID, author, and title are required",
                }
            ), 400

        # Get the IRC session
        from app.services.irc import get_session

        session = get_session(session_id)
        if not session:
            return jsonify({"success": False, "error": "Session not found"}), 404

        # Perform title-level search
        server_candidates = session.search_title_level(
            author, title, max_results, timeout_minutes
        )

        return jsonify(
            {
                "success": True,
                "search_type": "title_level",
                "author": author,
                "title": title,
                "server_candidates": server_candidates,
                "total_found": len(server_candidates),
            }
        )

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/irc/smart-search", methods=["POST"])
def smart_search_and_download_endpoint():
    """API endpoint for intelligent two-tier search and download with automatic fallback."""
    try:
        data = request.get_json() or {}
        session_id = data.get("session_id")
        author = data.get("author")
        title = data.get(
            "title"
        )  # optional - if not provided, does author-level search
        timeout_minutes = data.get("timeout_minutes", 3)
        custom_filename = data.get("custom_filename")

        if not session_id or not author:
            return jsonify(
                {"success": False, "error": "Session ID and author are required"}
            ), 400

        # Get the IRC session
        from app.services.irc import get_session

        session = get_session(session_id)
        if not session:
            return jsonify({"success": False, "error": "Session not found"}), 404

        # Perform smart search and download
        result = session.smart_search_and_download(
            author, title, timeout_minutes, custom_filename
        )

        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/irc/download/fallback", methods=["POST"])
def download_with_fallback_endpoint():
    """API endpoint to download with automatic fallback across multiple candidates."""
    try:
        data = request.get_json() or {}
        session_id = data.get("session_id")
        candidates = data.get("candidates", [])
        timeout_minutes = data.get("timeout_minutes", 3)
        custom_filename = data.get("custom_filename")

        if not session_id or not candidates:
            return jsonify(
                {"success": False, "error": "Session ID and candidates are required"}
            ), 400

        # Get the IRC session
        from app.services.irc import get_session

        session = get_session(session_id)
        if not session:
            return jsonify({"success": False, "error": "Session not found"}), 404

        # Perform download with fallback
        result = session.download_with_fallback(
            candidates, timeout_minutes, custom_filename
        )

        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/irc/download/epub", methods=["POST"])
def download_epub_only_endpoint():
    """API endpoint to download EPUB files only (openbooks pattern)."""
    try:
        data = request.get_json() or {}
        session_id = data.get("session_id")
        download_command = data.get("download_command")
        output_dir = data.get("output_dir")  # optional

        if not session_id or not download_command:
            return jsonify(
                {
                    "success": False,
                    "error": "Session ID and download command are required",
                }
            ), 400

        # Perform EPUB-only download
        result = download_epub_only(session_id, download_command, output_dir)

        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
