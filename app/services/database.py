#!/usr/bin/env python3
"""
Database service for Calibre Library Monitor
Handles database initialization and basic operations
"""

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


def find_calibre_metadata_db() -> Optional[str]:
    """
    Find the Calibre metadata.db file in common locations.

    Returns:
        str: Path to metadata.db if found, None otherwise
    """
    # Common Calibre library locations
    home = Path.home()
    potential_paths = [
        # Current directory
        Path("metadata.db"),
        Path("./metadata.db"),
        # Common Calibre library locations on Linux
        home / "Calibre Library" / "metadata.db",
        home / "calibre-library" / "metadata.db",
        home / "Documents" / "Calibre Library" / "metadata.db",
        home / "Documents" / "calibre-library" / "metadata.db",
        # Common locations on macOS
        home
        / "Library"
        / "Application Support"
        / "calibre"
        / "Calibre Library"
        / "metadata.db",
        home / "Documents" / "Calibre Library" / "metadata.db",
        # Common locations on Windows (if running under WSL or Wine)
        home
        / ".wine"
        / "drive_c"
        / "users"
        / "Public"
        / "Documents"
        / "Calibre Library"
        / "metadata.db",
        # Additional search patterns
        home / "Books" / "metadata.db",
        home / "eBooks" / "metadata.db",
        home / "Library" / "metadata.db",
    ]

    # Also search for any directory containing metadata.db in home directory
    try:
        for path in home.rglob("metadata.db"):
            if path.is_file():
                # Verify it's actually a Calibre database by checking for expected tables
                if verify_calibre_database(str(path)):
                    return str(path)
    except (PermissionError, OSError):
        # Skip if we can't access certain directories
        pass

    # Check the predefined paths
    for path in potential_paths:
        if path.exists() and path.is_file():
            if verify_calibre_database(str(path)):
                return str(path)

    return None


def verify_calibre_database(db_path: str) -> bool:
    """
    Verify that a database file is a valid Calibre metadata database.

    Args:
        db_path: Path to the database file

    Returns:
        bool: True if it's a valid Calibre database, False otherwise
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check for essential Calibre tables
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name IN ('books', 'authors', 'books_authors_link')
        """)

        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        # All three essential tables should be present
        return len(tables) >= 3

    except (sqlite3.Error, OSError):
        return False


def get_metadata_db_info(db_path: str) -> Dict[str, Any]:
    """
    Get information about a Calibre metadata database.

    Args:
        db_path: Path to the metadata database

    Returns:
        dict: Information about the database
    """
    if not os.path.exists(db_path):
        return {"success": False, "message": "Database file not found"}

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get book count
        cursor.execute("SELECT COUNT(*) FROM books")
        book_count = cursor.fetchone()[0]

        # Get author count
        cursor.execute("SELECT COUNT(*) FROM authors")
        author_count = cursor.fetchone()[0]

        # Get library path (if available)
        cursor.execute("SELECT val FROM preferences WHERE key = 'library_path'")
        library_path_result = cursor.fetchone()
        library_path = library_path_result[0] if library_path_result else "Unknown"

        conn.close()

        return {
            "success": True,
            "books": book_count,
            "authors": author_count,
            "library_path": library_path,
            "database_path": db_path,
        }

    except sqlite3.Error as e:
        return {"success": False, "message": f"Database error: {str(e)}"}


