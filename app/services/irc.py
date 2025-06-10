#!/usr/bin/env python3
"""
Enhanced IRC service for Calibre Library Monitor
Handles IRC connections, book searches, and file downloads with DCC protocol support
Based on openbooks project implementation patterns
"""

import os
import random
import re
import socket
import ssl  # Add SSL support for TLS connections
import string
import threading
import time
import zipfile
from datetime import datetime
from typing import Dict, List, Optional

from .dcc import DCCHandler
from .search_parser import SearchResultParser


class IRCSession:
    """Manages a persistent IRC session for downloading multiple files."""

    def __init__(
        self,
        server: str = "irc.irchighway.net",
        port: int = 6697,  # Use TLS port like openbooks
        channel: str = "#ebooks",
        enable_tls: bool = True,  # Enable TLS by default like openbooks
        user_agent: str = "Calibre Monitor v1.0",  # Version for CTCP responses
        search_bot: str = "search",  # Configurable search bot like openbooks
        connect_timeout: int = 30,  # Connection timeout
        response_timeout: int = 60,  # Response timeout
    ):
        self.server = server
        self.port = port
        self.channel = channel
        self.enable_tls = enable_tls
        self.user_agent = user_agent
        self.search_bot = search_bot
        self.connect_timeout = connect_timeout
        self.response_timeout = response_timeout
        self.socket = None
        self.nickname = self._generate_random_nickname()
        self.real_name = self.nickname  # Use same as nickname
        self.connected = False
        self.joined_channel = False
        self.last_command_time = 0
        self.rate_limit_delay = 10  # Match openbooks minimum 10 seconds
        self.download_dir = "downloads"
        self.session_id = f"irc_session_{int(time.time())}"

        # Initialize parsers
        self.search_parser = SearchResultParser()

        # Thread-safe status tracking
        self._status_lock = threading.RLock()
        self._status = {
            "connected": False,
            "joined_channel": False,
            "last_activity": None,
            "total_searches": 0,
            "total_downloads": 0,
            "errors": [],
            "nickname": self.nickname,
            "server": self.server,
            "channel": self.channel,
            "tls_enabled": self.enable_tls,
        }

        # Response handling
        self._response_buffer = []
        self._response_lock = threading.Lock()
        self._listener_thread = None
        self._running = False

    def _generate_random_nickname(self) -> str:
        """Generate a random nickname for IRC connection."""
        adjectives = [
            "Dark",
            "Web",
            "Quick",
            "Silent",
            "Swift",
            "Digital",
            "Cyber",
            "Net",
        ]
        nouns = ["Horse", "Wolf", "Eagle", "Lion", "Hawk", "Fox", "Bear", "Tiger"]
        numbers = random.randint(100, 999)

        base = f"{random.choice(adjectives)}{random.choice(nouns)}{numbers}"
        # Add some random characters if needed
        if random.choice([True, False]):
            base += random.choice(["_", ""]) + "".join(
                random.choices(string.ascii_lowercase, k=2)
            )

        return base[:16]  # IRC nickname length limit

    def _update_status(self, updates: Dict) -> None:
        """Thread-safe status update."""
        with self._status_lock:
            self._status.update(updates)
            self._status["last_activity"] = datetime.now().isoformat()

    def get_status(self) -> Dict:
        """Get current session status."""
        with self._status_lock:
            return self._status.copy()

    def connect(self) -> bool:
        """Connect to IRC server and join channel with TLS support and retry logic."""
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Create socket with optional TLS support (like openbooks)
                if self.enable_tls:
                    context = ssl.create_default_context()
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                    raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.socket = context.wrap_socket(raw_socket)
                    print(
                        f"[IRC] Connecting to {self.server}:{self.port} with TLS as {self.nickname}..."
                    )
                else:
                    self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    print(
                        f"[IRC] Connecting to {self.server}:{self.port} as {self.nickname}..."
                    )

                self.socket.settimeout(self.connect_timeout)
                self.socket.connect((self.server, self.port))

                # Send connection commands (same as openbooks)
                self.socket.send(f"NICK {self.nickname}\r\n".encode())
                self.socket.send(
                    f"USER {self.nickname} 0 * :{self.real_name}\r\n".encode()
                )

                # Wait for connection confirmation with improved error handling
                connected = False
                nick_retries = 0
                max_nick_retries = 3

                while not connected and nick_retries < max_nick_retries:
                    try:
                        resp = self.socket.recv(2048).decode(errors="ignore")
                        print(f"[IRC] {resp.strip()}")

                        # Handle different response codes
                        if "004" in resp or "Welcome" in resp:
                            connected = True
                        elif "433" in resp or "Nickname is already in use" in resp:
                            # Nickname in use - generate new one
                            old_nick = self.nickname
                            self.nickname = self._generate_random_nickname()
                            print(
                                f"[IRC] Nickname {old_nick} in use, trying: {self.nickname}"
                            )
                            self.socket.send(f"NICK {self.nickname}\r\n".encode())
                            nick_retries += 1
                        elif "ERROR" in resp or "Closing Link" in resp:
                            raise Exception(f"IRC connection error: {resp}")
                        elif "PING" in resp:
                            # Handle PING during connection
                            pong_response = resp.replace("PING", "PONG")
                            self.socket.send(pong_response.encode())

                    except socket.timeout:
                        nick_retries += 1
                        if nick_retries >= max_nick_retries:
                            raise Exception("Connection timeout during registration")

                if not connected:
                    raise Exception("Failed to register nickname after maximum retries")

                # Wait before joining (like openbooks does)
                time.sleep(2)

                # Join channel
                self.socket.send(f"JOIN {self.channel}\r\n".encode())

                # Wait for join confirmation
                join_confirmed = False
                join_timeout = 10
                join_start = time.time()

                while not join_confirmed and (time.time() - join_start) < join_timeout:
                    try:
                        resp = self.socket.recv(2048).decode(errors="ignore")
                        if resp:
                            print(f"[IRC] {resp.strip()}")
                            if (
                                f"JOIN {self.channel}" in resp or "366" in resp
                            ):  # End of NAMES list
                                join_confirmed = True
                            elif "PING" in resp:
                                pong_response = resp.replace("PING", "PONG")
                                self.socket.send(pong_response.encode())
                    except socket.timeout:
                        continue

                if not join_confirmed:
                    print(
                        f"[IRC] Warning: Join confirmation not received for {self.channel}"
                    )
                else:
                    print(f"[IRC] Successfully joined channel {self.channel}")

                self.connected = True
                self.joined_channel = True
                self._update_status(
                    {
                        "connected": True,
                        "joined_channel": True,
                        "nickname": self.nickname,
                        "tls_enabled": self.enable_tls,
                    }
                )

                # Start background listener for responses
                self._start_response_listener()

                print(f"[IRC] Session {self.session_id} connected successfully")
                return True

            except Exception as e:
                error_msg = f"Connection attempt {retry_count + 1} failed: {str(e)}"
                print(f"[IRC] {error_msg}")

                if self.socket:
                    try:
                        self.socket.close()
                    except Exception:
                        pass
                    self.socket = None

                retry_count += 1
                if retry_count < max_retries:
                    sleep_time = 5 * retry_count  # Progressive backoff
                    print(f"[IRC] Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)
                else:
                    self._update_status(
                        {
                            "connected": False,
                            "errors": [
                                f"Failed to connect after {max_retries} attempts: {str(e)}"
                            ],
                        }
                    )
                    return False

        return False

    def _start_response_listener(self) -> None:
        """Start background thread to listen for IRC responses."""

        def listener():
            while self.connected and self.socket:
                try:
                    self.socket.settimeout(1)
                    resp = self.socket.recv(4096).decode(errors="ignore")
                    if resp:
                        # Handle PING/PONG to stay connected
                        if "PING" in resp:
                            pong_response = resp.replace("PING", "PONG")
                            self.socket.send(pong_response.encode())

                        # Store response for processing
                        self._process_irc_response(resp)
                        print(f"[IRC] {resp.strip()}")
                    else:
                        break
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"[IRC] Listener error: {e}")
                    break

        thread = threading.Thread(target=listener, daemon=True)
        thread.start()

    def _process_irc_response(self, response: str) -> None:
        """Process IRC responses for search results, DCC offers, and CTCP requests."""
        lines = response.strip().split("\n")

        for line in lines:
            line = line.strip()

            # Handle CTCP VERSION requests (important for IRC Highway allow-listing)
            if "\x01VERSION\x01" in line:
                self._handle_version_request(line)

            # Check for DCC SEND offers
            if DCCHandler.is_dcc_message(line):
                self._handle_dcc_offer(line)

            # Store potential search results
            if self._is_potential_search_result(line):
                self._store_search_result(line)

    def _handle_version_request(self, line: str) -> None:
        """Handle CTCP VERSION requests (critical for IRC Highway allow-listing)."""
        try:
            # Extract the sender from the line format: ":sender PRIVMSG target :..."
            if line.startswith(":"):
                sender = line.split(" ")[0][1:]  # Remove the leading ":"
                if "!" in sender:
                    sender = sender.split("!")[0]  # Get nickname only

                # Send CTCP VERSION response (like openbooks)
                version_response = (
                    f"NOTICE {sender} :\x01VERSION {self.user_agent}\x01\r\n"
                )
                if self.socket:
                    self.socket.send(version_response.encode())
                    print(
                        f"[IRC] Sent CTCP VERSION response to {sender}: {self.user_agent}"
                    )
        except Exception as e:
            print(f"[IRC] Error handling VERSION request: {e}")

    def _handle_dcc_offer(self, line: str) -> None:
        """Handle incoming DCC SEND offers."""
        dcc = DCCHandler.parse_dcc_string(line)
        if dcc:
            print(f"[IRC] DCC offer received: {dcc.filename} ({dcc.size} bytes)")
            # Store DCC offer for potential download
            if not hasattr(self, "_dcc_offers"):
                self._dcc_offers = []
            self._dcc_offers.append(dcc)

    def _is_potential_search_result(self, line: str) -> bool:
        """Check if line might be a search result."""
        return line.startswith("!") and any(
            ext in line.lower()
            for ext in [".epub", ".pdf", ".mobi", ".txt", ".zip", ".rar"]
        )

    def _store_search_result(self, line: str) -> None:
        """Store potential search result."""
        if not hasattr(self, "_search_results"):
            self._search_results = []
        self._search_results.append(line)

    def _enforce_rate_limit(self) -> None:
        """Enforce rate limiting between commands."""
        current_time = time.time()
        time_since_last = current_time - self.last_command_time

        if time_since_last < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last
            print(f"[IRC] Rate limiting: waiting {sleep_time:.1f} seconds...")
            time.sleep(sleep_time)

        self.last_command_time = time.time()

    def search_books(
        self, author: str, title: Optional[str] = None, max_results: int = 50
    ) -> List[Dict]:
        """Search for books using @search command with enhanced parsing (following openbooks patterns)."""
        if not self.connected or not self.socket:
            raise Exception("Not connected to IRC")

        self._enforce_rate_limit()

        # Clear previous search results
        self._search_results = []
        self._dcc_offers = []

        # Format search command (based on openbooks patterns)
        # Use configurable search bot prefix
        if title:
            # For specific book searches, include both author and title
            search_query = f"@{self.search_bot} {author} {title}"
        else:
            # For author searches, just use author name
            search_query = f"@{self.search_bot} {author}"

        print(f"[IRC] Searching with bot '{self.search_bot}': {search_query}")

        # Send search command to the channel
        try:
            self.socket.send(f"PRIVMSG {self.channel} :{search_query}\r\n".encode())
        except Exception as e:
            raise Exception(f"Failed to send search command: {e}")

        # Wait for search results (following openbooks timeout pattern)
        print("[IRC] Waiting for search results...")
        start_time = time.time()
        timeout = 20  # Increased timeout like openbooks

        while time.time() - start_time < timeout:
            time.sleep(1)
            # Check if we've received enough results
            if (
                hasattr(self, "_search_results")
                and len(self._search_results) >= max_results
            ):
                print(
                    f"[IRC] Received {len(self._search_results)} results, stopping collection"
                )
                break

        # Parse collected results
        if hasattr(self, "_search_results") and self._search_results:
            print(f"[IRC] Processing {len(self._search_results)} raw results")

            books, parse_errors = self.search_parser.parse_search_results(
                self._search_results
            )

            # Filter results if specific criteria provided (following openbooks filtering)
            if author or title:
                original_count = len(books)
                filter_term = f"{author} {title}".strip() if title else author
                books = self.search_parser.filter_results(
                    books, author_filter=filter_term
                )
                print(f"[IRC] Filtered from {original_count} to {len(books)} results")

            # Limit results to max_results
            if len(books) > max_results:
                books = books[:max_results]
                print(f"[IRC] Limited results to {max_results}")

            # Convert to dict format for API compatibility
            results = []
            for book in books:
                results.append(
                    {
                        "server": book.server,
                        "author": book.author,
                        "title": book.title,
                        "format": book.format,
                        "size": book.size,
                        "download_command": book.full_command,
                        "raw_line": book.raw_line,
                        "parsed_at": datetime.now().isoformat(),
                        "search_query": search_query,  # Track what was searched
                    }
                )

            # Log parsing errors for debugging
            if parse_errors:
                print(f"[IRC] {len(parse_errors)} parsing errors occurred")
                for error in parse_errors[:3]:  # Log first 3 errors
                    print(f"[IRC] Parse error: {error.error} - {error.line[:100]}")

            self._update_status(
                {
                    "total_searches": self._status["total_searches"] + 1,
                    "last_search_query": search_query,
                    "last_search_results": len(results),
                }
            )

            print(
                f"[IRC] Search completed. Found {len(results)} books for '{search_query}'"
            )
            return results

        else:
            print(f"[IRC] No search results received for '{search_query}'")
            return []

    def _is_search_result(self, line: str) -> bool:
        """Check if a line contains a search result."""
        # Look for common patterns in IRC search results
        patterns = [
            r"!\w+\s+",  # Bot name followed by space
            r"\d+\.\s*",  # Numbered results
            r"\[.*\]",  # Results in brackets
            r"<.*>",  # Results in angle brackets
        ]

        for pattern in patterns:
            if re.search(pattern, line) and any(
                ext in line.lower()
                for ext in [".epub", ".pdf", ".mobi", ".txt", ".zip"]
            ):
                return True
        return False

    def _parse_search_result(self, line: str) -> Optional[Dict]:
        """Parse a search result line into structured data."""
        try:
            # Extract filename and other info
            # This is a simplified parser - may need adjustment based on actual IRC bot responses

            # Look for common file extensions
            extensions = [".epub", ".pdf", ".mobi", ".txt", ".zip"]
            filename = None

            for ext in extensions:
                if ext in line.lower():
                    # Find the filename around the extension
                    parts = line.split()
                    for part in parts:
                        if ext in part.lower():
                            filename = part.strip("[]()<>")
                            break
                    break

            if filename:
                return {
                    "raw_line": line,
                    "filename": filename,
                    "download_command": line.strip(),  # The exact line to send back for download
                    "parsed_at": datetime.now().isoformat(),
                }

        except Exception as e:
            print(f"[IRC] Error parsing result: {e}")

        return None

    def download_file(
        self,
        download_command: str,
        custom_filename: Optional[str] = None,
        search_query: str = "",
    ) -> Dict:
        """Download a file using DCC protocol from IRC."""
        if not self.connected or not self.socket:
            raise Exception("Not connected to IRC")

        self._enforce_rate_limit()

        print(f"[IRC] Requesting download: {download_command}")

        # Clear any previous DCC offers
        if hasattr(self, "_dcc_offers"):
            self._dcc_offers.clear()
        else:
            self._dcc_offers = []

        # Send the download command (usually the exact line from search results)
        self.socket.send(f"PRIVMSG {self.channel} :{download_command}\r\n".encode())

        # Wait for DCC SEND offer
        dcc_offer = None
        self.socket.settimeout(
            self.response_timeout
        )  # Use response timeout for DCC offer

        start_time = time.time()
        while time.time() - start_time < self.response_timeout:
            try:
                resp = self.socket.recv(4096).decode(errors="ignore")
                if resp:
                    print(f"[IRC] Response: {resp.strip()}")

                    # Handle PING/PONG
                    if "PING" in resp:
                        pong_response = resp.replace("PING", "PONG")
                        self.socket.send(pong_response.encode())

                    # Process response for DCC offers
                    self._process_irc_response(resp)

                    # Check if we got a DCC offer
                    if hasattr(self, "_dcc_offers") and self._dcc_offers:
                        dcc_offer = self._dcc_offers[-1]  # Get latest offer
                        print(f"[IRC] Got DCC offer: {dcc_offer.filename}")
                        break
            except socket.timeout:
                break
            except Exception as e:
                print(f"[IRC] Download request error: {e}")
                break

        if not dcc_offer:
            error_msg = "No DCC offer received"
            print(f"[IRC] {error_msg}")
            return {"success": False, "error": error_msg}

        # Download the file using DCC protocol
        try:
            os.makedirs(self.download_dir, exist_ok=True)

            # Use provided filename or DCC offer filename
            if custom_filename:
                filename = custom_filename
            else:
                filename = dcc_offer.filename

            file_path = os.path.join(self.download_dir, filename)
            print(f"[IRC] Downloading via DCC to: {file_path}")

            # Use DCCHandler to perform the download
            download_result = DCCHandler.download_file(dcc_offer, file_path)

            if download_result.get("success", False):
                downloaded_size = download_result.get("size", 0)
                print(
                    f"[IRC] DCC download completed: {file_path} ({downloaded_size} bytes)"
                )

                # If it's a zip file, try to extract it
                extracted_files = []
                if file_path.lower().endswith(".zip"):
                    extracted_files = self._extract_zip(file_path, search_query)

                self._update_status(
                    {"total_downloads": self._status["total_downloads"] + 1}
                )

                return {
                    "success": True,
                    "file_path": file_path,
                    "file_size": downloaded_size,
                    "extracted_files": extracted_files,
                    "dcc_info": {
                        "filename": dcc_offer.filename,
                        "ip": dcc_offer.ip,
                        "port": dcc_offer.port,
                        "size": dcc_offer.size,
                    },
                    "download_result": download_result,
                }
            else:
                error_msg = f"DCC download failed: {download_result.get('error', 'Unknown error')}"
                print(f"[IRC] {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "download_result": download_result,
                }

        except Exception as e:
            error_msg = f"DCC download failed: {str(e)}"
            print(f"[IRC] {error_msg}")
            return {"success": False, "error": error_msg}

    def _extract_zip(self, zip_path: str, search_query: str = "") -> List[str]:
        """
        Extract a zip file and return list of extracted EPUB files with enhanced text file parsing.
        Follows openbooks patterns for ZIP archive handling and book listing extraction.
        """
        extracted_files = []
        try:
            extract_dir = os.path.splitext(zip_path)[0] + "_extracted"
            os.makedirs(extract_dir, exist_ok=True)

            with zipfile.ZipFile(zip_path, "r") as zip_file:
                file_list = zip_file.namelist()
                print(f"[IRC] ZIP archive contains {len(file_list)} files")

                # First priority: Look for text files that might contain book listings
                # Following openbooks pattern: search results are often delivered as text files in ZIP
                txt_files = [
                    name
                    for name in file_list
                    if name.lower().endswith((".txt", ".log", ".list", ".dat"))
                ]

                if txt_files:
                    print(
                        f"[IRC] Found {len(txt_files)} text files in archive: {[f for f in txt_files]}"
                    )

                    # Parse text files for book listings
                    parsed_books = self._parse_text_files_from_zip(
                        zip_file, txt_files, search_query
                    )

                    if parsed_books:
                        print(
                            f"[IRC] Successfully parsed {len(parsed_books)} book entries from text files"
                        )
                        # Return the parsed book information with proper formatting
                        return [f"PARSED_BOOK:{book}" for book in parsed_books]
                    else:
                        print("[IRC] No relevant book listings found in text files")

                # Second priority: Extract actual EPUB files from archive (openbooks pattern)
                epub_files = [
                    name for name in file_list if name.lower().endswith(".epub")
                ]

                if epub_files:
                    print(f"[IRC] Found {len(epub_files)} EPUB files in archive")

                    # Extract only EPUB files to save space
                    for epub_file in epub_files:
                        try:
                            zip_file.extract(epub_file, extract_dir)
                            extracted_path = os.path.join(extract_dir, epub_file)
                            extracted_files.append(extracted_path)
                            print(f"[IRC] Extracted: {epub_file}")
                        except Exception as e:
                            print(f"[IRC] Failed to extract {epub_file}: {e}")

                    print(
                        f"[IRC] Successfully extracted {len(extracted_files)} EPUB files to {extract_dir}"
                    )
                    return extracted_files

                # Third priority: Look for other ebook formats if no EPUB found
                ebook_extensions = [".mobi", ".azw3", ".pdf", ".rtf", ".lit", ".html"]
                other_ebooks = [
                    name
                    for name in file_list
                    if any(name.lower().endswith(ext) for ext in ebook_extensions)
                ]

                if other_ebooks:
                    print(
                        f"[IRC] Found {len(other_ebooks)} other ebook files: {[f.split('/')[-1] for f in other_ebooks[:5]]}"
                    )

                    # Extract other ebook formats as fallback
                    for ebook_file in other_ebooks[
                        :10
                    ]:  # Limit to 10 files to prevent spam
                        try:
                            zip_file.extract(ebook_file, extract_dir)
                            extracted_path = os.path.join(extract_dir, ebook_file)
                            extracted_files.append(extracted_path)
                        except Exception as e:
                            print(f"[IRC] Failed to extract {ebook_file}: {e}")

                    print(
                        f"[IRC] Extracted {len(extracted_files)} ebook files as fallback"
                    )
                    return extracted_files

                print(
                    f"[IRC] No ebook files or book listings found in ZIP archive: {zip_path}"
                )

        except zipfile.BadZipFile:
            print(f"[IRC] Invalid ZIP file: {zip_path}")
        except Exception as e:
            print(f"[IRC] ZIP extraction failed: {e}")

        return extracted_files

    def _parse_text_files_from_zip(
        self, zip_file, txt_files: List[str], search_query: str
    ) -> List[str]:
        """
        Parse text files from ZIP archive to extract book information.
        Enhanced implementation following openbooks ParseSearchV2 patterns.
        """
        all_books = []

        for txt_file in txt_files:
            try:
                print(f"[IRC] Processing text file: {txt_file}")

                with zip_file.open(txt_file) as f:
                    # Try multiple encodings like openbooks does
                    content = None
                    for encoding in ["utf-8", "latin-1", "cp1252", "ascii"]:
                        try:
                            f.seek(0)
                            content = f.read().decode(encoding)
                            break
                        except UnicodeDecodeError:
                            continue

                    if content is None:
                        print(f"[IRC] Could not decode {txt_file} with any encoding")
                        continue

                # Parse lines for book information
                lines = content.split("\n")
                books = self._parse_book_lines_enhanced(lines, txt_file)

                if books:
                    all_books.extend(books)
                    print(
                        f"[IRC] Parsed {len(books)} valid book entries from {txt_file}"
                    )
                else:
                    print(f"[IRC] No valid book entries found in {txt_file}")

            except Exception as e:
                print(f"[IRC] Error parsing {txt_file}: {e}")
                continue

        if not all_books:
            print("[IRC] No books found in any text files")
            return []

        print(f"[IRC] Total books parsed from all text files: {len(all_books)}")

        # Filter and rank books based on search query with enhanced logic
        filtered_books = self._filter_books_by_query_enhanced(all_books, search_query)
        return filtered_books

    def _parse_book_lines(self, lines: List[str]) -> List[Dict]:
        """Parse individual lines to extract book information following the pattern <!server> <author> - <book title>.<extension> <file size>"""
        books = []

        for line in lines:
            line = line.strip()
            if not line or not line.startswith("<!"):
                continue

            try:
                book_info = self._parse_single_book_line(line)
                if book_info:
                    books.append(book_info)
            except Exception as e:
                print(f"[IRC] Error parsing line '{line}': {e}")
                continue

        return books

    def _parse_single_book_line(self, line: str) -> Optional[Dict]:
        """Parse a single book line following the pattern <!server> <author> - <book title>.<extension> <file size>"""
        # Pattern: <!server> <author> - <book title>.<extension> <file size>
        # Example: <!Library> Stephen King - The Shining.epub 1.2MB

        if not line.startswith("<!"):
            return None

        # Extract server name
        server_end = line.find(">")
        if server_end == -1:
            return None

        server = line[2:server_end]  # Remove <! and >
        remaining = line[server_end + 1 :].strip()

        # Look for dash separator between author and title
        dash_pos = remaining.find(" - ")
        if dash_pos == -1:
            return None

        author_part = remaining[:dash_pos].strip()
        title_and_rest = remaining[dash_pos + 3 :].strip()

        # Find file extension and size
        # Look for common ebook extensions
        extensions = ["epub", "mobi", "azw3", "pdf", "txt", "html", "rtf"]
        extension_found = None
        title_end = len(title_and_rest)

        for ext in extensions:
            pattern = f".{ext}"
            pos = title_and_rest.lower().find(pattern)
            if pos != -1:
                extension_found = ext
                title_end = pos
                break

        if not extension_found:
            return None

        title = title_and_rest[:title_end].strip()

        # Extract file size (everything after the extension)
        size_part = title_and_rest[title_end:].strip()
        # Remove the extension part and extract size
        size_match = re.search(r"(\d+(?:\.\d+)?\s*[KMGT]?B)", size_part, re.IGNORECASE)
        file_size = size_match.group(1) if size_match else "Unknown"

        return {
            "server": server,
            "author": author_part,
            "title": title,
            "extension": extension_found,
            "size": file_size,
            "raw_line": line,
        }

    def _filter_books_by_query(self, books: List[Dict], search_query: str) -> List[str]:
        """Filter and rank books based on search query with intelligent author/title matching."""
        if not books or not search_query:
            return []

        query_lower = search_query.lower()
        matched_books = []

        for book in books:
            author_lower = book["author"].lower()
            title_lower = book["title"].lower()

            # Check if this is an author search or title search
            if self._is_author_match(author_lower, query_lower):
                score = self._calculate_author_score(book, query_lower)
                matched_books.append((book, score, "author"))
            elif self._is_title_match(title_lower, query_lower):
                score = self._calculate_title_score(book, query_lower)
                matched_books.append((book, score, "title"))

        if not matched_books:
            return []

        # Sort by score (higher is better)
        matched_books.sort(key=lambda x: x[1], reverse=True)

        # Format results for return
        results = []
        for book, score, match_type in matched_books[:20]:  # Limit to top 20 results
            result = f"{book['author']} - {book['title']}.{book['extension']} ({book['size']}) [Score: {score:.2f}, Match: {match_type}]"
            results.append(result)

        return results

    def _is_author_match(self, author_name: str, query: str) -> bool:
        """Check if the query matches an author name (handles reversed names)."""
        # Split both author and query into words
        author_words = set(author_name.replace(",", "").split())
        query_words = set(query.split())

        # Check for substantial overlap (at least 1 word match for short queries, more for longer)
        min_matches = 1 if len(query_words) <= 2 else 2
        matches = len(author_words.intersection(query_words))

        return matches >= min_matches

    def _is_title_match_simple(self, title: str, query: str) -> bool:
        """Check if the query matches a title (simple version)."""
        # Simple substring match for titles
        return query in title or any(
            word in title for word in query.split() if len(word) > 2
        )

    def _calculate_author_score(self, book: Dict, query: str) -> float:
        """Calculate score for author matches with prioritization rules."""
        score = 0.0
        title_lower = book["title"].lower()

        # Base score for author match
        score += 10.0

        # Bonus for v5 in title (highest priority for author searches)
        if "v5" in title_lower:
            score += 50.0
        elif "v4" in title_lower:
            score += 30.0
        elif "v3" in title_lower:
            score += 20.0
        elif "v2" in title_lower:
            score += 10.0

        # File size bonus (larger is better)
        size_score = self._get_size_score(book["size"])
        score += size_score

        # Format preference (epub > mobi > others)
        format_bonus = {"epub": 5.0, "mobi": 3.0, "azw3": 2.0}.get(
            book["extension"], 0.0
        )
        score += format_bonus

        return score

    def _calculate_title_score(self, book: Dict, query: str) -> float:
        """Calculate score for title matches."""
        score = 0.0
        title_lower = book["title"].lower()
        query_lower = query.lower()

        # Base score for title match
        if query_lower == title_lower:
            score += 20.0  # Exact match
        elif query_lower in title_lower:
            score += 15.0  # Substring match
        else:
            # Word overlap
            title_words = set(title_lower.split())
            query_words = set(query_lower.split())
            overlap = len(title_words.intersection(query_words))
            score += overlap * 2.0

        # Same bonuses as author search but with lower weight
        if "v5" in title_lower:
            score += 25.0
        elif "v4" in title_lower:
            score += 15.0

        size_score = self._get_size_score(book["size"])
        score += size_score * 0.5  # Lower weight for title searches

        format_bonus = {"epub": 3.0, "mobi": 2.0, "azw3": 1.0}.get(
            book["extension"], 0.0
        )
        score += format_bonus

        return score

    def _get_size_score(self, size_str: str) -> float:
        """Convert file size to a score (larger files get higher scores)."""
        if not size_str or size_str == "Unknown":
            return 0.0

        try:
            # Extract number and unit
            match = re.match(r"(\d+(?:\.\d+)?)\s*([KMGT]?B)", size_str.upper())
            if not match:
                return 0.0

            number = float(match.group(1))
            unit = match.group(2)

            # Convert to MB for scoring
            multipliers = {
                "B": 0.000001,
                "KB": 0.001,
                "MB": 1.0,
                "GB": 1000.0,
                "TB": 1000000.0,
            }
            size_mb = number * multipliers.get(unit, 1.0)

            # Score based on size (logarithmic scale to prevent huge files from dominating)
            import math

            return math.log10(max(size_mb, 0.1)) * 2.0

        except Exception:
            return 0.0

    def _parse_book_lines_enhanced(
        self, lines: List[str], source_file: str
    ) -> List[Dict]:
        """
        Enhanced book line parsing following openbooks parseLineV2 patterns.
        Supports multiple line formats and better error recovery.
        """
        books = []
        valid_lines = 0

        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue

            # Skip comment lines and headers
            if line.startswith("#") or line.startswith("//") or line.startswith(";"):
                continue

            try:
                book_info = self._parse_single_book_line_enhanced(
                    line, source_file, line_num
                )
                if book_info:
                    books.append(book_info)
                    valid_lines += 1
            except Exception as e:
                # Log parsing errors but continue processing
                if valid_lines < 5:  # Only log first few errors to avoid spam
                    print(f"[IRC] Parse error in {source_file}:{line_num}: {e}")
                continue

        print(
            f"[IRC] Parsed {len(books)} valid books from {valid_lines} lines in {source_file}"
        )
        return books

    def _parse_single_book_line_enhanced(
        self, line: str, source_file: str, line_num: int
    ) -> Optional[Dict]:
        """
        Enhanced single line parsing following openbooks parseLineV2 patterns.
        Supports multiple formats:
        - !server author - title.ext ::INFO:: size
        - !server author - title.ext size
        - Alternative format: <!server> author - title.ext size
        - Simple format: server author - title.ext size (without leading !)
        """
        original_line = line

        # Try different line formats
        patterns = [
            # openbooks v2 format: !server author - title.ext ::INFO:: size
            r"^!([^>]+)\s+(.+?)\s+-\s+(.+?)\.([a-zA-Z0-9]+)\s+::INFO::\s+(.+)$",
            # openbooks v1 format: !server author - title.ext size
            r"^!([^>]+)\s+(.+?)\s+-\s+(.+?)\.([a-zA-Z0-9]+)\s+(.+)$",
            # Alternative format: <!server> author - title.ext size
            r"^<!([^>]+)>\s+(.+?)\s+-\s+(.+?)\.([a-zA-Z0-9]+)\s+(.+)$",
            # Simple format: server author - title.ext size
            r"^([^!\s]+)\s+(.+?)\s+-\s+(.+?)\.([a-zA-Z0-9]+)\s+(.+)$",
        ]

        for pattern in patterns:
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                server, author, title, extension, size_info = match.groups()

                # Clean up the extracted data
                server = server.strip()
                author = author.strip()
                title = title.strip()
                extension = extension.lower().strip()

                # Extract just the size from size_info (may contain additional info)
                size = self._extract_size_from_info(size_info)

                # Validate ebook extension
                if not self._is_valid_ebook_extension(extension):
                    continue

                # Validate minimum data quality
                if len(author) < 2 or len(title) < 2:
                    continue

                return {
                    "server": server,
                    "author": author,
                    "title": title,
                    "extension": extension,
                    "size": size,
                    "raw_line": original_line,
                    "source_file": source_file,
                    "line_number": line_num,
                    "full_command": f"!{server} {author} - {title}.{extension}",
                }

        # If no pattern matched, return None (not an error)
        return None

    def _extract_size_from_info(self, size_info: str) -> str:
        """Extract file size from info string, handling various formats."""
        # Common size patterns
        size_patterns = [
            r"(\d+(?:\.\d+)?\s*[KMGT]?B)",  # Standard: 1.2MB, 500KB, etc.
            r"(\d+(?:\.\d+)?\s*[KMGT])",  # Without B: 1.2M, 500K
            r"(\d+(?:,\d+)*\s*bytes?)",  # Bytes: 1,234,567 bytes
        ]

        for pattern in size_patterns:
            match = re.search(pattern, size_info, re.IGNORECASE)
            if match:
                return match.group(1)

        # If no size found, return the original string (up to first 20 chars)
        return size_info[:20].strip()

    def _is_valid_ebook_extension(self, extension: str) -> bool:
        """Check if the extension is a valid ebook format."""
        valid_extensions = {
            "epub",
            "mobi",
            "azw",
            "azw3",
            "pdf",
            "txt",
            "html",
            "htm",
            "rtf",
            "doc",
            "docx",
            "lit",
            "pdb",
            "fb2",
            "djvu",
            "chm",
        }
        return extension.lower() in valid_extensions

    def _filter_books_by_query_enhanced(
        self, books: List[Dict], search_query: str
    ) -> List[str]:
        """
        Enhanced filtering following openbooks intelligent search patterns.
        Implements sophisticated scoring for author vs title searches.
        """
        if not books or not search_query:
            return [self._format_book_result(book) for book in books[:20]]

        query_lower = search_query.lower().strip()
        matched_books = []

        # Determine if this is primarily an author search or title search
        search_type = self._determine_search_type(query_lower)

        for book in books:
            score = 0.0
            match_types = []

            # Author matching
            author_score = self._calculate_author_match_score(
                book["author"], query_lower
            )
            if author_score > 0:
                score += author_score
                match_types.append("author")

            # Title matching
            title_score = self._calculate_title_match_score(book["title"], query_lower)
            if title_score > 0:
                score += title_score
                match_types.append("title")

            # Only include books with some match
            if score > 0:
                # Apply search type weighting
                if search_type == "author" and "author" in match_types:
                    score *= 1.5  # Boost author matches for author searches
                elif search_type == "title" and "title" in match_types:
                    score *= 1.3  # Boost title matches for title searches

                # Apply additional scoring factors
                score += self._get_version_score(book["title"])
                score += self._get_enhanced_size_score(book["size"])
                score += self._get_format_preference_score(book["extension"])

                matched_books.append((book, score, match_types))

        if not matched_books:
            print(f"[IRC] No books matched query: {search_query}")
            return []

        # Sort by score (descending)
        matched_books.sort(key=lambda x: x[1], reverse=True)

        # Format and return results (limit to top 30)
        results = []
        for book, score, match_types in matched_books[:30]:
            formatted_result = self._format_enhanced_book_result(
                book, score, match_types
            )
            results.append(formatted_result)

        print(f"[IRC] Filtered to {len(results)} books matching '{search_query}'")
        return results

    def _determine_search_type(self, query: str) -> str:
        """Determine if query is primarily for author or title search."""
        # Look for patterns that suggest author search
        author_indicators = ["by ", "author:", "written by", ".", ","]
        title_indicators = ["the ", "a ", "an ", "book:", "title:"]

        author_score = sum(1 for indicator in author_indicators if indicator in query)
        title_score = sum(1 for indicator in title_indicators if indicator in query)

        if author_score > title_score:
            return "author"
        elif title_score > author_score:
            return "title"
        else:
            # Default heuristic: if query has fewer than 3 words, likely author
            return "author" if len(query.split()) <= 2 else "title"

    def _calculate_author_match_score(self, author: str, query: str) -> float:
        """Calculate how well the author matches the query."""
        author_lower = author.lower()
        score = 0.0

        # Exact match (highest score)
        if query == author_lower:
            score += 100.0
        # Full substring match
        elif query in author_lower:
            score += 80.0
        # Partial word matching
        else:
            author_words = set(author_lower.replace(",", "").split())
            query_words = set(query.split())

            # Calculate word overlap
            matches = author_words.intersection(query_words)
            if matches:
                # Score based on proportion of query words matched
                match_ratio = len(matches) / len(query_words)
                score += match_ratio * 60.0

        return score

    def _calculate_title_match_score(self, title: str, query: str) -> float:
        """Calculate how well the title matches the query."""
        title_lower = title.lower()
        score = 0.0

        # Exact match
        if query == title_lower:
            score += 100.0
        # Full substring match
        elif query in title_lower:
            score += 70.0
        # Word-based matching
        else:
            title_words = set(title_lower.split())
            query_words = set(query.split())

            matches = title_words.intersection(query_words)
            if matches:
                match_ratio = len(matches) / len(query_words)
                score += match_ratio * 50.0

        return score

    def _get_version_score(self, title: str) -> float:
        """Score books based on version indicators (v5 > v4 > v3 etc)."""
        title_lower = title.lower()

        # Version priority scoring (openbooks pattern)
        if "v5" in title_lower or "version 5" in title_lower:
            return 50.0
        elif "v4" in title_lower or "version 4" in title_lower:
            return 30.0
        elif "v3" in title_lower or "version 3" in title_lower:
            return 20.0
        elif "v2" in title_lower or "version 2" in title_lower:
            return 10.0
        elif "v1" in title_lower or "version 1" in title_lower:
            return 5.0

        # Bonus for other quality indicators
        quality_indicators = ["retail", "final", "complete", "unabridged", "original"]
        for indicator in quality_indicators:
            if indicator in title_lower:
                return 15.0

        return 0.0

    def _get_enhanced_size_score(self, size_str: str) -> float:
        """Enhanced size scoring with better parsing."""
        if not size_str or size_str == "Unknown":
            return 0.0

        try:
            # Parse size more robustly
            size_mb = self._parse_size_to_mb(size_str)
            if size_mb <= 0:
                return 0.0

            # Logarithmic scoring to prevent huge files from dominating
            import math

            base_score = math.log10(max(size_mb, 0.1)) * 3.0

            # Prefer reasonable ebook sizes (0.5MB - 50MB)
            if 0.5 <= size_mb <= 50:
                base_score += 5.0
            elif size_mb > 50:
                base_score -= 2.0  # Penalty for very large files

            return max(base_score, 0.0)

        except Exception:
            return 0.0

    def _parse_size_to_mb(self, size_str: str) -> float:
        """Parse size string to MB value."""
        # Clean the size string
        size_clean = re.sub(r"[,\s]+", "", size_str.upper())

        # Extract number and unit
        match = re.match(r"(\d+(?:\.\d+)?)([KMGT]?B?)", size_clean)
        if not match:
            return 0.0

        number = float(match.group(1))
        unit = match.group(2) or "B"

        # Convert to MB
        multipliers = {
            "B": 0.000001,
            "KB": 0.001,
            "K": 0.001,
            "MB": 1.0,
            "M": 1.0,
            "GB": 1000.0,
            "G": 1000.0,
            "TB": 1000000.0,
            "T": 1000000.0,
        }

        return number * multipliers.get(unit, 1.0)

    def _get_format_preference_score(self, extension: str) -> float:
        """Score based on format preference (EPUB highest)."""
        format_scores = {
            "epub": 15.0,  # Highest preference
            "mobi": 10.0,
            "azw3": 8.0,
            "pdf": 5.0,
            "html": 3.0,
            "txt": 2.0,
            "rtf": 1.0,
        }
        return format_scores.get(extension.lower(), 0.0)

    def _format_enhanced_book_result(
        self, book: Dict, score: float, match_types: List[str]
    ) -> str:
        """Format book result with enhanced information."""
        match_info = "+".join(match_types) if match_types else "general"
        return (
            f"{book['author']} - {book['title']}.{book['extension']} "
            f"({book['size']}) [{book['server']}] "
            f"[Score: {score:.1f}, Match: {match_info}]"
        )

    def _format_book_result(self, book: Dict) -> str:
        """Simple book result formatting."""
        return (
            f"{book['author']} - {book['title']}.{book['extension']} "
            f"({book['size']}) [{book['server']}]"
        )

    def disconnect(self) -> None:
        """Disconnect from IRC server."""
        if self.socket:
            try:
                self.socket.send(b"QUIT :Goodbye\r\n")
                self.socket.close()
            except Exception:
                pass
            finally:
                self.socket = None
                self.connected = False
                self.joined_channel = False
                print(f"[IRC] Disconnected from {self.server}")

    def search_epub_only(self, query: str, max_results: int = 50) -> List[Dict]:
        """Search for books and filter for EPUB format only (openbooks pattern)."""
        # Perform regular search
        all_results = self.search_books(query, max_results=max_results)

        # Filter for EPUB only using search parser
        if all_results:
            # Convert back to BookDetail objects for filtering
            book_details = []
            for result in all_results:
                from .search_parser import BookDetail

                book_detail = BookDetail(
                    server=result.get("server", ""),
                    author=result.get("author", ""),
                    title=result.get("title", ""),
                    format=result.get("format", ""),
                    size=result.get("size", ""),
                    full_command=result.get("download_command", ""),
                    raw_line=result.get("raw_line", ""),
                )
                book_details.append(book_detail)

            # Filter for EPUB only
            epub_books = self.search_parser.filter_results(book_details, epub_only=True)

            # Convert back to dict format
            epub_results = []
            for book in epub_books:
                epub_results.append(
                    {
                        "server": book.server,
                        "author": book.author,
                        "title": book.title,
                        "format": book.format,
                        "size": book.size,
                        "download_command": book.full_command,
                        "raw_line": book.raw_line,
                        "parsed_at": datetime.now().isoformat(),
                        "search_query": query,
                    }
                )

            print(f"[IRC] Filtered to {len(epub_results)} EPUB-only results")
            return epub_results

        return []

    def download_epub_only(
        self,
        download_command: str,
        output_dir: Optional[str] = None,
        search_query: str = "",
    ) -> Dict:
        """Download a file and extract only EPUB files if it's an archive."""
        if not output_dir:
            output_dir = self.download_dir

        # Set download directory temporarily
        original_dir = self.download_dir
        self.download_dir = output_dir

        try:
            # Download the file
            result = self.download_file(download_command, search_query=search_query)

            if result.get("success"):
                file_path = result.get("file_path")
                extracted_files = result.get("extracted_files", [])

                # If extracted files contain parsed book info (from text files)
                if extracted_files and any(
                    f.startswith("PARSED_BOOK:") for f in extracted_files
                ):
                    # Return the parsed book information
                    parsed_books = [
                        f.replace("PARSED_BOOK:", "")
                        for f in extracted_files
                        if f.startswith("PARSED_BOOK:")
                    ]
                    result["parsed_books"] = parsed_books
                    result["file_type"] = "parsed_text"
                    print(f"[IRC] Returned {len(parsed_books)} parsed book entries")
                elif file_path and file_path.lower().endswith(".epub"):
                    # Already an EPUB file
                    result["epub_files"] = [file_path]
                    result["file_type"] = "epub"
                elif extracted_files:
                    # Archive with extracted EPUB files
                    epub_files = [
                        f for f in extracted_files if f.lower().endswith(".epub")
                    ]
                    result["epub_files"] = epub_files
                    result["file_type"] = "archive"
                    print(f"[IRC] Extracted {len(epub_files)} EPUB files")
                else:
                    result["epub_files"] = []
                    result["file_type"] = "other"
                    print("[IRC] No EPUB files found in download")

            return result

        finally:
            # Restore original download directory
            self.download_dir = original_dir

    def search_author_level(
        self, author: str, max_results: int = 50, timeout_minutes: int = 3
    ) -> List[Dict]:
        """
        Author-level search: Find different titles by the same author.
        Returns best candidates for each unique title using v5 or largest file size priority.
        """
        if not self.connected or not self.socket:
            raise Exception("Not connected to IRC")

        print(f"[IRC] Starting author-level search for: {author}")

        # Perform search with author only
        all_results = self.search_books(
            author, max_results=max_results * 2
        )  # Get more results for filtering

        if not all_results:
            print(f"[IRC] No results found for author: {author}")
            return []

        # Group results by title to find unique books
        title_groups = {}
        for result in all_results:
            title_key = self._normalize_title(result["title"])
            if title_key not in title_groups:
                title_groups[title_key] = []
            title_groups[title_key].append(result)

        print(f"[IRC] Found {len(title_groups)} unique titles for author '{author}'")

        # Select best candidate for each title using v5/size priority
        best_candidates = []
        for title_key, candidates in title_groups.items():
            best_candidate = self._select_best_candidate(candidates, "author")
            if best_candidate:
                best_candidates.append(best_candidate)

        # Sort by title and limit results
        best_candidates.sort(key=lambda x: x["title"])
        final_results = best_candidates[:max_results]

        print(
            f"[IRC] Author-level search completed. Found {len(final_results)} unique books"
        )
        return final_results

    def search_title_level(
        self, author: str, title: str, max_results: int = 20, timeout_minutes: int = 3
    ) -> List[Dict]:
        """
        Title-level search: Find specific title by author with multiple server options.
        Returns candidates ranked by v5 or largest file size, different servers prioritized.
        """
        if not self.connected or not self.socket:
            raise Exception("Not connected to IRC")

        print(f"[IRC] Starting title-level search for: {author} - {title}")

        # Perform search with both author and title
        all_results = self.search_books(author, title, max_results=max_results * 3)

        if not all_results:
            print(f"[IRC] No results found for: {author} {title}")
            return []

        # Filter for exact title matches
        exact_matches = []
        normalized_target = self._normalize_title(title)

        for result in all_results:
            normalized_result = self._normalize_title(result["title"])
            if self._is_title_match(normalized_target, normalized_result):
                exact_matches.append(result)

        if not exact_matches:
            print(f"[IRC] No exact title matches found for: {title}")
            return []

        print(f"[IRC] Found {len(exact_matches)} exact matches for title")

        # Group by server and select best from each
        server_groups = {}
        for result in exact_matches:
            server = result["server"]
            if server not in server_groups:
                server_groups[server] = []
            server_groups[server].append(result)

        # Select best candidate from each server
        server_candidates = []
        for server, candidates in server_groups.items():
            best_candidate = self._select_best_candidate(candidates, "title")
            if best_candidate:
                server_candidates.append(best_candidate)

        # Sort by quality score (v5 first, then size)
        server_candidates = self._rank_candidates(server_candidates, "title")

        print(
            f"[IRC] Title-level search completed. Found {len(server_candidates)} server options"
        )
        return server_candidates[:max_results]

    def smart_search_and_download(
        self,
        author: str,
        title: Optional[str] = None,
        timeout_minutes: int = 3,
        custom_filename: Optional[str] = None,
    ) -> Dict:
        """
        Intelligent two-tier search and download with automatic fallback.

        If title is provided: uses title-level search for specific book with server fallback
        If title is None: uses author-level search to find best books by author
        """
        try:
            if title:
                # Title-level search: find specific book with server options
                print(
                    f"[IRC] Smart search: Looking for specific book '{title}' by {author}"
                )
                candidates = self.search_title_level(
                    author, title, max_results=10, timeout_minutes=timeout_minutes
                )

                if candidates:
                    print(f"[IRC] Found {len(candidates)} server options for '{title}'")
                    # Download with fallback across servers
                    download_result = self.download_with_fallback(
                        candidates, timeout_minutes, custom_filename
                    )
                    download_result["search_type"] = "title_level"
                    download_result["search_query"] = f"{author} - {title}"
                    return download_result
                else:
                    return {
                        "success": False,
                        "error": f"No copies of '{title}' by {author} found on any server",
                        "search_type": "title_level",
                        "search_query": f"{author} - {title}",
                    }
            else:
                # Author-level search: find best unique books by author
                print(f"[IRC] Smart search: Finding best books by {author}")
                unique_books = self.search_author_level(
                    author, max_results=20, timeout_minutes=timeout_minutes
                )

                if unique_books:
                    # For author search, return the list of unique books for user selection
                    return {
                        "success": True,
                        "search_type": "author_level",
                        "search_query": author,
                        "unique_books": unique_books,
                        "total_found": len(unique_books),
                        "message": f"Found {len(unique_books)} unique books by {author}. Use title-level search to download specific book.",
                    }
                else:
                    return {
                        "success": False,
                        "error": f"No books found by author: {author}",
                        "search_type": "author_level",
                        "search_query": author,
                    }

        except Exception as e:
            return {
                "success": False,
                "error": f"Smart search failed: {str(e)}",
                "search_type": "smart_search",
                "search_query": f"{author} - {title}" if title else author,
            }

    def download_with_fallback(
        self,
        candidates: List[Dict],
        timeout_minutes: int = 3,
        custom_filename: Optional[str] = None,
    ) -> Dict:
        """
        Download file with automatic fallback to next candidate if timeout occurs.
        Tries each candidate in order until successful or all candidates exhausted.
        """
        if not candidates:
            return {"success": False, "error": "No candidates provided"}

        timeout_seconds = timeout_minutes * 60
        total_attempts = len(candidates)

        print(
            f"[IRC] Starting download with {total_attempts} candidates, {timeout_minutes}min timeout each"
        )

        for attempt, candidate in enumerate(candidates, 1):
            server = candidate.get("server", "unknown")
            title = candidate.get("title", "unknown")

            print(
                f"[IRC] Attempt {attempt}/{total_attempts}: Trying server '{server}' for '{title}'"
            )

            try:
                # Set custom timeout for this download
                download_result = self._download_with_timeout(
                    candidate["download_command"], timeout_seconds, custom_filename
                )

                if download_result.get("success", False):
                    print(f"[IRC] Download successful from server '{server}'")
                    download_result["attempt_number"] = attempt
                    download_result["total_attempts"] = total_attempts
                    download_result["used_candidate"] = candidate
                    return download_result
                else:
                    error_msg = download_result.get("error", "Unknown error")
                    print(f"[IRC] Download failed from server '{server}': {error_msg}")

                    # If not the last candidate, continue to next
                    if attempt < total_attempts:
                        print("[IRC] Trying next candidate...")
                        continue

            except Exception as e:
                print(f"[IRC] Exception during download from server '{server}': {e}")
                if attempt < total_attempts:
                    continue

        # All candidates failed
        return {
            "success": False,
            "error": f"All {total_attempts} download candidates failed",
            "total_attempts": total_attempts,
            "candidates_tried": [c.get("server", "unknown") for c in candidates],
        }

    def _download_with_timeout(
        self,
        download_command: str,
        timeout_seconds: int,
        custom_filename: Optional[str] = None,
    ) -> Dict:
        """Download file with specific timeout."""
        import signal

        def timeout_handler(signum, frame):
            raise TimeoutError(f"Download timeout after {timeout_seconds} seconds")

        # Set up timeout signal
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout_seconds)

        try:
            # Perform the download
            result = self.download_file(download_command, custom_filename)
            signal.alarm(0)  # Cancel the alarm
            return result

        except TimeoutError as e:
            print(f"[IRC] Download timeout: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            print(f"[IRC] Download error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            # Restore original signal handler
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

    def _normalize_title(self, title: str) -> str:
        """Normalize title for comparison by removing common variations."""
        if not title:
            return ""

        normalized = title.lower().strip()

        # Remove common prefixes/suffixes
        prefixes_to_remove = ["the ", "a ", "an "]
        for prefix in prefixes_to_remove:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :]

        # Remove version information and extra content
        normalized = re.sub(
            r"\s*\([^)]*\)\s*", " ", normalized
        )  # Remove parentheses content
        normalized = re.sub(
            r"\s*\[[^\]]*\]\s*", " ", normalized
        )  # Remove brackets content
        normalized = re.sub(
            r"\s*v\d+\s*", " ", normalized, re.IGNORECASE
        )  # Remove version numbers
        normalized = re.sub(r"\s+", " ", normalized).strip()  # Normalize whitespace

        return normalized

    def _is_title_match(self, target: str, candidate: str) -> bool:
        """Check if two normalized titles match closely enough."""
        if not target or not candidate:
            return False

        # Exact match
        if target == candidate:
            return True

        # Substring match (either direction)
        if target in candidate or candidate in target:
            return True

        # Word-based similarity
        target_words = set(target.split())
        candidate_words = set(candidate.split())

        if not target_words or not candidate_words:
            return False

        # Calculate similarity ratio
        overlap = len(target_words.intersection(candidate_words))
        total_unique = len(target_words.union(candidate_words))
        similarity = overlap / total_unique if total_unique > 0 else 0

        # Consider it a match if similarity is high enough
        return similarity >= 0.7

    def _select_best_candidate(
        self, candidates: List[Dict], search_type: str
    ) -> Optional[Dict]:
        """Select the best candidate from a list using v5/size priority."""
        if not candidates:
            return None

        if len(candidates) == 1:
            return candidates[0]

        # Score each candidate
        scored_candidates = []
        for candidate in candidates:
            score = self._calculate_candidate_score(candidate, search_type)
            scored_candidates.append((candidate, score))

        # Sort by score (highest first)
        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        best_candidate = scored_candidates[0][0]
        best_score = scored_candidates[0][1]

        print(
            f"[IRC] Selected best candidate: {best_candidate.get('title', 'unknown')} "
            f"from {best_candidate.get('server', 'unknown')} (score: {best_score:.2f})"
        )

        return best_candidate

    def _calculate_candidate_score(self, candidate: Dict, search_type: str) -> float:
        """Calculate quality score for a candidate."""
        score = 0.0
        title = candidate.get("title", "").lower()
        size = candidate.get("size", "")
        format_type = candidate.get("format", "").lower()

        # Version priority (highest priority)
        if "v5" in title:
            score += 100.0
        elif "v4" in title:
            score += 80.0
        elif "v3" in title:
            score += 60.0
        elif "v2" in title:
            score += 40.0
        elif "v1" in title:
            score += 20.0

        # File size scoring
        size_score = self._parse_size_for_scoring(size)
        score += size_score

        # Format preference (EPUB highest)
        format_scores = {
            "epub": 30.0,
            "mobi": 20.0,
            "azw3": 15.0,
            "pdf": 10.0,
            "txt": 5.0,
        }
        score += format_scores.get(format_type, 0.0)

        # Quality indicators
        quality_keywords = ["retail", "final", "complete", "unabridged", "original"]
        for keyword in quality_keywords:
            if keyword in title:
                score += 25.0
                break

        # Bonus for specific search types
        if search_type == "author":
            # For author searches, prefer newer versions more
            if "v5" in title:
                score += 50.0
        elif search_type == "title":
            # For title searches, prefer larger files (more complete)
            score += size_score * 0.5

        return score

    def _parse_size_for_scoring(self, size_str: str) -> float:
        """Parse size string and return scoring value."""
        if not size_str:
            return 0.0

        try:
            # Extract number and unit
            match = re.match(r"(\d+(?:\.\d+)?)\s*([KMGT]?B?)", size_str.upper())
            if not match:
                return 0.0

            number = float(match.group(1))
            unit = match.group(2) or "B"

            # Convert to MB for scoring
            multipliers = {
                "B": 0.000001,
                "KB": 0.001,
                "K": 0.001,
                "MB": 1.0,
                "M": 1.0,
                "GB": 1000.0,
                "G": 1000.0,
                "TB": 1000000.0,
                "T": 1000000.0,
            }

            size_mb = number * multipliers.get(unit, 1.0)

            # Logarithmic scoring with reasonable ebook size preference
            import math

            base_score = math.log10(max(size_mb, 0.1)) * 10.0

            # Bonus for reasonable ebook sizes (0.5MB - 50MB)
            if 0.5 <= size_mb <= 50:
                base_score += 20.0
            elif size_mb > 100:
                base_score -= 10.0  # Penalty for very large files

            return max(base_score, 0.0)

        except Exception:
            return 0.0

    def _rank_candidates(self, candidates: List[Dict], search_type: str) -> List[Dict]:
        """Rank candidates by quality score."""
        if not candidates:
            return []

        scored_candidates = []
        for candidate in candidates:
            score = self._calculate_candidate_score(candidate, search_type)
            scored_candidates.append((candidate, score))

        # Sort by score (highest first)
        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        # Return just the candidates in ranked order
        return [candidate for candidate, score in scored_candidates]


