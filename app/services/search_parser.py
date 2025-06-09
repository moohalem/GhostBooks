#!/usr/bin/env python3
"""
IRC Search Result Parser
Enhanced parser for IRC bot responses, based on openbooks project patterns
"""

import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple


@dataclass
class BookDetail:
    """Container for parsed book information."""

    server: str
    author: str
    title: str
    format: str
    size: str
    full_command: str
    raw_line: str


@dataclass
class ParseError:
    """Container for parsing errors."""

    line: str
    error: str
    timestamp: str


class SearchResultParser:
    """Parses IRC search results into structured book data."""

    # Common ebook file extensions
    FILE_TYPES = [
        "epub",
        "mobi",
        "azw3",
        "html",
        "rtf",
        "pdf",
        "cdr",
        "lit",
        "cbr",
        "doc",
        "htm",
        "jpg",
        "txt",
        "rar",
        "zip",
    ]

    # Archive extensions (should be last)
    ARCHIVE_EXTENSIONS = ["rar", "zip"]

    def __init__(self):
        self.results: List[BookDetail] = []
        self.errors: List[ParseError] = []

    def parse_search_results(
        self, text_lines: List[str]
    ) -> Tuple[List[BookDetail], List[ParseError]]:
        """
        Parse multiple search result lines.

        Args:
            text_lines: List of IRC response lines

        Returns:
            Tuple of (BookDetail list, ParseError list)
        """
        results = []
        errors = []

        for line in text_lines:
            line = line.strip()
            if not line:
                continue

            try:
                book_detail = self.parse_line(line)
                if book_detail:
                    results.append(book_detail)
            except Exception as e:
                errors.append(
                    ParseError(
                        line=line, error=str(e), timestamp=datetime.now().isoformat()
                    )
                )

        return results, errors

    def parse_line(self, line: str) -> Optional[BookDetail]:
        """
        Parse a single search result line.

        Args:
            line: Single IRC message line

        Returns:
            BookDetail object or None if parsing fails
        """
        # Skip non-book lines
        if not self._is_book_line(line):
            return None

        # Try different parsing strategies
        parsers = [
            self._parse_info_format,  # Lines with ::INFO::
            self._parse_standard_format,  # Standard bot format
            self._parse_simple_format,  # Simple format fallback
        ]

        for parser in parsers:
            try:
                result = parser(line)
                if result:
                    return result
            except Exception:
                continue

        return None

    def _is_book_line(self, line: str) -> bool:
        """Check if line contains a book result."""
        # Must start with ! (bot prefix) and contain a file extension
        if not line.startswith("!"):
            return False

        line_lower = line.lower()
        return any(f".{ext}" in line_lower for ext in self.FILE_TYPES)

    def _parse_info_format(self, line: str) -> Optional[BookDetail]:
        """
        Parse lines with ::INFO:: format.
        Example: !Ook F Scott Fitzgerald - The Great Gatsby.epub  ::INFO:: 332.7KB
        """
        if "::INFO::" not in line:
            return None

        # Split on ::INFO::
        main_part, info_part = line.split("::INFO::", 1)
        main_part = main_part.strip()
        size = info_part.strip()

        # Extract server (first word after !)
        parts = main_part.split()
        if len(parts) < 2:
            return None

        server = parts[0][1:]  # Remove ! prefix
        content = " ".join(parts[1:])

        # Parse author, title, and format
        author, title, file_format = self._extract_author_title_format(content)

        return BookDetail(
            server=server,
            author=author,
            title=title,
            format=file_format,
            size=size,
            full_command=main_part,
            raw_line=line,
        )

    def _parse_standard_format(self, line: str) -> Optional[BookDetail]:
        """
        Parse standard bot format without ::INFO::.
        Example: !Horla F Scott Fitzgerald - The Great Gatsby (retail) (epub).epub
        """
        parts = line.split()
        if len(parts) < 2:
            return None

        server = parts[0][1:]  # Remove ! prefix
        content = " ".join(parts[1:])

        # Extract file info
        author, title, file_format = self._extract_author_title_format(content)

        return BookDetail(
            server=server,
            author=author,
            title=title,
            format=file_format,
            size="Unknown",
            full_command=line.strip(),
            raw_line=line,
        )

    def _parse_simple_format(self, line: str) -> Optional[BookDetail]:
        """
        Simple fallback parser for unusual formats.
        """
        parts = line.split()
        if len(parts) < 2:
            return None

        server = parts[0][1:]  # Remove ! prefix
        content = " ".join(parts[1:])

        # Find file extension
        file_format = "unknown"
        for ext in self.FILE_TYPES:
            if f".{ext}" in content.lower():
                file_format = ext
                break

        return BookDetail(
            server=server,
            author="Unknown",
            title=content,
            format=file_format,
            size="Unknown",
            full_command=line.strip(),
            raw_line=line,
        )

    def _extract_author_title_format(self, content: str) -> Tuple[str, str, str]:
        """
        Extract author, title, and format from content string.

        Args:
            content: The main content part of the line

        Returns:
            Tuple of (author, title, format)
        """
        # Find file extension first
        file_format = "unknown"
        title_end_pos = len(content)

        for ext in self.FILE_TYPES:
            pattern = f"\\.{ext}"
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                file_format = ext
                title_end_pos = match.start()

                # If it's an archive, look for actual format in content
                if ext in self.ARCHIVE_EXTENSIONS:
                    for inner_ext in self.FILE_TYPES[:-2]:  # Exclude archives
                        if inner_ext in content.lower():
                            file_format = inner_ext
                            break
                break

        # Extract title part (before file extension)
        title_content = content[:title_end_pos].strip()

        # Look for author-title separator
        if " - " in title_content:
            parts = title_content.split(" - ", 1)
            author = parts[0].strip()
            title = parts[1].strip()
        else:
            # No clear separator, try to guess
            words = title_content.split()
            if len(words) > 2:
                # Assume first 1-2 words are author
                author = " ".join(words[:2])
                title = " ".join(words[2:])
            else:
                author = "Unknown"
                title = title_content

        # Clean up parenthetical information from title
        title = re.sub(r"\s*\([^)]*\)\s*", " ", title).strip()

        return author, title, file_format

    def filter_results(
        self,
        results: List[BookDetail],
        author_filter: Optional[str] = None,
        format_filter: Optional[str] = None,
        min_quality: bool = True,
        epub_only: bool = False,
    ) -> List[BookDetail]:
        """
        Filter and sort search results.

        Args:
            results: List of BookDetail objects
            author_filter: Filter by author name
            format_filter: Filter by file format
            min_quality: If True, prefer non-archive formats
            epub_only: If True, only return EPUB files (openbooks pattern)

        Returns:
            Filtered and sorted list
        """
        if results is None:
            return []

        filtered = results.copy()

        # EPUB-only filter (openbooks alignment)
        if epub_only:
            filtered = [r for r in filtered if r.format.lower() == "epub"]
            print(f"[PARSER] EPUB-only filter: {len(filtered)} results remaining")

        # Author filter
        if author_filter:
            author_lower = author_filter.lower()
            filtered = [
                r
                for r in filtered
                if author_lower in r.author.lower() or author_lower in r.title.lower()
            ]

        # Format filter
        if format_filter:
            format_lower = format_filter.lower()
            filtered = [r for r in filtered if r.format.lower() == format_lower]

        # Quality filter - prefer non-archive formats
        if min_quality and not epub_only:  # Skip if epub_only already applied
            # Separate archives and non-archives
            non_archives = [
                r for r in filtered if r.format not in self.ARCHIVE_EXTENSIONS
            ]
            archives = [r for r in filtered if r.format in self.ARCHIVE_EXTENSIONS]

            # Prefer non-archives, but include archives if no alternatives
            if non_archives:
                filtered = non_archives
            else:
                filtered = archives

        # Sort by server and format preference (epub gets highest priority)
        format_priority = {"epub": 1, "mobi": 2, "azw3": 3, "pdf": 4, "txt": 5}

        def sort_key(book: BookDetail) -> Tuple[int, str, str]:
            format_score = format_priority.get(book.format, 6)
            return (format_score, book.author.lower(), book.title.lower())

        filtered.sort(key=sort_key)

        return filtered


