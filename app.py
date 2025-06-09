#!/usr/bin/env python3
"""
Flask Web Interface for Calibre Library Monitor
Shows authors, titles, missing books, and provides IRC search functionality
"""

import os
import re
import socket
import sqlite3
import threading
import time
import zipfile
from typing import List, Set, Tuple
from urllib.parse import quote

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
app.secret_key = "calibre_monitor_secret_key_change_in_production"

# Database paths
DB_PATH = "authors_books.db"
CALIBRE_DB_PATH = "metadata.db"

# Global variable to track IRC search status
irc_search_status = {}


def initialize_database():
    """Initialize the authors_books database from Calibre metadata if it doesn't exist."""
    if os.path.exists(DB_PATH):
        print(f"Database {DB_PATH} already exists. Skipping initialization.")
        return {"success": True, "message": "Database already exists"}

    if not os.path.exists(CALIBRE_DB_PATH):
        return {
            "success": False,
            "message": f"Calibre database {CALIBRE_DB_PATH} not found",
        }

    print("Initializing database from Calibre metadata...")

    try:
        # Connect to the Calibre database
        conn = sqlite3.connect(CALIBRE_DB_PATH)
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
        new_conn = sqlite3.connect(DB_PATH)
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

        print(f"Inserted {len(author_book_list)} records into {DB_PATH}.")
        return {
            "success": True,
            "message": f"Initialized database with {len(author_book_list)} records",
        }

    except Exception as e:
        return {"success": False, "message": f"Error initializing database: {str(e)}"}


def get_author_key(author, verbose=False):
    """Get the OpenLibrary author key for a given author name."""
    url = f"https://openlibrary.org/search/authors.json?q={quote(author)}"
    if verbose:
        print(f"[VERBOSE] Querying author key for: {author}")
        print(f"[VERBOSE] URL: {url}")
    try:
        # Add small delay to avoid rate limiting
        time.sleep(0.5)
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            for doc in data.get("docs", []):
                if verbose:
                    print(f"[VERBOSE] Found author candidate: {doc.get('name', '')}")
                # Match author name exactly (case-insensitive)
                if doc.get("name", "").strip().lower() == author.strip().lower():
                    if verbose:
                        print(f"[VERBOSE] Author match found: {doc.get('key')}")
                    return doc.get("key")
        else:
            print(f"Author API error for {author}: {response.status_code}")
    except Exception as e:
        print(f"Error querying OpenLibrary for author {author}: {e}")
    return None


def connect_to_irc(
    server,
    port,
    channel,
    nickname="WebDarkHorse",
    realname="WebDarkHorse",
    password=None,
):
    """Connect to IRC server and join channel."""
    irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print(f"[IRC] Connecting to {server}:{port}...")
    irc.connect((server, port))
    irc.send(f"NICK {nickname}\r\n".encode())
    irc.send(f"USER {nickname} 0 * :{realname or nickname}\r\n".encode())
    if password:
        irc.send(f"PASS {password}\r\n".encode())
    connected = False
    while not connected:
        resp = irc.recv(2048).decode(errors="ignore")
        print(f"[IRC] {resp.strip()}")
        if "004" in resp or "Welcome" in resp:
            connected = True
        elif "433" in resp:
            print(f"[IRC] Nickname {nickname} is already in use.")
            nickname = nickname + "_"
            irc.send(f"NICK {nickname}\r\n".encode())
    irc.send(f"JOIN {channel}\r\n".encode())
    print(f"[IRC] Joined channel {channel}")
    return irc