def initialize_database(
    db_path: str, calibre_db_path: str, force_reinit: bool = False
) -> Dict[str, Any]:
    """Initialize the authors_books database from Calibre metadata."""
    # Ensure the data directory exists
    data_dir = os.path.dirname(db_path)
    if data_dir and not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)

    # Check if database exists and we're not forcing re-initialization
    if os.path.exists(db_path) and not force_reinit:
        # Get current database stats for comparison
        try:
            stats = get_database_stats(db_path)
            return {
                "success": True,
                "message": f"Database already exists with {stats['total_books']} records from {stats['authors']} authors",
                "records_imported": stats["total_books"],
                "authors_count": stats["authors"],
            }
        except Exception:
            # If we can't get stats, proceed with re-initialization
            pass

    # Remove existing database if we're re-initializing
    if os.path.exists(db_path) and force_reinit:
        print(f"Removing existing database for re-initialization: {db_path}")
        os.remove(db_path)

    # Try to find metadata.db if the provided path doesn't exist
    if not os.path.exists(calibre_db_path):
        print(
            f"Calibre database {calibre_db_path} not found. Searching for metadata.db..."
        )
        found_path = find_calibre_metadata_db()

        if found_path:
            print(f"Found Calibre database at: {found_path}")
            calibre_db_path = found_path
        else:
            return {
                "success": False,
                "message": "Calibre database not found. Please ensure metadata.db is accessible.",
            }

    print("Initializing database from Calibre metadata...")

    try:
        # Connect to the Calibre database
        conn = sqlite3.connect(calibre_db_path)
        cursor = conn.cursor()

        # Query to get book titles and their authors
        query = """
        SELECT books.title, authors.name
        FROM books
        JOIN books_authors_link ON books.id = books_authors_link.book
        JOIN authors ON books_authors_link.author = authors.id
        ORDER BY authors.name, books.title
        """

        cursor.execute(query)
        results = cursor.fetchall()

        # Create a list of (author, title) tuples
        author_book_list = [(author, title) for title, author in results]

        # Close the connection
        conn.close()

        # Create a new SQLite database and table for author-book list
        new_conn = sqlite3.connect(db_path)
        new_cursor = new_conn.cursor()

        # Create table with additional 'missing' and 'olid' columns
        new_cursor.execute("""
        CREATE TABLE IF NOT EXISTS author_book (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            title TEXT NOT NULL,
            missing BOOLEAN NOT NULL DEFAULT 0,
            olid TEXT,
            olid_last_updated TIMESTAMP
        )
        """)

        # Create the OLID caching table (for backward compatibility and detailed tracking)
        new_cursor.execute("""
        CREATE TABLE IF NOT EXISTS author_olid (
            author TEXT PRIMARY KEY,
            olid TEXT NOT NULL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Create the author processing table
        new_cursor.execute("""
        CREATE TABLE IF NOT EXISTS author_processing (
            author TEXT PRIMARY KEY,
            last_processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_count INTEGER DEFAULT 0
        )
        """)

        # Create the missing_book table for storing books found via OpenLibrary API
        new_cursor.execute("""
        CREATE TABLE IF NOT EXISTS missing_book (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            title TEXT NOT NULL,
            discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT DEFAULT 'openlibrary',
            UNIQUE(author, title)
        )
        """)

        # Insert data with missing set to 0 (False)
        new_cursor.executemany(
            "INSERT INTO author_book (author, title, missing) VALUES (?, ?, ?)",
            [(author, title, False) for author, title in author_book_list],
        )
        new_conn.commit()
        new_conn.close()

        print(f"Inserted {len(author_book_list)} records into {db_path}.")

        # Get unique authors count
        unique_authors = len(set(author for author, title in author_book_list))

        return {
            "success": True,
            "message": f"Initialized database with {len(author_book_list)} records from {unique_authors} authors",
            "records_imported": len(author_book_list),
            "authors_count": unique_authors,
        }

    except Exception as e:
        return {"success": False, "message": f"Error initializing database: {str(e)}"}


def get_database_connection(db_path: str) -> sqlite3.Connection:
    """Get a database connection."""
    return sqlite3.connect(db_path)


def get_authors(db_path: str) -> List[str]:
    """Get all unique authors from the database."""
    conn = get_database_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT author FROM author_book ORDER BY author")
    authors = [row[0] for row in cursor.fetchall()]
    conn.close()
    return authors


def get_author_books(db_path: str, author_name: str) -> List[Dict[str, Any]]:
    """Get all books for a specific author."""
    conn = get_database_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, title, missing FROM author_book WHERE author = ? ORDER BY title",
        (author_name,),
    )
    books = [
        {"id": row[0], "title": row[1], "missing": bool(row[2])}
        for row in cursor.fetchall()
    ]
    conn.close()
    return books


def get_missing_books(db_path: str) -> List[Dict[str, str]]:
    """Get all books marked as missing, excluding ignored books."""
    ensure_ignored_books_table(db_path)

    conn = get_database_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT ab.author, ab.title 
        FROM author_book ab
        LEFT JOIN ignored_books ib ON ab.author = ib.author AND ab.title = ib.title
        WHERE ab.missing = 1 AND ib.id IS NULL
        ORDER BY ab.author, ab.title
    """)
    missing_books = [{"author": row[0], "title": row[1]} for row in cursor.fetchall()]
    conn.close()
    return missing_books


