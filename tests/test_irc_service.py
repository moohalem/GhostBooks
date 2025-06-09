#!/usr/bin/env python3
"""
Test suite for IRC service functionality
"""

import os
import sys
import tempfile
import zipfile
from unittest.mock import patch

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestIRCService:
    """Test class for IRC service functionality."""

    def test_irc_session_initialization(self):
        """Test IRC session initialization with openbooks patterns."""
        from app.services.irc import IRCSession

        session = IRCSession(
            server="irc.irchighway.net",
            port=6697,
            channel="#ebooks",
            enable_tls=True,
            search_bot="search",
            user_agent="Calibre Monitor v1.0",
        )

        assert session.server == "irc.irchighway.net"
        assert session.port == 6697
        assert session.channel == "#ebooks"
        assert session.enable_tls is True
        assert session.search_bot == "search"
        assert session.user_agent == "Calibre Monitor v1.0"
        assert session.rate_limit_delay == 10  # openbooks pattern
        assert session.search_parser is not None

    def test_nickname_generation(self):
        """Test random nickname generation."""
        from app.services.irc import IRCSession

        session1 = IRCSession()
        session2 = IRCSession()

        # Nicknames should be different
        assert session1.nickname != session2.nickname

        # Nicknames should follow pattern
        assert len(session1.nickname) <= 16  # IRC limit
        assert session1.nickname.replace("_", "").replace("-", "").isalnum()

    def test_status_tracking(self):
        """Test thread-safe status tracking."""
        from app.services.irc import IRCSession

        session = IRCSession()

        initial_status = session.get_status()
        assert initial_status["connected"] is False
        assert initial_status["joined_channel"] is False
        assert initial_status["total_searches"] == 0
        assert initial_status["total_downloads"] == 0

        # Test status update
        session._update_status({"connected": True})
        updated_status = session.get_status()
        assert updated_status["connected"] is True
        assert "last_activity" in updated_status

    def test_epub_only_zip_extraction(self):
        """Test ZIP extraction filtering for EPUB files only."""
        from app.services.irc import IRCSession

        session = IRCSession()

        # Create test zip file with mixed content
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_zip:
            with zipfile.ZipFile(tmp_zip.name, "w") as zf:
                # Add EPUB files
                zf.writestr("book1.epub", b"fake epub content 1")
                zf.writestr(
                    "book2.EPUB", b"fake epub content 2"
                )  # Test case insensitive
                # Add non-EPUB files (should be ignored)
                zf.writestr("book.pdf", b"fake pdf content")
                zf.writestr("book.mobi", b"fake mobi content")
                zf.writestr("readme.txt", b"readme content")
                zf.writestr("cover.jpg", b"cover image")

            try:
                # Test extraction
                extracted_files = session._extract_zip(tmp_zip.name)

                # Should only extract EPUB files
                assert len(extracted_files) == 2
                assert any("book1.epub" in f for f in extracted_files)
                assert any("book2.EPUB" in f for f in extracted_files)

                # Verify files were actually extracted
                for file_path in extracted_files:
                    assert os.path.exists(file_path)

            finally:
                # Cleanup
                os.unlink(tmp_zip.name)
                extract_dir = tmp_zip.name.replace(".zip", "_extracted")
                if os.path.exists(extract_dir):
                    import shutil

                    shutil.rmtree(extract_dir)

    def test_epub_only_zip_extraction_no_epubs(self):
        """Test ZIP extraction when no EPUB files are present."""
        from app.services.irc import IRCSession

        session = IRCSession()

        # Create test zip file with no EPUB content
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_zip:
            with zipfile.ZipFile(tmp_zip.name, "w") as zf:
                # Add only non-EPUB files
                zf.writestr("book.pdf", b"fake pdf content")
                zf.writestr("book.mobi", b"fake mobi content")
                zf.writestr("readme.txt", b"readme content")

            try:
                # Test extraction
                extracted_files = session._extract_zip(tmp_zip.name)

                # Should return empty list when no EPUB files
                assert len(extracted_files) == 0

            finally:
                # Cleanup
                os.unlink(tmp_zip.name)

    @patch("app.services.irc.IRCSession.search_books")
    def test_search_epub_only_method(self, mock_search_books):
        """Test EPUB-only search method."""
        from app.services.irc import IRCSession

        # Mock mixed search results
        mock_search_books.return_value = [
            {
                "server": "test_server",
                "author": "Test Author",
                "title": "Test Book EPUB",
                "format": "epub",
                "size": "1.2MB",
                "download_command": "!test epub",
                "raw_line": "test epub line",
            },
            {
                "server": "test_server",
                "author": "Test Author",
                "title": "Test Book PDF",
                "format": "pdf",
                "size": "2.5MB",
                "download_command": "!test pdf",
                "raw_line": "test pdf line",
            },
            {
                "server": "test_server",
                "author": "Test Author",
                "title": "Test Book MOBI",
                "format": "mobi",
                "size": "1.8MB",
                "download_command": "!test mobi",
                "raw_line": "test mobi line",
            },
        ]

        session = IRCSession()
        session.connected = True

        # Test EPUB-only search
        results = session.search_epub_only("test query", 50)

        # Should only return EPUB results
        assert len(results) == 1
        assert results[0]["format"] == "epub"
        assert results[0]["title"] == "Test Book EPUB"

        # Verify search_books was called with correct parameters
        mock_search_books.assert_called_once_with("test query", None, 50)

    @patch("app.services.irc.IRCSession.download_file")
    def test_download_epub_only_epub_file(self, mock_download_file):
        """Test EPUB-only download with actual EPUB file."""
        from app.services.irc import IRCSession

        # Mock successful download of EPUB file
        mock_download_file.return_value = {
            "success": True,
            "file_path": "/tmp/test_book.epub",
            "file_size": 1024000,
            "extracted_files": [],
        }

        session = IRCSession()
        session.connected = True

        result = session.download_epub_only("!test download")

        assert result["success"] is True
        assert result["file_path"] == "/tmp/test_book.epub"
        mock_download_file.assert_called_once_with("!test download", None)

    @patch("app.services.irc.IRCSession.download_file")
    @patch("app.services.irc.IRCSession._extract_zip")
    def test_download_epub_only_zip_file(self, mock_extract_zip, mock_download_file):
        """Test EPUB-only download with ZIP file containing EPUBs."""
        from app.services.irc import IRCSession

        # Mock successful download of ZIP file
        mock_download_file.return_value = {
            "success": True,
            "file_path": "/tmp/test_books.zip",
            "file_size": 2048000,
            "extracted_files": [],
        }

        # Mock ZIP extraction returning EPUB files
        mock_extract_zip.return_value = [
            "/tmp/test_books_extracted/book1.epub",
            "/tmp/test_books_extracted/book2.epub",
        ]

        session = IRCSession()
        session.connected = True

        result = session.download_epub_only("!test download zip")

        assert result["success"] is True
        assert result["file_path"] == "/tmp/test_books.zip"
        assert "extracted_files" in result
        assert "epub_count" in result
        assert result["epub_count"] == 2
        assert len(result["extracted_files"]) == 2

        mock_download_file.assert_called_once_with("!test download zip", None)
        mock_extract_zip.assert_called_once_with("/tmp/test_books.zip")

    def test_connection_info(self):
        """Test connection information retrieval."""
        from app.services.irc import IRCSession

        session = IRCSession(
            server="test.server.com", port=6667, channel="#test", search_bot="testbot"
        )

        info = session.get_connection_info()

        assert info["server"] == "test.server.com"
        assert info["port"] == 6667
        assert info["channel"] == "#test"
        assert info["search_bot"] == "testbot"
        assert "session_id" in info
        assert "nickname" in info
        assert info["connected"] is False
        assert info["is_healthy"] is False

    def test_rate_limiting(self):
        """Test rate limiting enforcement."""
        import time

        from app.services.irc import IRCSession

        session = IRCSession()
        session.rate_limit_delay = 1  # Short delay for testing

        # First command should go through immediately
        start_time = time.time()
        session._enforce_rate_limit()
        elapsed = time.time() - start_time
        assert elapsed < 0.1  # Should be immediate

        # Second command should be delayed
        start_time = time.time()
        session._enforce_rate_limit()
        elapsed = time.time() - start_time
        assert elapsed >= 0.9  # Should wait for rate limit