# Global session manager
_active_sessions: Dict[str, IRCSession] = {}
_sessions_lock = threading.RLock()


def create_irc_session() -> str:
    """Create a new IRC session and return session ID."""
    session = IRCSession()

    with _sessions_lock:
        _active_sessions[session.session_id] = session

    # Connect in background
    def connect_session():
        try:
            if session.connect():
                print(f"[IRC] Session {session.session_id} connected successfully")
            else:
                print(f"[IRC] Session {session.session_id} failed to connect")
                # Keep session in list for status tracking even if connection failed
        except Exception as e:
            print(f"[IRC] Session {session.session_id} connection error: {e}")
            session._update_status({"errors": [f"Connection failed: {str(e)}"]})

    thread = threading.Thread(target=connect_session, daemon=True)
    thread.start()

    return session.session_id


def get_session(session_id: str) -> Optional[IRCSession]:
    """Get an active IRC session."""
    with _sessions_lock:
        return _active_sessions.get(session_id)


def close_session(session_id: str) -> bool:
    """Close an IRC session."""
    with _sessions_lock:
        session = _active_sessions.pop(session_id, None)
        if session:
            session.disconnect()
            return True
        return False


def search_and_download(
    session_id: str, author: str, title: Optional[str] = None
) -> Dict:
    """Search for books and return results for potential download."""
    session = get_session(session_id)
    if not session:
        return {"success": False, "error": "Session not found"}

    if not session.connected:
        return {"success": False, "error": "Session not connected"}

    try:
        results = session.search_books(author, title)
        return {
            "success": True,
            "results": results,
            "session_status": session.get_status(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def download_from_result(
    session_id: str, download_command: str, filename: Optional[str] = None
) -> Dict:
    """Download a file using a specific download command."""
    session = get_session(session_id)
    if not session:
        return {"success": False, "error": "Session not found"}

    if not session.connected:
        return {"success": False, "error": "Session not connected"}

    try:
        result = session.download_file(download_command, filename)
        result["session_status"] = session.get_status()
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_session_status(session_id: str) -> Dict:
    """Get the status of an IRC session."""
    session = get_session(session_id)
    if not session:
        return {"success": False, "error": "Session not found"}

    return {"success": True, "status": session.get_status(), "session_id": session_id}


def list_active_sessions() -> List[Dict]:
    """List all active IRC sessions."""
    with _sessions_lock:
        sessions = []
        for session_id, session in _active_sessions.items():
            sessions.append({"session_id": session_id, "status": session.get_status()})
        return sessions


def search_epub_only(session_id: str, search_query: str, max_results: int = 50) -> Dict:
    """Search for EPUB books only (openbooks pattern)."""
    session = get_session(session_id)
    if not session:
        return {"success": False, "error": "Session not found"}

    if not session.connected:
        return {"success": False, "error": "Session not connected"}

    try:
        results = session.search_epub_only(search_query, max_results)
        return {
            "success": True,
            "results": results,
            "epub_count": len(results),
            "session_status": session.get_status(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def download_epub_only(
    session_id: str, download_command: str, output_dir: Optional[str] = None
) -> Dict:
    """Download a file ensuring it's EPUB format only (openbooks pattern)."""
    session = get_session(session_id)
    if not session:
        return {"success": False, "error": "Session not found"}

    if not session.connected:
        return {"success": False, "error": "Session not connected"}

    try:
        result = session.download_epub_only(download_command, output_dir)
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


def smart_search_and_download(
    session_id: str,
    author: str,
    title: Optional[str] = None,
    timeout_minutes: int = 3,
    custom_filename: Optional[str] = None,
) -> Dict:
    """
    Intelligent two-tier search and download with automatic fallback.

    Args:
        session_id: IRC session ID
        author: Author name to search for
        title: Optional specific title. If provided, searches for exact book with server fallback.
               If None, returns list of unique books by author for selection.
        timeout_minutes: Timeout for download attempts (default 3 minutes)
        custom_filename: Optional custom filename for download

    Returns:
        For title search: Download result with fallback across servers
        For author search: List of unique books for user selection
    """
    session = get_session(session_id)
    if not session:
        return {"success": False, "error": "Session not found"}

    if not session.connected:
        return {"success": False, "error": "Session not connected"}

    try:
        result = session.smart_search_and_download(
            author, title, timeout_minutes, custom_filename
        )
        result["session_status"] = session.get_status()
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_author_books(session_id: str, author: str, max_results: int = 50) -> Dict:
    """
    Author-level search: Find all unique books by an author.
    Returns best version of each unique title.
    """
    session = get_session(session_id)
    if not session:
        return {"success": False, "error": "Session not found"}

    if not session.connected:
        return {"success": False, "error": "Session not connected"}

    try:
        unique_books = session.search_author_level(author, max_results)
        return {
            "success": True,
            "author": author,
            "unique_books": unique_books,
            "total_found": len(unique_books),
            "session_status": session.get_status(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_specific_book(
    session_id: str, author: str, title: str, max_results: int = 20
) -> Dict:
    """
    Title-level search: Find specific book with multiple server options.
    Returns candidates from different servers ranked by quality.
    """
    session = get_session(session_id)
    if not session:
        return {"success": False, "error": "Session not found"}

    if not session.connected:
        return {"success": False, "error": "Session not connected"}

    try:
        server_options = session.search_title_level(author, title, max_results)
        return {
            "success": True,
            "author": author,
            "title": title,
            "server_options": server_options,
            "total_servers": len(server_options),
            "session_status": session.get_status(),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def download_with_server_fallback(
    session_id: str,
    candidates: List[Dict],
    timeout_minutes: int = 3,
    custom_filename: Optional[str] = None,
) -> Dict:
    """
    Download file with automatic fallback across multiple server candidates.
    Tries each candidate in order until successful or all exhausted.
    """
    session = get_session(session_id)
    if not session:
        return {"success": False, "error": "Session not found"}

    if not session.connected:
        return {"success": False, "error": "Session not connected"}

    try:
        result = session.download_with_fallback(
            candidates, timeout_minutes, custom_filename
        )
        result["session_status"] = session.get_status()
        return result
    except Exception as e:
        return {"success": False, "error": str(e)}