def update_missing_books(db_path: str, author: str, missing_titles: List[str]) -> None:
    """Update missing status for books by an author."""
    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    # First, reset all books by this author to not missing
    cursor.execute("UPDATE author_book SET missing = 0 WHERE author = ?", (author,))

    # Then mark the missing ones
    for title in missing_titles:
        cursor.execute(
            "UPDATE author_book SET missing = 1 WHERE author = ? AND title = ?",
            (author, title),
        )

    conn.commit()
    conn.close()


def get_database_stats(db_path: str) -> Dict[str, int]:
    """Get database statistics."""
    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(DISTINCT author) FROM author_book")
    author_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM author_book")
    total_books = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM author_book WHERE missing = 1")
    missing_books = cursor.fetchone()[0]

    conn.close()

    return {
        "authors": author_count,
        "total_books": total_books,
        "missing_books": missing_books,
    }


def search_authors(db_path: str, query: str) -> List[str]:
    """Search for authors by name pattern."""
    conn = get_database_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT author FROM author_book WHERE author LIKE ? ORDER BY author LIMIT 50",
        (f"%{query}%",),
    )
    authors = [row[0] for row in cursor.fetchall()]
    conn.close()
    return authors


def search_authors_with_stats(
    db_path: str, query: str, limit: int = 20
) -> List[Dict[str, Any]]:
    """Search for authors by name pattern with detailed stats for autocomplete."""
    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    # Search with case-insensitive matching and return stats
    cursor.execute(
        """
        SELECT 
            ab.author,
            COUNT(*) as total_books,
            SUM(CASE WHEN ab.missing = 1 THEN 1 ELSE 0 END) as missing_books,
            MAX(ap.last_processed_at) as last_processed
        FROM author_book ab
        LEFT JOIN author_processing ap ON ab.author = ap.author
        WHERE LOWER(ab.author) LIKE LOWER(?)
        GROUP BY ab.author
        ORDER BY 
            CASE 
                WHEN LOWER(ab.author) LIKE LOWER(?) THEN 1  -- Exact match first
                WHEN LOWER(ab.author) LIKE LOWER(?) THEN 2  -- Starts with query
                ELSE 3  -- Contains query
            END,
            ab.author
        LIMIT ?
    """,
        (
            f"%{query}%",  # Main search filter
            query,  # Exact match priority
            f"{query}%",  # Starts with priority
            limit,
        ),
    )

    authors = []
    for row in cursor.fetchall():
        authors.append(
            {
                "id": row[0],  # Use author name as ID for now
                "name": row[0],
                "total_books": row[1],
                "missing_books": row[2] or 0,
                "last_processed": row[3],
                "completion_rate": round(((row[1] - (row[2] or 0)) / row[1]) * 100, 1)
                if row[1] > 0
                else 0,
            }
        )

    conn.close()
    return authors


def get_popular_authors(db_path: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get most popular authors (by book count) for search suggestions."""
    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT 
            author,
            COUNT(*) as total_books,
            SUM(CASE WHEN missing = 1 THEN 1 ELSE 0 END) as missing_books
        FROM author_book
        GROUP BY author
        ORDER BY total_books DESC, author
        LIMIT ?
    """,
        (limit,),
    )

    authors = []
    for row in cursor.fetchall():
        authors.append(
            {
                "name": row[0],
                "total_books": row[1],
                "missing_books": row[2] or 0,
                "completion_rate": round(((row[1] - (row[2] or 0)) / row[1]) * 100, 1)
                if row[1] > 0
                else 0,
            }
        )

    conn.close()
    return authors


