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
        self, download_command: str, custom_filename: Optional[str] = None
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
                    extracted_files = self._extract_zip(file_path)

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

    def _extract_zip(self, zip_path: str) -> List[str]:
        """Extract a zip file and return list of extracted EPUB files only (openbooks pattern)."""
        extracted_files = []
        try:
            extract_dir = os.path.splitext(zip_path)[0] + "_extracted"
            os.makedirs(extract_dir, exist_ok=True)

            with zipfile.ZipFile(zip_path, "r") as zip_file:
                # Filter for .epub files only (openbooks alignment)
                epub_files = [
                    name
                    for name in zip_file.namelist()
                    if name.lower().endswith(".epub")
                ]

                if not epub_files:
                    print(f"[IRC] No EPUB files found in zip archive: {zip_path}")
                    return extracted_files

                # Extract only EPUB files
                for epub_file in epub_files:
                    zip_file.extract(epub_file, extract_dir)
                    extracted_files.append(os.path.join(extract_dir, epub_file))

                print(
                    f"[IRC] Extracted {len(extracted_files)} EPUB files to {extract_dir}"
                )

        except Exception as e:
            print(f"[IRC] Extraction failed: {e}")

        return extracted_files

    def disconnect(self) -> None:
        """Disconnect from IRC server."""
        if self.socket:
            try:
                self.socket.send(b"QUIT :Goodbye\r\n")
                self.socket.close()
            except Exception:
                pass

        self.connected = False
        self.joined_channel = False
        self._update_status({"connected": False, "joined_channel": False})
        print(f"[IRC] Disconnected session {self.session_id}")

    def is_healthy(self) -> bool:
        """Check if IRC session is healthy and responsive (openbooks pattern)."""
        if not self.connected or not self.socket:
            return False

        try:
            # Send a simple PING to test connection
            self.socket.send(f"PING :{self.server}\r\n".encode())
            return True
        except Exception:
            return False

    def get_connection_info(self) -> Dict:
        """Get detailed connection information (openbooks pattern)."""
        return {
            "session_id": self.session_id,
            "server": self.server,
            "port": self.port,
            "channel": self.channel,
            "nickname": self.nickname,
            "connected": self.connected,
            "joined_channel": self.joined_channel,
            "tls_enabled": self.enable_tls,
            "search_bot": self.search_bot,
            "user_agent": self.user_agent,
            "rate_limit_delay": self.rate_limit_delay,
            "last_command_time": self.last_command_time,
            "is_healthy": self.is_healthy(),
        }

    def search_epub_only(self, search_query: str, max_results: int = 50) -> List[Dict]:
        """
        Search for books and return only EPUB results (openbooks pattern).

        Args:
            search_query: The search term
            max_results: Maximum number of results to return

        Returns:
            List of BookDetail objects for EPUB files only
        """
        print(f"[IRC] Searching for EPUB files only: '{search_query}'")

        # Perform standard search (correct parameter order: author first)
        results = self.search_books(search_query, None, max_results)

        # Filter for EPUB only using the search_parser
        if hasattr(self, "search_parser"):
            # Convert dict results back to BookDetail objects for filtering
            book_objects = []
            for result in results:
                if isinstance(result, dict):
                    # Create a mock BookDetail-like object for filtering
                    book_obj = type(
                        "BookDetail",
                        (),
                        {
                            "format": result.get("format", "unknown"),
                            "author": result.get("author", ""),
                            "title": result.get("title", ""),
                            "server": result.get("server", ""),
                            "size": result.get("size", ""),
                            "full_command": result.get("download_command", ""),
                            "raw_line": result.get("raw_line", ""),
                        },
                    )()
                    book_objects.append(book_obj)

            epub_book_objects = self.search_parser.filter_results(
                book_objects, epub_only=True, min_quality=True
            )

            # Convert back to dict format
            epub_results = []
            for book in epub_book_objects:
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
                    }
                )
        else:
            # Fallback filter if search_parser not available
            epub_results = [r for r in results if r.get("format", "").lower() == "epub"]

        print(
            f"[IRC] Found {len(epub_results)} EPUB results out of {len(results)} total"
        )
        return epub_results

    def download_epub_only(
        self, download_command: str, output_dir: Optional[str] = None
    ) -> dict:
        """
        Download a file and ensure it's an EPUB (openbooks pattern).

        Args:
            download_command: IRC download command
            output_dir: Directory to save the file

        Returns:
            Download result dictionary with success status
        """
        print(f"[IRC] Starting EPUB-only download: {download_command}")

        # Perform standard download
        result = self.download_file(download_command, output_dir)

        if result.get("success") and "file_path" in result:
            file_path = result["file_path"]

            # Check if it's an EPUB file
            if file_path.lower().endswith(".epub"):
                print(f"[IRC] Downloaded EPUB file: {file_path}")
                return result

            # If it's a zip, extract only EPUB files
            elif file_path.lower().endswith(".zip"):
                print(f"[IRC] Extracting EPUB files from zip: {file_path}")
                epub_files = self._extract_zip(file_path)

                if epub_files:
                    result["extracted_files"] = epub_files
                    result["epub_count"] = len(epub_files)
                    print(f"[IRC] Successfully extracted {len(epub_files)} EPUB files")
                    return result
                else:
                    error_msg = "No EPUB files found in archive"
                    print(f"[IRC] {error_msg}")
                    return {
                        "success": False,
                        "error": error_msg,
                        "file_path": file_path,
                    }

            # Non-EPUB file downloaded
            else:
                error_msg = f"Downloaded file is not EPUB format: {file_path}"
                print(f"[IRC] {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "file_path": file_path,
                    "note": "File downloaded but not EPUB format",
                }

        # Download failed
        return result


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
