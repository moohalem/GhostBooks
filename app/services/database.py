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

        # Create table with an additional 'missing' column
        new_cursor.execute("""
        CREATE TABLE IF NOT EXISTS author_book (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            title TEXT NOT NULL,
            missing BOOLEAN NOT NULL DEFAULT 0
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
        "SELECT title, missing FROM author_book WHERE author = ? ORDER BY title",
        (author_name,),
    )
    books = [{"title": row[0], "missing": bool(row[1])} for row in cursor.fetchall()]
    conn.close()
    return books


def get_missing_books(db_path: str) -> List[Dict[str, str]]:
    """Get all books marked as missing."""
    conn = get_database_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT author, title FROM author_book WHERE missing = 1 ORDER BY author, title"
    )
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