def ensure_author_processing_table(db_path: str) -> None:
    """Ensure the author_processing table exists for tracking processing times."""
    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS author_processing (
            author TEXT PRIMARY KEY,
            last_processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_count INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


def update_author_processing_time(db_path: str, author: str) -> None:
    """Update the processing timestamp for an author."""
    ensure_author_processing_table(db_path)

    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR REPLACE INTO author_processing (author, last_processed_at, processed_count)
        VALUES (?, CURRENT_TIMESTAMP, 
                COALESCE((SELECT processed_count FROM author_processing WHERE author = ?), 0) + 1)
    """,
        (author, author),
    )

    conn.commit()
    conn.close()


def get_recently_processed_authors(
    db_path: str, limit: int = 10
) -> List[Dict[str, Any]]:
    """Get recently processed authors with their stats."""
    ensure_author_processing_table(db_path)

    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    # Get recently processed authors with their book stats
    cursor.execute(
        """
        SELECT 
            ap.author,
            ap.last_processed_at,
            ap.processed_count,
            COUNT(ab.id) as total_books,
            SUM(CASE WHEN ab.missing = 1 THEN 1 ELSE 0 END) as missing_books
        FROM author_processing ap
        LEFT JOIN author_book ab ON ap.author = ab.author
        GROUP BY ap.author, ap.last_processed_at, ap.processed_count
        ORDER BY ap.last_processed_at DESC
        LIMIT ?
    """,
        (limit,),
    )

    authors = []
    for row in cursor.fetchall():
        authors.append(
            {
                "name": row[0],
                "last_processed_at": row[1],
                "processed_count": row[2],
                "total_books": row[3] or 0,
                "missing_books": row[4] or 0,
            }
        )

    conn.close()
    return authors


def ensure_author_olid_table(db_path: str) -> None:
    """Ensure the author_olid table exists for caching OpenLibrary IDs."""
    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS author_olid (
            author TEXT PRIMARY KEY,
            olid TEXT NOT NULL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def get_author_olid(db_path: str, author: str) -> Optional[str]:
    """Get cached OLID for an author."""
    ensure_author_olid_table(db_path)

    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT olid FROM author_olid WHERE author = ?", (author,))

    result = cursor.fetchone()
    conn.close()

    return result[0] if result else None


def store_author_olid(db_path: str, author: str, olid: str) -> None:
    """Store or update OLID for an author."""
    ensure_author_olid_table(db_path)

    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR REPLACE INTO author_olid (author, olid, last_updated)
        VALUES (?, ?, CURRENT_TIMESTAMP)
    """,
        (author, olid),
    )

    conn.commit()
    conn.close()


def migrate_database_schema(db_path: str) -> Dict[str, Any]:
    """Migrate database schema to add OLID columns if they don't exist."""
    try:
        conn = get_database_connection(db_path)
        cursor = conn.cursor()

        # Check if OLID columns exist in author_book table
        cursor.execute("PRAGMA table_info(author_book)")
        columns = [column[1] for column in cursor.fetchall()]

        migrations_applied = []

        # Add OLID column if it doesn't exist
        if "olid" not in columns:
            cursor.execute("ALTER TABLE author_book ADD COLUMN olid TEXT")
            migrations_applied.append("Added 'olid' column to author_book table")

        # Add OLID last updated column if it doesn't exist
        if "olid_last_updated" not in columns:
            cursor.execute(
                "ALTER TABLE author_book ADD COLUMN olid_last_updated TIMESTAMP"
            )
            migrations_applied.append(
                "Added 'olid_last_updated' column to author_book table"
            )

        # Ensure the author_olid table exists (for detailed tracking)
        ensure_author_olid_table(db_path)

        # Ensure the missing_book table exists
        ensure_missing_book_table(db_path)

        conn.commit()
        conn.close()

        return {
            "success": True,
            "migrations_applied": migrations_applied,
            "message": f"Applied {len(migrations_applied)} database migrations",
        }

    except Exception as e:
        return {"success": False, "message": f"Database migration failed: {str(e)}"}


