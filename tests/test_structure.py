#!/usr/bin/env python3
"""
Test suite to verify the reorganized project structure and IRC functionality
"""

import os
import sys
from unittest.mock import Mock, patch

import pytest

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestProjectStructure:
    """Test class for project structure verification."""

    def test_config_import(self):
        """Test that configuration can be imported and loaded."""
        from config import get_config

        config = get_config("development")
        assert config is not None
        assert "SECRET_KEY" in config or config.get("DEBUG") is not None

    def test_app_factory_import(self):
        """Test that Flask app factory works correctly."""
        from app import create_app
        from config import get_config

        config = get_config("development")
        app = create_app(config)
        assert app is not None
        assert app.config.get("SECRET_KEY") is not None

    def test_services_import(self):
        """Test that all services can be imported."""
        from app.services.database import initialize_database
        from app.services.irc import create_irc_session
        from app.services.openlibrary import get_author_key
        from app.services.search_parser import SearchResultParser

        # Test that classes can be instantiated
        search_parser = SearchResultParser()
        assert search_parser is not None

        # Test that functions exist
        assert callable(initialize_database)
        assert callable(create_irc_session)
        assert callable(get_author_key)

    def test_routes_import(self):
        """Test that route blueprints can be imported."""
        from app.routes import api_bp, main_bp

        assert api_bp.name == "api"
        assert main_bp.name == "main"

    def test_irc_session_creation(self):
        """Test that IRC session can be created with proper configuration."""
        from app.services.irc import IRCSession

        session = IRCSession(
            server="irc.irchighway.net", port=6697, channel="#ebooks", enable_tls=True
        )

        assert session is not None
        assert session.server == "irc.irchighway.net"
        assert session.port == 6697
        assert session.channel == "#ebooks"
        assert session.enable_tls is True
        assert session.search_parser is not None

    def test_search_parser_epub_filtering(self):
        """Test that search parser can filter EPUB files correctly."""
        from app.services.search_parser import BookDetail, SearchResultParser

        parser = SearchResultParser()

        # Create mock book objects
        epub_book = BookDetail(
            server="test_server",
            author="Test Author",
            title="Test Book",
            format="epub",
            size="1.2MB",
            full_command="!test download",
            raw_line="test line",
        )

        pdf_book = BookDetail(
            server="test_server",
            author="Test Author",
            title="Test Book PDF",
            format="pdf",
            size="2.5MB",
            full_command="!test download pdf",
            raw_line="test pdf line",
        )

        books = [epub_book, pdf_book]

        # Test EPUB-only filtering
        epub_only = parser.filter_results(books, epub_only=True)
        assert len(epub_only) == 1
        assert epub_only[0].format == "epub"

    @patch("app.services.irc.IRCSession.connect")
    def test_irc_epub_only_search(self, mock_connect):
        """Test EPUB-only search functionality."""
        from app.services.irc import IRCSession

        mock_connect.return_value = True

        session = IRCSession()
        session.connected = True
        session.socket = Mock()

        # Mock search_books to return mixed results
        with patch.object(session, "search_books") as mock_search:
            mock_search.return_value = [
                {
                    "server": "test",
                    "author": "Test Author",
                    "title": "Test Book",
                    "format": "epub",
                    "size": "1.2MB",
                    "download_command": "!test",
                    "raw_line": "test",
                },
                {
                    "server": "test",
                    "author": "Test Author",
                    "title": "Test Book PDF",
                    "format": "pdf",
                    "size": "2.5MB",
                    "download_command": "!test pdf",
                    "raw_line": "test pdf",
                },
            ]

            # Test EPUB-only search
            results = session.search_epub_only("test query")

            # Should only return EPUB results
            assert len(results) == 1
            assert results[0]["format"] == "epub"

    def test_zip_extraction_epub_filtering(self):
        """Test that ZIP extraction only processes EPUB files."""
        import tempfile
        import zipfile

        from app.services.irc import IRCSession

        session = IRCSession()

        # Create a test zip file with mixed content
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_zip:
            with zipfile.ZipFile(tmp_zip.name, "w") as zf:
                # Add EPUB file
                zf.writestr("test_book.epub", b"fake epub content")
                # Add non-EPUB file
                zf.writestr("test_book.pdf", b"fake pdf content")
                zf.writestr("readme.txt", b"readme content")

            # Test extraction
            extracted_files = session._extract_zip(tmp_zip.name)

            # Should only extract EPUB files
            assert len(extracted_files) == 1
            assert extracted_files[0].endswith("test_book.epub")

            # Cleanup
            os.unlink(tmp_zip.name)
            if os.path.exists(tmp_zip.name.replace(".zip", "_extracted")):
                import shutil

                shutil.rmtree(tmp_zip.name.replace(".zip", "_extracted"))


if __name__ == "__main__":
    # Run tests when executed directly
    pytest.main([__file__, "-v"])
    test_imports()