def search_author_on_irc_and_download_zip(
    irc, author, download_dir="downloads"
) -> Set[str]:
    """Search for an author by name on IRC and download the zip file with book listings."""
    # Search by author name (not book title)
    search_cmd = f"@find {author}\r\n"
    irc.send(search_cmd.encode())
    print(f"[IRC] Searching for AUTHOR: '{author}' (not individual book titles)")
    print(f"[IRC] Sent search command: {search_cmd.strip()}")

    link = None
    irc.settimeout(60)
    try:
        while True:
            resp = irc.recv(4096).decode(errors="ignore")
            print(f"[IRC] {resp.strip()}")
            match = re.search(r"(https?://\S+\.zip)", resp)
            if match:
                link = match.group(1)
                print(f"[IRC] Found zip link for author '{author}': {link}")
                break
    except socket.timeout:
        print(f"[IRC] Timeout waiting for zip link for author '{author}'.")
        return set()

    if not link:
        print(f"[IRC] No zip link found for author '{author}'.")
        return set()

    os.makedirs(download_dir, exist_ok=True)
    zip_path = os.path.join(download_dir, f"{author.replace(' ', '_')}.zip")
    print(f"[DOWNLOAD] Downloading zip file for author '{author}' to {zip_path} ...")

    try:
        r = requests.get(link, timeout=30)
        with open(zip_path, "wb") as f:
            f.write(r.content)
        print(f"[DOWNLOAD] Download complete for author '{author}'.")
    except Exception as e:
        print(f"[DOWNLOAD] Error downloading zip for author '{author}': {e}")
        return set()

    found_titles = set()
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            for name in z.namelist():
                if name.lower().endswith(".txt"):
                    with z.open(name) as txtfile:
                        text = txtfile.read().decode(errors="ignore")
                        for line in text.splitlines():
                            line = line.strip()
                            if (
                                3 < len(line) < 120
                                and not line.islower()
                                and not line.isupper()
                            ):
                                found_titles.add(line.lower())
    except Exception as e:
        print(f"[PARSE] Error parsing zip file for author '{author}': {e}")
        return set()

    print(
        f"[PARSE] Found {len(found_titles)} possible titles in downloaded text files for author '{author}'."
    )
    return found_titles


def process_author_for_missing_books(
    author: str, verbose: bool = True
) -> List[Tuple[str, str]]:
    """Process a single author to find missing books and search IRC by author name."""
    if verbose:
        print(f"\n{'=' * 60}")
        print(f"PROCESSING AUTHOR: {author}")
        print(f"{'=' * 60}")

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get all local book titles for this author
    cursor.execute("SELECT id, title FROM author_book WHERE author = ?", (author,))
    local_books = {
        title.strip().lower(): book_id for book_id, title in cursor.fetchall()
    }

    if verbose:
        print(f"[LOCAL] Found {len(local_books)} books in local library for '{author}'")

    # Query OpenLibrary for the author's ID
    author_key = get_author_key(author, verbose=verbose)
    missing_books = []

    if author_key:
        olid = author_key.replace("/authors/", "")
        url = f"https://openlibrary.org/authors/{olid}/works.json?limit=1000"
        if verbose:
            print(f"[VERBOSE] Works API URL: {url}")

        try:
            # Add delay for rate limiting
            time.sleep(1)
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                # Filter for English language works only
                ol_titles = set()
                for entry in data.get("entries", []):
                    languages = entry.get("languages", [])
                    is_english = False
                    for lang in languages:
                        if (
                            isinstance(lang, dict)
                            and lang.get("key") == "/languages/eng"
                        ):
                            is_english = True
                            break
                        elif isinstance(lang, str) and "eng" in lang.lower():
                            is_english = True
                            break
                    if not languages or is_english:
                        title = entry.get("title", "").strip().lower()
                        if title:
                            ol_titles.add(title)

                if verbose:
                    print(
                        f"[OPENLIBRARY] Found {len(ol_titles)} English works for author '{author}' in OpenLibrary."
                    )

                # Print and flag missing in local
                for ol_title in ol_titles:
                    if ol_title and ol_title not in local_books:
                        if verbose:
                            print(
                                f"[RESULT] Missing in local DB: '{ol_title}' (author: {author})"
                            )

                # Print and flag missing in OpenLibrary, and collect missing books
                for local_title, book_id in local_books.items():
                    if local_title not in ol_titles:
                        if verbose:
                            print(
                                f"[RESULT] Local book not found in OpenLibrary: '{local_title}' (author: {author})"
                            )
                        cursor.execute(
                            "UPDATE author_book SET missing = 1 WHERE id = ?",
                            (book_id,),
                        )
                        missing_books.append((author, local_title))

                conn.commit()
            else:
                if verbose:
                    print(
                        f"Works API error for {author} ({author_key}): {response.status_code}"
                    )
        except Exception as e:
            if verbose:
                print(
                    f"Error querying OpenLibrary works for {author} ({author_key}): {e}"
                )
    else:
        if verbose:
            print(
                f"[RESULT] Author key not found for '{author}'. All their books flagged as missing."
            )
        for local_title, book_id in local_books.items():
            cursor.execute(
                "UPDATE author_book SET missing = 1 WHERE id = ?", (book_id,)
            )
            missing_books.append((author, local_title))
        conn.commit()

    conn.close()
    return missing_books