def store_author_olid_permanent(db_path: str, author: str, olid: Optional[str]) -> None:
    """Store OLID permanently in both the main author_book table and the tracking table."""
    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    try:
        # Update all records for this author in the main author_book table
        cursor.execute(
            """
            UPDATE author_book 
            SET olid = ?, olid_last_updated = CURRENT_TIMESTAMP 
            WHERE author = ?
        """,
            (olid, author),
        )

        # Also store in the tracking table for detailed statistics
        if olid:
            cursor.execute(
                """
                INSERT OR REPLACE INTO author_olid (author, olid, last_updated)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
                (author, olid),
            )

        conn.commit()

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_author_olid_from_books(db_path: str, author: str) -> Optional[str]:
    """Get OLID for an author from the main author_book table."""
    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT olid FROM author_book WHERE author = ? AND olid IS NOT NULL LIMIT 1",
        (author,),
    )

    result = cursor.fetchone()
    conn.close()

    return result[0] if result else None


def get_authors_with_olid(db_path: str) -> List[Dict[str, Any]]:
    """Get all authors that have OLID stored."""
    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT author, olid, olid_last_updated,
               COUNT(*) as book_count
        FROM author_book 
        WHERE olid IS NOT NULL 
        GROUP BY author, olid, olid_last_updated
        ORDER BY olid_last_updated DESC
    """)

    authors = []
    for row in cursor.fetchall():
        authors.append(
            {
                "author": row[0],
                "olid": row[1],
                "last_updated": row[2],
                "book_count": row[3],
            }
        )

    conn.close()
    return authors


