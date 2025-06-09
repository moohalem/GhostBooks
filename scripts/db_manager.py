#!/usr/bin/env python3
"""
Database management script for Calibre Library Monitor
Provides commands for database operations
"""

import argparse
import os
import sys

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.database import (
    get_database_stats,
    get_missing_books,
    initialize_database,
)
from config import get_config


def init_database():
    """Initialize the database from Calibre metadata."""
    print("📊 Initializing database from Calibre metadata...")

    config = get_config()
    result = initialize_database(config["DB_PATH"], config["CALIBRE_DB_PATH"])

    if result["success"]:
        print(f"✅ {result['message']}")
    else:
        print(f"❌ {result['message']}")


def show_stats():
    """Show database statistics."""
    print("📈 Database Statistics:")

    config = get_config()
    if not os.path.exists(config["DB_PATH"]):
        print("❌ Database not found. Run 'init' first.")
        return

    stats = get_database_stats(config["DB_PATH"])
    print(f"   📚 Total authors: {stats['authors']}")
    print(f"   📖 Total books: {stats['total_books']}")
    print(f"   🔍 Missing books: {stats['missing_books']}")


def list_missing():
    """List all missing books."""
    print("🔍 Missing Books:")

    config = get_config()
    if not os.path.exists(config["DB_PATH"]):
        print("❌ Database not found. Run 'init' first.")
        return

    missing_books = get_missing_books(config["DB_PATH"])

    if not missing_books:
        print("✅ No missing books found!")
        return

    # Group by author
    by_author = {}
    for book in missing_books:
        author = book["author"]
        if author not in by_author:
            by_author[author] = []
        by_author[author].append(book["title"])

    for author, titles in by_author.items():
        print(f"\n📝 {author} ({len(titles)} missing):")
        for title in titles:
            print(f"   • {title}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Database management for Calibre Library Monitor"
    )
    parser.add_argument(
        "command", choices=["init", "stats", "missing"], help="Command to execute"
    )

    args = parser.parse_args()

    if args.command == "init":
        init_database()
    elif args.command == "stats":
        show_stats()
    elif args.command == "missing":
        list_missing()


if __name__ == "__main__":
    main()