def get_db_connection():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_authors_with_stats():
    """Get all authors with their book counts and missing book counts."""
    conn = get_db_connection()
    query = """
    SELECT 
        author,
        COUNT(*) as total_books,
        SUM(missing) as missing_books,
        GROUP_CONCAT(CASE WHEN missing = 1 THEN title END) as missing_titles
    FROM author_book 
    GROUP BY author 
    ORDER BY author
    """
    authors = conn.execute(query).fetchall()
    conn.close()
    return authors


def get_books_by_author(author: str):
    """Get all books for a specific author."""
    conn = get_db_connection()
    query = """
    SELECT id, title, missing 
    FROM author_book 
    WHERE author = ? 
    ORDER BY title
    """
    books = conn.execute(query, (author,)).fetchall()
    conn.close()
    return books


def get_missing_books_summary():
    """Get summary of missing books."""
    conn = get_db_connection()

    # Total missing books
    total_missing = conn.execute(
        "SELECT COUNT(*) FROM author_book WHERE missing = 1"
    ).fetchone()[0]

    # Authors with missing books
    authors_with_missing = conn.execute(
        "SELECT COUNT(DISTINCT author) FROM author_book WHERE missing = 1"
    ).fetchone()[0]

    # Recent missing books (top 10)
    recent_missing = conn.execute("""
        SELECT author, title 
        FROM author_book 
        WHERE missing = 1 
        ORDER BY author, title 
        LIMIT 10
    """).fetchall()

    conn.close()

    return {
        "total_missing": total_missing,
        "authors_with_missing": authors_with_missing,
        "recent_missing": [
            {"author": row[0], "title": row[1]} for row in recent_missing
        ],
    }


# Global variable to track IRC search status
irc_search_status = {}


@app.route("/")
def index():
    """Single page application main page."""
    return render_template("index.html")


# API Endpoints for SPA
@app.route("/api/authors")
def api_authors():
    """API endpoint to get all authors with stats."""
    authors = get_authors_with_stats()
    return jsonify([dict(author) for author in authors])


@app.route("/api/author/<author_name>")
def api_author_detail(author_name):
    """API endpoint to get books for a specific author."""
    books = get_books_by_author(author_name)
    missing_books = [dict(book) for book in books if book["missing"]]
    all_books = [dict(book) for book in books]

    return jsonify(
        {
            "author": author_name,
            "books": all_books,
            "missing_books": missing_books,
            "total_books": len(all_books),
            "missing_count": len(missing_books),
        }
    )


@app.route("/api/missing_books")
def api_missing_books():
    """API endpoint to get all missing books grouped by author."""
    conn = get_db_connection()
    missing_books = conn.execute("""
        SELECT author, title, id 
        FROM author_book 
        WHERE missing = 1 
        ORDER BY author, title
    """).fetchall()
    conn.close()

    # Group by author
    authors_missing = {}
    for book in missing_books:
        author = book["author"]
        if author not in authors_missing:
            authors_missing[author] = []
        authors_missing[author].append(dict(book))

    return jsonify(authors_missing)