def get_authors_without_olid(db_path: str) -> List[Dict[str, Any]]:
    """Get all authors that don't have OLID stored."""
    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT author, COUNT(*) as book_count
        FROM author_book 
        WHERE olid IS NULL 
        GROUP BY author
        ORDER BY book_count DESC
    """)

    authors = []
    for row in cursor.fetchall():
        authors.append({"author": row[0], "book_count": row[1]})

    conn.close()
    return authors


def clear_author_olid_cache(db_path: str) -> int:
    """Clear all cached OLIDs and return count of cleared entries."""
    ensure_author_olid_table(db_path)

    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM author_olid")
    count = cursor.fetchone()[0]

    cursor.execute("DELETE FROM author_olid")
    conn.commit()
    conn.close()

    return count


def get_author_olid_stats(db_path: str) -> Dict[str, Any]:
    """Get statistics about OLID storage and cache performance."""
    ensure_author_olid_table(db_path)

    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    # Get total entries in tracking table
    cursor.execute("SELECT COUNT(*) FROM author_olid")
    total_entries = cursor.fetchone()[0]

    # Get entries with valid OLIDs (not null/empty)
    cursor.execute(
        "SELECT COUNT(*) FROM author_olid WHERE olid IS NOT NULL AND olid != ''"
    )
    entries_with_olid = cursor.fetchone()[0]

    # Get entries without valid OLIDs
    entries_without_olid = total_entries - entries_with_olid

    # Calculate cache hit rate
    cache_hit_rate = round(
        (entries_with_olid / total_entries * 100) if total_entries > 0 else 0, 1
    )

    # Get additional stats from main author_book table
    cursor.execute(
        "SELECT COUNT(DISTINCT author) FROM author_book WHERE olid IS NOT NULL"
    )
    authors_with_permanent_olid = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT author) FROM author_book WHERE olid IS NULL")
    authors_without_permanent_olid = cursor.fetchone()[0]

    conn.close()

    return {
        "total_entries": total_entries,
        "entries_with_olid": entries_with_olid,
        "entries_without_olid": entries_without_olid,
        "cache_hit_rate": cache_hit_rate,
        "authors_with_permanent_olid": authors_with_permanent_olid,
        "authors_without_permanent_olid": authors_without_permanent_olid,
    }


def sync_with_calibre_metadata(db_path: str, calibre_db_path: str) -> Dict[str, Any]:
    """Synchronize the application database with the latest Calibre metadata."""
    if not os.path.exists(calibre_db_path):
        return {
            "success": False,
            "message": f"Calibre database not found at {calibre_db_path}",
        }

    if not os.path.exists(db_path):
        return {
            "success": False,
            "message": f"Application database not found at {db_path}. Please initialize first.",
        }

    try:
        # Connect to Calibre database
        calibre_conn = sqlite3.connect(calibre_db_path)
        calibre_conn.row_factory = sqlite3.Row
        calibre_cursor = calibre_conn.cursor()

        # Connect to application database
        app_conn = get_database_connection(db_path)
        app_cursor = app_conn.cursor()

        # Get existing author-book combinations
        app_cursor.execute("SELECT author, title FROM author_book")
        existing_combinations = set((row[0], row[1]) for row in app_cursor.fetchall())

        # Query Calibre database for all author-book combinations
        calibre_cursor.execute("""
            SELECT DISTINCT a.name as author, b.title
            FROM books b
            JOIN books_authors_link bal ON b.id = bal.book
            JOIN authors a ON bal.author = a.id
            WHERE a.name IS NOT NULL AND b.title IS NOT NULL
            ORDER BY a.name, b.title
        """)

        new_records = 0
        updated_records = 0

        for row in calibre_cursor.fetchall():
            author = row["author"].strip()
            title = row["title"].strip()

            # Skip empty authors or titles
            if not author or not title:
                continue

            combination = (author, title)

            if combination not in existing_combinations:
                # New record - insert it
                app_cursor.execute(
                    """
                    INSERT INTO author_book (author, title, missing)
                    VALUES (?, ?, 0)
                """,
                    (author, title),
                )
                new_records += 1

        # Get final statistics
        app_cursor.execute("SELECT COUNT(DISTINCT author) FROM author_book")
        total_authors = app_cursor.fetchone()[0]

        app_cursor.execute("SELECT COUNT(*) FROM author_book")
        total_books = app_cursor.fetchone()[0]

        # Commit changes
        app_conn.commit()

        # Close connections
        calibre_conn.close()
        app_conn.close()

        return {
            "success": True,
            "message": "Database synchronized successfully",
            "new_records": new_records,
            "updated_records": updated_records,
            "total_authors": total_authors,
            "total_books": total_books,
        }

    except Exception as e:
        return {"success": False, "message": f"Error during synchronization: {str(e)}"}


def ensure_missing_book_table(db_path: str) -> None:
    """Ensure the missing_book table exists for storing missing books found via OpenLibrary API."""
    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS missing_book (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            title TEXT NOT NULL,
            discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT DEFAULT 'openlibrary',
            UNIQUE(author, title)
        )
    """)

    conn.commit()
    conn.close()


def store_missing_books(db_path: str, author: str, missing_books: List[str]) -> int:
    """
    Store missing books for an author in the missing_book table.

    Args:
        db_path: Path to the database
        author: Author name
        missing_books: List of missing book titles

    Returns:
        int: Number of new missing books added
    """
    if not missing_books:
        return 0

    ensure_missing_book_table(db_path)

    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    new_books_added = 0

    try:
        for title in missing_books:
            # Use INSERT OR IGNORE to avoid duplicates
            cursor.execute(
                """
                INSERT OR IGNORE INTO missing_book (author, title, source) 
                VALUES (?, ?, 'openlibrary')
                """,
                (author, title),
            )
            # Check if a row was actually inserted
            if cursor.rowcount > 0:
                new_books_added += 1

        conn.commit()

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

    return new_books_added


