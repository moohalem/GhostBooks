#!/usr/bin/env python3
"""
OpenLibrary service for Calibre Library Monitor
Handles OpenLibrary API interactions with OLID caching
"""

import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple
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


def filter_openlibrary_title(title: str) -> str:
    """
    Filter OpenLibrary title by removing parentheses content and colon content.

    Args:
        title: Original title from OpenLibrary

    Returns:
        Filtered title with parentheses and colon content removed
    """
    if not title:
        return ""

    # Remove content in parentheses (including the parentheses)
    filtered = re.sub(r"\([^)]*\)", "", title)

    # Remove colon and everything to the right of it
    if ":" in filtered:
        filtered = filtered.split(":")[0]

    # Clean up extra whitespace
    filtered = filtered.strip()

    return filtered


def smart_title_match(
    local_title: str, filtered_openlibrary_titles: Set[str]
) -> bool:
    """
    Check if a local title matches any filtered OpenLibrary title using smart matching.

    The local title is considered a match if it contains all the words from a filtered
    OpenLibrary title, allowing for more complete local titles to match shorter filtered ones.

    Args:
        local_title: Title from local Calibre library
        filtered_openlibrary_titles: Set of filtered OpenLibrary titles

    Returns:
        True if a match is found, False otherwise
    """
    if not local_title:
        return False

    # Normalize local title for comparison
    local_normalized = local_title.lower().strip()
    local_words = set(local_normalized.split())

    for ol_title in filtered_openlibrary_titles:
        if not ol_title:
            continue

        ol_normalized = ol_title.lower().strip()
        ol_words = set(ol_normalized.split())

        # Check if local title contains all words from OpenLibrary title
        # This allows "Home Coming: Escaping From Alcatraz" to match "Home Coming"
        if ol_words.issubset(local_words):
            return True

        # Also check exact match after normalization
        if local_normalized == ol_normalized:
            return True

    return False


def process_openlibrary_titles(
    titles: List[str],
) -> Tuple[List[str], Set[str]]:
    """
    Process OpenLibrary titles by filtering and removing duplicates.

    Args:
        titles: Raw titles from OpenLibrary API

    Returns:
        Tuple of (original_titles, filtered_unique_titles_set)
    """
    filtered_titles = []
    seen_filtered = set()

    for title in titles:
        filtered = filter_openlibrary_title(title)
        if filtered and filtered.lower() not in seen_filtered:
            filtered_titles.append(filtered)
            seen_filtered.add(filtered.lower())

    return filtered_titles, seen_filtered


def compare_author_books(
    author: str, local_books: List[str], db_path: Optional[str] = None, verbose: bool = False
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

    # Process and filter OpenLibrary titles
    processed_openlibrary_books, filtered_openlibrary_set = process_openlibrary_titles(
        openlibrary_books
    )

    # Find missing books using smart matching
    missing_books = []
    for title in processed_openlibrary_books:
        # Check if this OpenLibrary title is NOT found in local collection using smart matching
        # We need to reverse the logic: check if any local title matches this OpenLibrary title
        found_match = False
        for local_book in local_books:
            # Check if the local book contains all words from the filtered OpenLibrary title
            if smart_title_match(local_book, {title}):
                found_match = True
                break
        
        if not found_match:
            missing_books.append(title)

    return {
        "success": True,
        "author": author,
        "author_key": author_key,
        "local_count": len(local_books),
        "openlibrary_count": len(openlibrary_books),
        "missing_count": len(missing_books),
        "missing_books": missing_books,
    }
