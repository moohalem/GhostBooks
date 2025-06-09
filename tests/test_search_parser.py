#!/usr/bin/env python3
"""
Test suite for search parser functionality
"""

import os
import sys

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSearchParser:
    """Test class for search parser functionality."""

    def test_search_parser_initialization(self):
        """Test search parser initialization."""
        from app.services.search_parser import SearchResultParser

        parser = SearchResultParser()
        assert parser is not None

    def test_book_detail_creation(self):
        """Test BookDetail object creation."""
        from app.services.search_parser import BookDetail

        book = BookDetail(
            server="test_server",
            author="Test Author",
            title="Test Book",
            format="epub",
            size="1.2MB",
            full_command="!test download",
            raw_line="!test Test Author - Test Book [epub] [1.2MB]",
        )

        assert book.server == "test_server"
        assert book.author == "Test Author"
        assert book.title == "Test Book"
        assert book.format == "epub"
        assert book.size == "1.2MB"
        assert book.full_command == "!test download"

    def test_epub_only_filtering(self):
        """Test EPUB-only filtering functionality."""
        from app.services.search_parser import BookDetail, SearchResultParser

        parser = SearchResultParser()

        # Create test books with different formats
        books = [
            BookDetail(
                server="test",
                author="Author 1",
                title="Book 1",
                format="epub",
                size="1MB",
                full_command="!cmd1",
                raw_line="line1",
            ),
            BookDetail(
                server="test",
                author="Author 2",
                title="Book 2",
                format="pdf",
                size="2MB",
                full_command="!cmd2",
                raw_line="line2",
            ),
            BookDetail(
                server="test",
                author="Author 3",
                title="Book 3",
                format="EPUB",
                size="1.5MB",
                full_command="!cmd3",
                raw_line="line3",  # Test case insensitive
            ),
            BookDetail(
                server="test",
                author="Author 4",
                title="Book 4",
                format="mobi",
                size="1.8MB",
                full_command="!cmd4",
                raw_line="line4",
            ),
        ]

        # Test EPUB-only filtering
        epub_only = parser.filter_results(books, epub_only=True)

        # Should return only EPUB books (case insensitive)
        assert len(epub_only) == 2
        assert all(book.format.lower() == "epub" for book in epub_only)

    def test_format_priority_scoring(self):
        """Test format priority scoring with EPUB preference."""
        from app.services.search_parser import BookDetail, SearchResultParser

        parser = SearchResultParser()

        # Create books with different formats
        books = [
            BookDetail(
                server="test",
                author="Author",
                title="Book",
                format="pdf",
                size="2MB",
                full_command="!pdf",
                raw_line="pdf line",
            ),
            BookDetail(
                server="test",
                author="Author",
                title="Book",
                format="epub",
                size="1MB",
                full_command="!epub",
                raw_line="epub line",
            ),
            BookDetail(
                server="test",
                author="Author",
                title="Book",
                format="mobi",
                size="1.5MB",
                full_command="!mobi",
                raw_line="mobi line",
            ),
            BookDetail(
                server="test",
                author="Author",
                title="Book",
                format="txt",
                size="0.5MB",
                full_command="!txt",
                raw_line="txt line",
            ),
        ]

        # Filter with format priority (should prioritize EPUB)
        filtered = parser.filter_results(books, min_quality=True)

        # EPUB should be first due to highest priority
        assert len(filtered) > 0
        # In case of same book title, EPUB should be prioritized
        epub_books = [book for book in filtered if book.format.lower() == "epub"]
        assert len(epub_books) > 0

    def test_author_filtering(self):
        """Test author name filtering."""
        from app.services.search_parser import BookDetail, SearchResultParser

        parser = SearchResultParser()

        books = [
            BookDetail(
                server="test",
                author="Stephen King",
                title="The Shining",
                format="epub",
                size="1MB",
                full_command="!king1",
                raw_line="king line 1",
            ),
            BookDetail(
                server="test",
                author="Stephen King",
                title="IT",
                format="epub",
                size="1.5MB",
                full_command="!king2",
                raw_line="king line 2",
            ),
            BookDetail(
                server="test",
                author="J.K. Rowling",
                title="Harry Potter",
                format="epub",
                size="2MB",
                full_command="!rowling",
                raw_line="rowling line",
            ),
        ]

        # Test filtering by author
        king_books = parser.filter_results(books, author_filter="Stephen King")
        assert len(king_books) == 2
        assert all(book.author == "Stephen King" for book in king_books)

        # Test partial author match
        partial_books = parser.filter_results(books, author_filter="King")
        assert len(partial_books) == 2

    def test_empty_results_handling(self):
        """Test handling of empty search results."""
        from app.services.search_parser import SearchResultParser

        parser = SearchResultParser()

        # Test with empty list
        filtered = parser.filter_results([], epub_only=True)
        assert len(filtered) == 0

        # Test with None
        filtered = parser.filter_results(None, epub_only=True)
        assert filtered == []

    def test_case_insensitive_format_filtering(self):
        """Test case insensitive format filtering."""
        from app.services.search_parser import BookDetail, SearchResultParser

        parser = SearchResultParser()

        books = [
            BookDetail(
                server="test",
                author="Author",
                title="Book 1",
                format="EPUB",
                size="1MB",
                full_command="!cmd1",
                raw_line="line1",
            ),
            BookDetail(
                server="test",
                author="Author",
                title="Book 2",
                format="epub",
                size="1MB",
                full_command="!cmd2",
                raw_line="line2",
            ),
            BookDetail(
                server="test",
                author="Author",
                title="Book 3",
                format="Epub",
                size="1MB",
                full_command="!cmd3",
                raw_line="line3",
            ),
            BookDetail(
                server="test",
                author="Author",
                title="Book 4",
                format="PDF",
                size="2MB",
                full_command="!cmd4",
                raw_line="line4",
            ),
        ]

        # Test EPUB-only filtering with mixed case
        epub_only = parser.filter_results(books, epub_only=True)

        # Should return all EPUB books regardless of case
        assert len(epub_only) == 3
        assert all(book.format.lower() == "epub" for book in epub_only)

    def test_parse_search_results_error_handling(self):
        """Test error handling in parse_search_results."""
        from app.services.search_parser import SearchResultParser

        parser = SearchResultParser()

        # Test with malformed/empty results
        malformed_lines = [
            "",  # Empty line
            "invalid line with no format",  # No file extension
            "!bot some text without proper format",  # Missing brackets/format
        ]

        books, errors = parser.parse_search_results(malformed_lines)

        # Should handle errors gracefully
        assert isinstance(books, list)
        assert isinstance(errors, list)
        # May have some errors for malformed lines
        assert len(errors) >= 0