def test_parser():
    """Test the search result parser with sample data."""
    sample_lines = [
        "!Ook F Scott Fitzgerald - The Great Gatsby.epub  ::INFO:: 332.7KB",
        "!MusicWench F Scott Fitzgerald - The Great Gatsby.mobi  ::INFO:: 376.6KB",
        "!Oatmeal F. Scott Fitzgerald - The Great Gatsby (V1.5 RTF).rar ::INFO:: 272.23KB",
        "!Horla F Scott Fitzgerald - The Great Gatsby (retail) (epub).epub",
        "!JimBob420 F. Scott Fitzgerald - The Great Gatsby (V1.5 RTF).rar ::INFO:: 272.23KB",
        "!DeathCookie Isaac_Asimov_Foundation_01_Foundation.epub.rar  ::INFO:: 530.0KB",
        "Non-book line that should be ignored",
        "!InvalidLine without proper format",
    ]

    parser = SearchResultParser()
    results, errors = parser.parse_search_results(sample_lines)

    print(f"Parsed {len(results)} books and {len(errors)} errors")
    print("\nBooks found:")
    for book in results:
        print(f"  {book.author} - {book.title} ({book.format}, {book.size})")

    print("\nErrors:")
    for error in errors:
        print(f"  {error.error}: {error.line}")

    # Test filtering
    print("\nFiltered for 'Fitzgerald':")
    filtered = parser.filter_results(results, author_filter="Fitzgerald")
    for book in filtered:
        print(f"  {book.author} - {book.title} ({book.format})")


if __name__ == "__main__":
    test_parser()