def get_missing_books_by_author(db_path: str, author: str) -> List[Dict[str, Any]]:
    """
    Get all missing books for a specific author, excluding ignored books.

    Args:
        db_path: Path to the database
        author: Author name

    Returns:
        List of missing books with metadata
    """
    ensure_missing_book_table(db_path)
    ensure_ignored_books_table(db_path)

    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT mb.title, mb.discovered_at, mb.source 
        FROM missing_book mb
        LEFT JOIN ignored_books ib ON mb.author = ib.author AND mb.title = ib.title
        WHERE mb.author = ? AND ib.id IS NULL
        ORDER BY mb.discovered_at DESC
        """,
        (author,),
    )

    books = [
        {"title": row[0], "discovered_at": row[1], "source": row[2]}
        for row in cursor.fetchall()
    ]

    conn.close()
    return books


def get_all_missing_books(
    db_path: str, limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Get all missing books from the database, excluding ignored books.

    Args:
        db_path: Path to the database
        limit: Optional limit on number of results

    Returns:
        List of missing books with metadata
    """
    ensure_missing_book_table(db_path)
    ensure_ignored_books_table(db_path)

    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    query = """
        SELECT mb.author, mb.title, mb.discovered_at, mb.source 
        FROM missing_book mb
        LEFT JOIN ignored_books ib ON mb.author = ib.author AND mb.title = ib.title
        WHERE ib.id IS NULL
        ORDER BY mb.discovered_at DESC
    """

    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query)

    books = [
        {"author": row[0], "title": row[1], "discovered_at": row[2], "source": row[3]}
        for row in cursor.fetchall()
    ]

    conn.close()
    return books


def get_missing_book_stats(db_path: str) -> Dict[str, Any]:
    """
    Get statistics about missing books in the database, excluding ignored books.

    Args:
        db_path: Path to the database

    Returns:
        Dictionary with missing book statistics
    """
    ensure_missing_book_table(db_path)
    ensure_ignored_books_table(db_path)

    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    # Total missing books (excluding ignored)
    cursor.execute("""
        SELECT COUNT(*) FROM missing_book mb
        LEFT JOIN ignored_books ib ON mb.author = ib.author AND mb.title = ib.title
        WHERE ib.id IS NULL
    """)
    total_missing = cursor.fetchone()[0]

    # Authors with missing books (excluding ignored)
    cursor.execute("""
        SELECT COUNT(DISTINCT mb.author) FROM missing_book mb
        LEFT JOIN ignored_books ib ON mb.author = ib.author AND mb.title = ib.title
        WHERE ib.id IS NULL
    """)
    authors_with_missing = cursor.fetchone()[0]

    # Recent discoveries (last 7 days, excluding ignored)
    cursor.execute("""
        SELECT COUNT(*) FROM missing_book mb
        LEFT JOIN ignored_books ib ON mb.author = ib.author AND mb.title = ib.title
        WHERE mb.discovered_at >= datetime('now', '-7 days') AND ib.id IS NULL
    """)
    recent_discoveries = cursor.fetchone()[0]

    # Top authors with most missing books (excluding ignored)
    cursor.execute("""
        SELECT mb.author, COUNT(*) as missing_count 
        FROM missing_book mb
        LEFT JOIN ignored_books ib ON mb.author = ib.author AND mb.title = ib.title
        WHERE ib.id IS NULL
        GROUP BY mb.author 
        ORDER BY missing_count DESC 
        LIMIT 10
    """)
    top_authors = [
        {"author": row[0], "missing_count": row[1]} for row in cursor.fetchall()
    ]

    conn.close()

    return {
        "total_missing": total_missing,
        "authors_with_missing": authors_with_missing,
        "recent_discoveries": recent_discoveries,
        "top_authors": top_authors,
    }


def clear_missing_books(db_path: str, author: Optional[str] = None) -> int:
    """
    Clear missing books from the database.

    Args:
        db_path: Path to the database
        author: Optional author name to clear only their missing books

    Returns:
        Number of records deleted
    """
    ensure_missing_book_table(db_path)

    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    if author:
        cursor.execute("DELETE FROM missing_book WHERE author = ?", (author,))
    else:
        cursor.execute("DELETE FROM missing_book")

    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()

    return deleted_count


