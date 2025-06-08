import os
import random
import re
import socket
import sqlite3
import time
import zipfile
from typing import List, Set, Tuple
from urllib.parse import quote

import requests

# Path to the Calibre metadata.db file
DB_PATH = "metadata.db"
NEW_DB_PATH = "authors_books.db"


def initialize_database():
    """Initialize the authors_books database from Calibre metadata if it doesn't exist."""
    if os.path.exists(NEW_DB_PATH):
        print(f"Database {NEW_DB_PATH} already exists. Skipping initialization.")
        return

    print("Initializing database from Calibre metadata...")

    # Connect to the Calibre database
    conn = sqlite3.connect(DB_PATH)
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
    new_conn = sqlite3.connect(NEW_DB_PATH)
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

    print(f"Inserted {len(author_book_list)} records into {NEW_DB_PATH}.")


# Initialize database
initialize_database()


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


# Function to check if a book title exists for an author in OpenLibrary
def is_book_missing(author, title, verbose=False):
    author_key = get_author_key(author, verbose=verbose)
    if not author_key:
        if verbose:
            print(
                f"[VERBOSE] Author key not found for '{author}'. Book '{title}' flagged as missing."
            )
        return True  # Author not found, so book is missing
    url = f"https://openlibrary.org/search.json?author={author_key}"
    if verbose:
        print(f"[VERBOSE] Querying books for author key: {author_key}")
        print(f"[VERBOSE] URL: {url}")
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            for doc in data.get("docs", []):
                if verbose:
                    print(f"[VERBOSE] Checking title: {doc.get('title', '')}")
                if doc.get("title", "").strip().lower() == title.strip().lower():
                    if verbose:
                        print(f"[VERBOSE] Book match found for '{title}'")
                    return False  # Book found
            if verbose:
                print(f"[VERBOSE] Book '{title}' not found for author '{author}'")
            return True  # Book not found
        else:
            print(f"Book API error for {author} ({author_key}): {response.status_code}")
            return False
    except Exception as e:
        print(f"Error querying OpenLibrary for {author} ({author_key}): {e}")
        return False


# Move IRC and download functions above the main logic so they are defined before use


def connect_to_irc(
    server, port, channel, nickname="DarkHorse", realname="DarkHorse", password=None
):
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


def match_missing_books_with_downloaded_titles(
    missing_books: List[Tuple[str, str]], found_titles: Set[str]
):
    print("\n[MATCH] Matching missing books with downloaded titles:")
    for author, title in missing_books:
        if title.strip().lower() in found_titles:
            print(f"[MATCH] Found missing book in download: {title}")
        else:
            print(f"[NO MATCH] Still missing: {title}")


def process_author_for_missing_books(
    author: str, verbose: bool = True
) -> List[Tuple[str, str]]:
    """Process a single author to find missing books and search IRC by author name."""
    print(f"\n{'=' * 60}")
    print(f"PROCESSING AUTHOR: {author}")
    print(f"{'=' * 60}")

    # Connect to database
    conn = sqlite3.connect(NEW_DB_PATH)
    cursor = conn.cursor()

    # Get all local book titles for this author
    cursor.execute("SELECT id, title FROM author_book WHERE author = ?", (author,))
    local_books = {
        title.strip().lower(): book_id for book_id, title in cursor.fetchall()
    }

    print(f"[LOCAL] Found {len(local_books)} books in local library for '{author}'")

    # Query OpenLibrary for the author's ID
    author_key = get_author_key(author, verbose=verbose)
    missing_books = []

    if author_key:
        olid = author_key.replace("/authors/", "")
        url = f"https://openlibrary.org/authors/{olid}/works.json?limit=1000"
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

                print(
                    f"[OPENLIBRARY] Found {len(ol_titles)} English works for author '{author}' in OpenLibrary."
                )

                # Print and flag missing in local
                for ol_title in ol_titles:
                    if ol_title and ol_title not in local_books:
                        print(
                            f"[RESULT] Missing in local DB: '{ol_title}' (author: {author})"
                        )

                # Print and flag missing in OpenLibrary, and collect missing books
                for local_title, book_id in local_books.items():
                    if local_title not in ol_titles:
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
                print(
                    f"Works API error for {author} ({author_key}): {response.status_code}"
                )
        except Exception as e:
            print(f"Error querying OpenLibrary works for {author} ({author_key}): {e}")
    else:
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

    # IRC search by author name (not individual book titles)
    if missing_books:
        print(
            f"\n[IRC+DOWNLOAD] Found {len(missing_books)} missing books for: {author}"
        )
        print(
            f"[IRC] Will search IRC by AUTHOR NAME: '{author}' (NOT individual book titles)"
        )
        try:
            irc = connect_to_irc("irc.irchighway.net", 6667, "#ebooks", "DarkHorse")
            found_titles = search_author_on_irc_and_download_zip(irc, author)
            if found_titles:
                match_missing_books_with_downloaded_titles(missing_books, found_titles)
            irc.close()
        except Exception as e:
            print(f"[IRC] Error during IRC search for '{author}': {e}")
    else:
        print(f"[RESULT] No missing books for {author} to search on IRC.")

    return missing_books


# Reopen the new database to update 'missing' column
new_conn = sqlite3.connect(NEW_DB_PATH)
new_cursor = new_conn.cursor()

# =====================
# TESTING MODE: Only one random author is processed per run to avoid errors and rate limits.
# TODO: Implement full author iteration with error handling and batching for production use.
# =====================

# Fetch all authors, pick 1 at random, and check all their books from OpenLibrary
new_cursor.execute("SELECT DISTINCT author FROM author_book")
authors = [row[0] for row in new_cursor.fetchall()]
if authors:
    test_author = random.choice(authors)
    print(f"[TEST] Randomly selected author: {test_author}")

    # Process the author (this will search IRC by author name, not book titles)
    missing_books = process_author_for_missing_books(test_author, verbose=True)
else:
    print("No authors found in the database.")

new_conn.close()

print(
    "Finished checking all books for a random author against OpenLibrary API and updated 'missing' flags."
)

# Print missing books after checking
new_conn = sqlite3.connect(NEW_DB_PATH)
new_cursor = new_conn.cursor()
new_cursor.execute("SELECT author, title FROM author_book WHERE missing = 1")
missing_books = new_cursor.fetchall()
if missing_books:
    print("\n[RESULT] Local books missing in OpenLibrary:")
    for author, title in missing_books:
        print(f"- Author: {author} | Title: {title}")
else:
    print("\n[RESULT] No local books missing in OpenLibrary for the tested author.")
new_conn.close()