@app.route("/api/search_author_irc", methods=["POST"])
def search_author_irc():
    """API endpoint to search for an author on IRC."""
    data = request.get_json()
    author = data.get("author")

    if not author:
        return jsonify({"error": "Author name required"}), 400

    # Check if search is already in progress
    if (
        author in irc_search_status
        and irc_search_status[author]["status"] == "searching"
    ):
        return jsonify({"error": "Search already in progress for this author"}), 409

    # Initialize search status
    irc_search_status[author] = {
        "status": "searching",
        "message": f"Starting IRC search for {author}...",
        "found_books": [],
        "timestamp": time.time(),
    }

    def search_in_background():
        """Background function to perform IRC search."""
        try:
            irc_search_status[author]["message"] = "Connecting to IRC..."

            # Use the existing function from the integrated main.py code
            missing_books = process_author_for_missing_books(author, verbose=False)

            if missing_books:
                irc_search_status[author]["message"] = (
                    f"Found {len(missing_books)} missing books. Searching IRC..."
                )

                # Connect to IRC and search
                irc = connect_to_irc(
                    "irc.irchighway.net", 6667, "#ebooks", "WebDarkHorse"
                )
                found_titles = search_author_on_irc_and_download_zip(irc, author)
                irc.close()

                # Match found titles with missing books
                matched_books = []
                for author_name, title in missing_books:
                    if title.strip().lower() in found_titles:
                        matched_books.append(title)

                irc_search_status[author].update(
                    {
                        "status": "completed",
                        "message": f"Search completed. Found {len(matched_books)} matching books.",
                        "found_books": matched_books,
                        "total_found_titles": len(found_titles),
                    }
                )
            else:
                irc_search_status[author].update(
                    {
                        "status": "completed",
                        "message": "No missing books found for this author.",
                        "found_books": [],
                    }
                )

        except Exception as e:
            irc_search_status[author].update(
                {
                    "status": "error",
                    "message": f"Error during IRC search: {str(e)}",
                    "found_books": [],
                }
            )

    # Start background search
    thread = threading.Thread(target=search_in_background)
    thread.daemon = True
    thread.start()

    return jsonify({"message": f"IRC search started for {author}"}), 202


@app.route("/api/search_status/<author>")
def search_status(author):
    """Get the status of IRC search for an author."""
    if author not in irc_search_status:
        return jsonify({"error": "No search found for this author"}), 404

    status = irc_search_status[author].copy()

    # Clean up old completed searches (older than 1 hour)
    if (
        status["status"] in ["completed", "error"]
        and time.time() - status["timestamp"] > 3600
    ):
        del irc_search_status[author]

    return jsonify(status)


@app.route("/api/refresh_author/<author>")
def refresh_author(author):
    """Refresh OpenLibrary data for a specific author."""
    try:
        # Process author against OpenLibrary using integrated function
        process_author_for_missing_books(author, verbose=False)

        # Get updated stats
        books = get_books_by_author(author)
        missing_count = len([book for book in books if book["missing"]])

        return jsonify(
            {
                "success": True,
                "message": f"Refreshed data for {author}",
                "missing_count": missing_count,
                "total_books": len(books),
            }
        )
    except Exception as e:
        return jsonify(
            {"success": False, "message": f"Error refreshing author data: {str(e)}"}
        ), 500


@app.route("/api/stats")
def api_stats():
    """API endpoint for dashboard statistics."""
    return jsonify(get_missing_books_summary())


@app.route("/api/initialize_database", methods=["POST"])
def api_initialize_database():
    """API endpoint to initialize database from Calibre metadata."""
    try:
        result = initialize_database()
        if result["success"]:
            return jsonify(result), 200
        else:
            return jsonify(result), 400
    except Exception as e:
        return jsonify(
            {"success": False, "message": f"Unexpected error: {str(e)}"}
        ), 500