def ensure_ignored_books_table(db_path: str) -> None:
    """Ensure the ignored_books table exists for storing ignored missing books."""
    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ignored_books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            title TEXT NOT NULL,
            ignored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(author, title)
        )
    """)

    conn.commit()
    conn.close()


def ignore_book(db_path: str, author: str, title: str) -> bool:
    """
    Add a book to the ignored list and remove it from missing books.

    Args:
        db_path: Path to the database
        author: Author name
        title: Book title

    Returns:
        bool: True if successfully ignored, False otherwise
    """
    ensure_ignored_books_table(db_path)
    ensure_missing_book_table(db_path)

    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    try:
        # Add to ignored_books table (using INSERT OR IGNORE to handle duplicates)
        cursor.execute(
            "INSERT OR IGNORE INTO ignored_books (author, title) VALUES (?, ?)",
            (author, title),
        )

        # Remove from missing_book table if it exists there
        cursor.execute(
            "DELETE FROM missing_book WHERE author = ? AND title = ?", (author, title)
        )

        # Update author_book table to set missing = 0 if it exists there
        cursor.execute(
            "UPDATE author_book SET missing = 0 WHERE author = ? AND title = ?",
            (author, title),
        )

        conn.commit()
        return True

    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def unignore_book(db_path: str, author: str, title: str) -> bool:
    """
    Remove a book from the ignored list.

    Args:
        db_path: Path to the database
        author: Author name
        title: Book title

    Returns:
        bool: True if successfully unignored, False otherwise
    """
    ensure_ignored_books_table(db_path)

    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "DELETE FROM ignored_books WHERE author = ? AND title = ?", (author, title)
        )

        conn.commit()
        return cursor.rowcount > 0

    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def is_book_ignored(db_path: str, author: str, title: str) -> bool:
    """
    Check if a book is in the ignored list.

    Args:
        db_path: Path to the database
        author: Author name
        title: Book title

    Returns:
        bool: True if book is ignored, False otherwise
    """
    ensure_ignored_books_table(db_path)

    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT 1 FROM ignored_books WHERE author = ? AND title = ? LIMIT 1",
        (author, title),
    )

    result = cursor.fetchone() is not None
    conn.close()
    return result


def get_ignored_books(
    db_path: str, author: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get all ignored books, optionally filtered by author.

    Args:
        db_path: Path to the database
        author: Optional author name to filter by

    Returns:
        List of ignored books with metadata
    """
    ensure_ignored_books_table(db_path)

    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    if author:
        cursor.execute(
            "SELECT author, title, ignored_at FROM ignored_books WHERE author = ? ORDER BY ignored_at DESC",
            (author,),
        )
    else:
        cursor.execute(
            "SELECT author, title, ignored_at FROM ignored_books ORDER BY ignored_at DESC"
        )

    books = [
        {"author": row[0], "title": row[1], "ignored_at": row[2]}
        for row in cursor.fetchall()
    ]

    conn.close()
    return books


def get_ignored_books_stats(db_path: str) -> Dict[str, Any]:
    """
    Get statistics about ignored books.

    Args:
        db_path: Path to the database

    Returns:
        Dictionary with ignored book statistics
    """
    ensure_ignored_books_table(db_path)

    conn = get_database_connection(db_path)
    cursor = conn.cursor()

    # Total ignored books
    cursor.execute("SELECT COUNT(*) FROM ignored_books")
    total_ignored = cursor.fetchone()[0]

    # Authors with ignored books
    cursor.execute("SELECT COUNT(DISTINCT author) FROM ignored_books")
    authors_with_ignored = cursor.fetchone()[0]

    # Recent ignores (last 7 days)
    cursor.execute("""
        SELECT COUNT(*) FROM ignored_books 
        WHERE ignored_at >= datetime('now', '-7 days')
    """)
    recent_ignores = cursor.fetchone()[0]

    conn.close()

    return {
        "total_ignored": total_ignored,
        "authors_with_ignored": authors_with_ignored,
        "recent_ignores": recent_ignores,
    }
