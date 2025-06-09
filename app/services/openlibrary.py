#!/usr/bin/env python3
"""
OpenLibrary service for Calibre Library Monitor
Handles OpenLibrdef compare_author_books(
    author: str, local_books: List[str], db_path: Optional[str] = None, verbose: bool = False
) -> Dict[str, Any]: API interactions with OLID caching
"""

import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from .database import get_author_olid_from_books, store_author_olid_permanent


def get_author_key(
    author: str, db_path: Optional[str] = None, verbose: bool = False
) -> Optional[str]:
    """Get the OpenLibrary author key for a given author name, with permanent storage."""
    # Check permanent storage first if db_path is provided
    if db_path:
        cached_olid = get_author_olid_from_books(db_path, author)
        if cached_olid:
            if verbose:
                print(f"[VERBOSE] Using stored OLID for {author}: {cached_olid}")
            return cached_olid

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
                    olid = doc.get("key")
                    if verbose:
                        print(f"[VERBOSE] Author match found: {olid}")

                    # Store the OLID permanently if db_path is provided
                    if db_path:
                        store_author_olid_permanent(db_path, author, olid)
                        if verbose:
                            print(
                                f"[VERBOSE] Permanently stored OLID for {author}: {olid}"
                            )

                    return olid

            # If no exact match found, store that we tried (with None)
            if db_path:
                store_author_olid_permanent(db_path, author, None)
                if verbose:
                    print(
                        f"[VERBOSE] No OLID found for {author}, stored as None to avoid future API calls"
                    )
        else:
            print(f"Author API error for {author}: {response.status_code}")
    except Exception as e:
        print(f"Error querying OpenLibrary for author {author}: {e}")
    return None


def get_author_books_from_openlibrary(
    author_key: str, verbose: bool = False
) -> List[str]:
    """Get all books by an author from OpenLibrary."""
    url = f"https://openlibrary.org/authors/{author_key}/works.json?limit=1000"
    if verbose:
        print(f"[VERBOSE] Querying books for author key: {author_key}")
        print(f"[VERBOSE] URL: {url}")

    try:
        # Add small delay to avoid rate limiting
        time.sleep(0.5)
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            books = []
            for entry in data.get("entries", []):
                title = entry.get("title", "").strip()
                if title:
                    books.append(title)
            if verbose:
                print(f"[VERBOSE] Found {len(books)} books for author key {author_key}")
            return books
        else:
            print(
                f"Books API error for author key {author_key}: {response.status_code}"
            )
    except Exception as e:
        print(f"Error querying OpenLibrary books for author key {author_key}: {e}")

    return []


def compare_author_books(
    author: str, local_books: List[str], db_path: str = None, verbose: bool = False
) -> Dict[str, Any]:
    """Compare local books with OpenLibrary books for an author."""
    author_key = get_author_key(author, db_path, verbose)
    if not author_key:
        return {
            "success": False,
            "message": f"Author '{author}' not found on OpenLibrary",
        }

    openlibrary_books = get_author_books_from_openlibrary(author_key, verbose)
    if not openlibrary_books:
        return {
            "success": False,
            "message": f"No books found for author '{author}' on OpenLibrary",
        }

    # Normalize titles for comparison (case-insensitive)
    local_titles_normalized = {title.lower().strip() for title in local_books}
    openlibrary_titles_normalized = {
        title.lower().strip() for title in openlibrary_books
    }

    # Find missing books
    missing_normalized = openlibrary_titles_normalized - local_titles_normalized
    missing_books = [
        title
        for title in openlibrary_books
        if title.lower().strip() in missing_normalized
    ]

    return {
        "success": True,
        "author": author,
        "author_key": author_key,
        "local_count": len(local_books),
        "openlibrary_count": len(openlibrary_books),
        "missing_count": len(missing_books),
        "missing_books": missing_books,
    }