@app.route("/api/process_all_authors", methods=["POST"])
def api_process_all_authors():
    """API endpoint to process all authors for missing books."""
    # Get optional parameters
    data = request.get_json() or {}
    limit = data.get(
        "limit", 10
    )  # Default to 10 authors to avoid overwhelming the system
    random_selection = data.get("random", True)  # Default to random selection

    # Check if database exists
    if not os.path.exists(DB_PATH):
        return jsonify(
            {
                "success": False,
                "message": "Database not initialized. Please initialize first.",
            }
        ), 400

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Get authors
        if random_selection:
            cursor.execute(
                "SELECT DISTINCT author FROM author_book ORDER BY RANDOM() LIMIT ?",
                (limit,),
            )
        else:
            cursor.execute("SELECT DISTINCT author FROM author_book LIMIT ?", (limit,))

        authors = [row[0] for row in cursor.fetchall()]
        conn.close()

        if not authors:
            return jsonify(
                {"success": False, "message": "No authors found in database"}
            ), 404

        # Process in background
        def process_authors_background():
            processed = 0
            errors = 0

            for author in authors:
                try:
                    process_author_for_missing_books(author, verbose=False)
                    processed += 1
                    print(f"Processed {processed}/{len(authors)}: {author}")
                    # Add delay to avoid rate limiting
                    time.sleep(2)
                except Exception as e:
                    errors += 1
                    print(f"Error processing {author}: {e}")

            print(
                f"Batch processing complete. Processed: {processed}, Errors: {errors}"
            )

        # Start background processing
        thread = threading.Thread(target=process_authors_background)
        thread.daemon = True
        thread.start()

        return jsonify(
            {
                "success": True,
                "message": f"Started processing {len(authors)} authors in background",
                "authors": authors,
                "limit": limit,
                "random": random_selection,
            }
        ), 202

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"Error starting batch processing: {str(e)}"}
        ), 500


@app.route("/api/process_specific_author", methods=["POST"])
def api_process_specific_author():
    """API endpoint to process a specific author by name from frontend input."""
    data = request.get_json()
    author_name = data.get("author") if data else None

    if not author_name:
        return jsonify({"success": False, "message": "Author name is required"}), 400

    # Check if database exists
    if not os.path.exists(DB_PATH):
        return jsonify(
            {
                "success": False,
                "message": "Database not initialized. Please initialize first.",
            }
        ), 400

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Check if author exists in database
        cursor.execute(
            "SELECT COUNT(*) FROM author_book WHERE author = ?", (author_name,)
        )
        count = cursor.fetchone()[0]
        conn.close()

        if count == 0:
            return jsonify(
                {
                    "success": False,
                    "message": f"Author '{author_name}' not found in database",
                }
            ), 404

        # Process the author
        missing_books = process_author_for_missing_books(author_name, verbose=True)

        return jsonify(
            {
                "success": True,
                "message": f"Processed author: {author_name}",
                "author": author_name,
                "missing_books_count": len(missing_books),
                "missing_books": [
                    {"author": mb[0], "title": mb[1]} for mb in missing_books
                ],
            }
        )

    except Exception as e:
        return jsonify(
            {
                "success": False,
                "message": f"Error processing author '{author_name}': {str(e)}",
            }
        ), 500


@app.route("/api/database_info")
def api_database_info():
    """API endpoint to get database information."""
    try:
        if not os.path.exists(DB_PATH):
            return jsonify(
                {
                    "initialized": False,
                    "calibre_db_exists": os.path.exists(CALIBRE_DB_PATH),
                    "message": "Database not initialized",
                }
            )

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Get basic stats
        cursor.execute("SELECT COUNT(*) FROM author_book")
        total_books = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT author) FROM author_book")
        total_authors = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM author_book WHERE missing = 1")
        missing_books = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(DISTINCT author) FROM author_book WHERE missing = 1"
        )
        authors_with_missing = cursor.fetchone()[0]

        conn.close()

        return jsonify(
            {
                "initialized": True,
                "calibre_db_exists": os.path.exists(CALIBRE_DB_PATH),
                "total_books": total_books,
                "total_authors": total_authors,
                "missing_books": missing_books,
                "authors_with_missing": authors_with_missing,
                "database_path": DB_PATH,
                "calibre_database_path": CALIBRE_DB_PATH,
            }
        )

    except Exception as e:
        return jsonify({"error": f"Error getting database info: {str(e)}"}), 500


@app.route("/api/search_authors")
def api_search_authors():
    """API endpoint to search for authors by name pattern."""
    query = request.args.get("q", "").strip()
    limit = int(request.args.get("limit", 10))

    if len(query) < 2:
        return jsonify([])

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Search for authors with names containing the query
        cursor.execute(
            """
            SELECT DISTINCT author, COUNT(*) as book_count,
                   SUM(CASE WHEN missing = 1 THEN 1 ELSE 0 END) as missing_count
            FROM author_book 
            WHERE author LIKE ? 
            GROUP BY author 
            ORDER BY author 
            LIMIT ?
            """,
            (f"%{query}%", limit),
        )

        authors = []
        for row in cursor.fetchall():
            authors.append(
                {"name": row[0], "book_count": row[1], "missing_count": row[2]}
            )

        conn.close()
        return jsonify(authors)

    except Exception as e:
        return jsonify({"error": f"Error searching authors: {str(e)}"}), 500


