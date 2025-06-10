#!/usr/bin/env python3
"""
Test suite for two-tier search functionality in IRC service.
Tests author-level and title-level search strategies.
"""

import os
import sys
from unittest.mock import Mock, patch

import pytest

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.irc import IRCSession


class TestTwoTierSearch:
    """Test cases for two-tier search functionality."""

    def setup_method(self):
        """Setup test IRC session."""
        self.session = IRCSession()
        self.session.connected = True
        self.session.socket = Mock()

    def test_normalize_title(self):
        """Test title normalization for comparison."""
        # Test basic normalization
        assert self.session._normalize_title("The Great Gatsby") == "great gatsby"
        assert (
            self.session._normalize_title("A Tale of Two Cities")
            == "tale of two cities"
        )
        assert (
            self.session._normalize_title("An American Tragedy") == "american tragedy"
        )

        # Test version removal
        assert self.session._normalize_title("Book Title v5") == "book title"
        assert self.session._normalize_title("Book Title V3") == "book title"

        # Test parentheses and brackets removal
        assert (
            self.session._normalize_title("Book Title (Complete Edition)")
            == "book title"
        )
        assert self.session._normalize_title("Book Title [Retail]") == "book title"

    def test_is_title_match(self):
        """Test title matching logic."""
        # Exact match
        assert self.session._is_title_match("great gatsby", "great gatsby") == True

        # Substring match
        assert self.session._is_title_match("gatsby", "great gatsby") == True
        assert self.session._is_title_match("great gatsby", "gatsby") == True

        # Word-based similarity
        assert self.session._is_title_match("great gatsby", "gatsby great") == True

        # No match
        assert self.session._is_title_match("different book", "great gatsby") == False

    def test_calculate_candidate_score(self):
        """Test candidate scoring system."""
        candidate_v5 = {
            "title": "Great Book v5",
            "size": "2.5MB",
            "format": "epub",
            "author": "Test Author",
        }

        candidate_v3 = {
            "title": "Great Book v3",
            "size": "2.0MB",
            "format": "mobi",
            "author": "Test Author",
        }

        score_v5 = self.session._calculate_candidate_score(candidate_v5, "author")
        score_v3 = self.session._calculate_candidate_score(candidate_v3, "author")

        # v5 should score higher than v3
        assert score_v5 > score_v3

        # Test quality indicators
        candidate_retail = {
            "title": "Great Book Retail Edition",
            "size": "2.0MB",
            "format": "epub",
            "author": "Test Author",
        }

        score_retail = self.session._calculate_candidate_score(
            candidate_retail, "author"
        )
        score_basic = self.session._calculate_candidate_score(candidate_v3, "author")

        # Retail should get bonus points
        assert score_retail > score_basic

    def test_select_best_candidate(self):
        """Test best candidate selection."""
        candidates = [
            {"title": "Book v3", "size": "1.0MB", "format": "pdf", "author": "Author"},
            {"title": "Book v5", "size": "2.0MB", "format": "epub", "author": "Author"},
            {"title": "Book v4", "size": "1.5MB", "format": "mobi", "author": "Author"},
        ]

        best = self.session._select_best_candidate(candidates, "author")

        # Should select v5 version
        assert best["title"] == "Book v5"

    def test_parse_size_for_scoring(self):
        """Test size parsing and scoring."""
        # Test different units
        assert self.session._parse_size_for_scoring("1.5MB") > 0
        assert self.session._parse_size_for_scoring("1500KB") > 0
        assert self.session._parse_size_for_scoring("0.5GB") > 0

        # Larger files should score higher (within reason)
        score_5mb = self.session._parse_size_for_scoring("5.0MB")
        score_1mb = self.session._parse_size_for_scoring("1.0MB")
        assert score_5mb > score_1mb

        # Test invalid size
        assert self.session._parse_size_for_scoring("invalid") == 0.0
        assert self.session._parse_size_for_scoring("") == 0.0

    @patch.object(IRCSession, "search_books")
    def test_search_author_level(self, mock_search):
        """Test author-level search functionality."""
        # Mock search results with different titles
        mock_search.return_value = [
            {
                "title": "Book One v5",
                "author": "Test Author",
                "format": "epub",
                "size": "2MB",
                "server": "Server1",
            },
            {
                "title": "Book One v3",
                "author": "Test Author",
                "format": "mobi",
                "size": "1MB",
                "server": "Server2",
            },
            {
                "title": "Book Two v4",
                "author": "Test Author",
                "format": "epub",
                "size": "3MB",
                "server": "Server1",
            },
            {
                "title": "Book Three",
                "author": "Test Author",
                "format": "pdf",
                "size": "1.5MB",
                "server": "Server3",
            },
        ]

        results = self.session.search_author_level("Test Author")

        # Should return 3 unique books (best version of each)
        assert len(results) == 3

        # Should select v5 version of Book One
        book_one = next(r for r in results if "book one" in r["title"].lower())
        assert "v5" in book_one["title"]

    @patch.object(IRCSession, "search_books")
    def test_search_title_level(self, mock_search):
        """Test title-level search functionality."""
        # Mock search results from different servers
        mock_search.return_value = [
            {
                "title": "Great Book v5",
                "author": "Test Author",
                "format": "epub",
                "size": "2MB",
                "server": "Server1",
            },
            {
                "title": "Great Book v3",
                "author": "Test Author",
                "format": "mobi",
                "size": "1MB",
                "server": "Server2",
            },
            {
                "title": "Great Book v5",
                "author": "Test Author",
                "format": "epub",
                "size": "2.5MB",
                "server": "Server3",
            },
        ]

        results = self.session.search_title_level("Test Author", "Great Book")

        # Should return candidates from different servers
        assert len(results) >= 2  # At least 2 different servers

        # Should rank v5 versions higher
        assert "v5" in results[0]["title"]

    @patch.object(IRCSession, "download_file")
    def test_download_with_fallback(self, mock_download):
        """Test download with server fallback."""
        candidates = [
            {"title": "Book", "server": "Server1", "download_command": "!server1 book"},
            {"title": "Book", "server": "Server2", "download_command": "!server2 book"},
        ]

        # First download fails, second succeeds
        mock_download.side_effect = [
            {"success": False, "error": "Server timeout"},
            {"success": True, "file_path": "/path/to/book.epub"},
        ]

        result = self.session.download_with_fallback(candidates, timeout_minutes=1)

        assert result["success"] == True
        assert result["attempt_number"] == 2
        assert result["total_attempts"] == 2

    @patch.object(IRCSession, "search_author_level")
    @patch.object(IRCSession, "search_title_level")
    @patch.object(IRCSession, "download_with_fallback")
    def test_smart_search_and_download_author_search(
        self, mock_download, mock_title_search, mock_author_search
    ):
        """Test smart search for author-only query."""
        mock_author_search.return_value = [
            {"title": "Book One", "author": "Test Author"},
            {"title": "Book Two", "author": "Test Author"},
        ]

        result = self.session.smart_search_and_download("Test Author")

        assert result["success"] == True
        assert result["search_type"] == "author_level"
        assert len(result["unique_books"]) == 2
        mock_author_search.assert_called_once()
        mock_title_search.assert_not_called()
        mock_download.assert_not_called()

    @patch.object(IRCSession, "search_title_level")
    @patch.object(IRCSession, "download_with_fallback")
    def test_smart_search_and_download_title_search(
        self, mock_download, mock_title_search
    ):
        """Test smart search for specific title query."""
        mock_title_search.return_value = [
            {
                "title": "Specific Book",
                "server": "Server1",
                "download_command": "!server1 book",
            },
            {
                "title": "Specific Book",
                "server": "Server2",
                "download_command": "!server2 book",
            },
        ]

        mock_download.return_value = {
            "success": True,
            "file_path": "/path/to/book.epub",
        }

        result = self.session.smart_search_and_download("Test Author", "Specific Book")

        assert result["success"] == True
        assert result["search_type"] == "title_level"
        mock_title_search.assert_called_once_with(
            "Test Author", "Specific Book", max_results=10, timeout_minutes=3
        )
        mock_download.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
