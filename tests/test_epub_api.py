#!/usr/bin/env python3
"""
Test suite for EPUB-only API endpoints
"""

import os
import sys
from unittest.mock import patch

import pytest

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def client():
    """Create test client."""
    from app import create_app
    from config import get_config

    config = get_config("development")
    app = create_app(config)
    app.config["TESTING"] = True

    with app.test_client() as client:
        with app.app_context():
            yield client


class TestEpubOnlyAPI:
    """Test class for EPUB-only API endpoints."""

    @patch("app.routes.api.search_epub_only")
    def test_search_epub_only_endpoint_success(self, mock_search, client):
        """Test successful EPUB-only search endpoint."""
        # Mock successful search
        mock_search.return_value = {
            "success": True,
            "results": [
                {
                    "server": "test_server",
                    "author": "Test Author",
                    "title": "Test Book",
                    "format": "epub",
                    "size": "1.2MB",
                    "download_command": "!test download",
                    "raw_line": "test line",
                }
            ],
            "epub_count": 1,
            "session_status": {"connected": True},
        }

        response = client.post(
            "/api/irc/search/epub",
            json={"session_id": "test_session", "search_query": "Test Author"},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["epub_count"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["format"] == "epub"

        mock_search.assert_called_once_with("test_session", "Test Author", 50)

    def test_search_epub_only_endpoint_missing_params(self, client):
        """Test EPUB-only search endpoint with missing parameters."""
        # Missing session_id
        response = client.post(
            "/api/irc/search/epub", json={"search_query": "Test Author"}
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "Session ID and search query are required" in data["error"]

        # Missing search_query
        response = client.post(
            "/api/irc/search/epub", json={"session_id": "test_session"}
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "Session ID and search query are required" in data["error"]

    @patch("app.routes.api.search_epub_only")
    def test_search_epub_only_endpoint_with_author_param(self, mock_search, client):
        """Test EPUB-only search endpoint with author parameter (backward compatibility)."""
        mock_search.return_value = {
            "success": True,
            "results": [],
            "epub_count": 0,
            "session_status": {"connected": True},
        }

        response = client.post(
            "/api/irc/search/epub",
            json={
                "session_id": "test_session",
                "author": "Test Author",  # Use author param instead of search_query
            },
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        mock_search.assert_called_once_with("test_session", "Test Author", 50)

    @patch("app.routes.api.download_epub_only")
    def test_download_epub_only_endpoint_success(self, mock_download, client):
        """Test successful EPUB-only download endpoint."""
        # Mock successful download
        mock_download.return_value = {
            "success": True,
            "file_path": "/tmp/test_book.epub",
            "file_size": 1024000,
        }

        response = client.post(
            "/api/irc/download/epub",
            json={"session_id": "test_session", "download_command": "!test download"},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["file_path"] == "/tmp/test_book.epub"

        mock_download.assert_called_once_with("test_session", "!test download", None)

    @patch("app.routes.api.download_epub_only")
    def test_download_epub_only_endpoint_with_output_dir(self, mock_download, client):
        """Test EPUB-only download endpoint with output directory."""
        mock_download.return_value = {
            "success": True,
            "file_path": "/custom/path/test_book.epub",
            "file_size": 1024000,
        }

        response = client.post(
            "/api/irc/download/epub",
            json={
                "session_id": "test_session",
                "download_command": "!test download",
                "output_dir": "/custom/path",
            },
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

        mock_download.assert_called_once_with(
            "test_session", "!test download", "/custom/path"
        )

    def test_download_epub_only_endpoint_missing_params(self, client):
        """Test EPUB-only download endpoint with missing parameters."""
        # Missing session_id
        response = client.post(
            "/api/irc/download/epub", json={"download_command": "!test download"}
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "Session ID and download command are required" in data["error"]

        # Missing download_command
        response = client.post(
            "/api/irc/download/epub", json={"session_id": "test_session"}
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "Session ID and download command are required" in data["error"]

    @patch("app.routes.api.download_epub_only")
    def test_download_epub_only_endpoint_zip_extraction(self, mock_download, client):
        """Test EPUB-only download endpoint with ZIP file extraction."""
        # Mock successful ZIP download with EPUB extraction
        mock_download.return_value = {
            "success": True,
            "file_path": "/tmp/test_books.zip",
            "file_size": 2048000,
            "extracted_files": [
                "/tmp/test_books_extracted/book1.epub",
                "/tmp/test_books_extracted/book2.epub",
            ],
            "epub_count": 2,
        }

        response = client.post(
            "/api/irc/download/epub",
            json={
                "session_id": "test_session",
                "download_command": "!test download zip",
            },
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["file_path"] == "/tmp/test_books.zip"
        assert "extracted_files" in data
        assert data["epub_count"] == 2
        assert len(data["extracted_files"]) == 2

    @patch("app.routes.api.search_epub_only")
    def test_search_epub_only_endpoint_error_handling(self, mock_search, client):
        """Test EPUB-only search endpoint error handling."""
        # Mock service error
        mock_search.return_value = {"success": False, "error": "Session not found"}

        response = client.post(
            "/api/irc/search/epub",
            json={"session_id": "invalid_session", "search_query": "Test Author"},
        )

        assert (
            response.status_code == 200
        )  # Service errors return 200 with error in body
        data = response.get_json()
        assert data["success"] is False
        assert "Session not found" in data["error"]

    @patch("app.routes.api.download_epub_only")
    def test_download_epub_only_endpoint_error_handling(self, mock_download, client):
        """Test EPUB-only download endpoint error handling."""
        # Mock service error
        mock_download.return_value = {
            "success": False,
            "error": "No EPUB files found in archive",
        }

        response = client.post(
            "/api/irc/download/epub",
            json={
                "session_id": "test_session",
                "download_command": "!test download non-epub",
            },
        )

        assert (
            response.status_code == 200
        )  # Service errors return 200 with error in body
        data = response.get_json()
        assert data["success"] is False
        assert "No EPUB files found in archive" in data["error"]