@app.route("/api/author/<author_name>/compare")
def api_author_compare(author_name):
    """API endpoint to compare author's books between local and OpenLibrary."""
    try:
        # Get local books
        books = get_books_by_author(author_name)
        all_books = [dict(book) for book in books]

        # Get OpenLibrary data for comparison
        author_key = get_author_key(author_name, verbose=False)
        ol_books = set()

        if author_key:
            olid = author_key.replace("/authors/", "")
            url = f"https://openlibrary.org/authors/{olid}/works.json?limit=1000"

            try:
                time.sleep(0.5)  # Rate limiting
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    for entry in data.get("entries", []):
                        title = entry.get("title", "").strip()
                        # Filter for English language works
                        if title and len(title) > 1:
                            # Check if it's English language work
                            languages = entry.get("languages", [])
                            if not languages or any(
                                "/languages/eng" in str(lang) for lang in languages
                            ):
                                ol_books.add(title.lower())
            except Exception as e:
                print(f"Error fetching OpenLibrary data for {author_name}: {e}")

        # Enhance book data with comparison info
        enhanced_books = []
        local_titles = set()

        for book in all_books:
            title_lower = book["title"].lower()
            local_titles.add(title_lower)

            book_status = {
                "id": book["id"],
                "title": book["title"],
                "missing": book["missing"],
                "status": "unknown",
                "status_info": "",
            }

            if book["missing"] == 1:
                # Book is marked as missing in local
                if title_lower in ol_books:
                    book_status["status"] = "missing_local"
                    book_status["status_info"] = (
                        "Missing from local library but found in OpenLibrary"
                    )
                else:
                    book_status["status"] = "missing_both"
                    book_status["status_info"] = (
                        "Not found in local library or OpenLibrary"
                    )
            else:
                # Book exists in local
                if title_lower in ol_books:
                    book_status["status"] = "exists_both"
                    book_status["status_info"] = (
                        "Available in both local library and OpenLibrary"
                    )
                else:
                    book_status["status"] = "missing_api"
                    book_status["status_info"] = (
                        "Available locally but not found in OpenLibrary"
                    )

            enhanced_books.append(book_status)

        # Find books that exist in OpenLibrary but not locally
        api_only_books = []
        for ol_title in ol_books:
            if ol_title not in local_titles:
                api_only_books.append(
                    {
                        "title": ol_title.title(),  # Capitalize first letter
                        "status": "missing_local",
                        "status_info": "Found in OpenLibrary but missing from local library",
                    }
                )

        return jsonify(
            {
                "author": author_name,
                "books": enhanced_books,
                "api_only_books": api_only_books,
                "total_local_books": len(all_books),
                "total_api_books": len(ol_books),
                "missing_from_local": len(
                    [b for b in enhanced_books if b["missing"] == 1]
                )
                + len(api_only_books),
                "missing_from_api": len(
                    [b for b in enhanced_books if b["status"] == "missing_api"]
                ),
                "comparison_available": author_key is not None,
            }
        )

    except Exception as e:
        return jsonify({"error": f"Error comparing author data: {str(e)}"}), 500


if __name__ == "__main__":
    # Initialize database if it doesn't exist
    if not os.path.exists(DB_PATH):
        print("Database not found. Attempting to initialize from Calibre metadata...")
        result = initialize_database()
        if not result["success"]:
            print(f"Failed to initialize database: {result['message']}")
            print(
                "Please ensure metadata.db exists or run the initialization manually."
            )
        else:
            print(result["message"])

    print("Starting Calibre Monitor Web Interface...")
    print("Access the web interface at: http://localhost:5001")
    app.run(debug=True, host="0.0.0.0", port=5001)
