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
        port: int = 6667,
        channel: str = "#ebooks",
    ):
        self.server = server
        self.port = port
        self.channel = channel
        self.socket = None
        self.nickname = self._generate_random_nickname()
        self.connected = False
        self.last_command_time = 0
        self.rate_limit_delay = 10  # Increased to match openbooks (minimum 10 seconds)
        self.download_dir = "downloads"
        self.session_id = f"irc_session_{int(time.time())}"

        # Initialize parsers
        self.search_parser = SearchResultParser()

        # Thread-safe status tracking
        self._status_lock = threading.RLock()
        self._status = {
            "connected": False,
            "last_activity": None,
            "total_searches": 0,
            "total_downloads": 0,
            "errors": [],
        }

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
        """Connect to IRC server and join channel."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(30)

            print(
                f"[IRC] Connecting to {self.server}:{self.port} as {self.nickname}..."
            )
            self.socket.connect((self.server, self.port))

            # Send connection commands
            self.socket.send(f"NICK {self.nickname}\r\n".encode())
            self.socket.send(f"USER {self.nickname} 0 * :{self.nickname}\r\n".encode())

            # Wait for connection confirmation
            connected = False
            retries = 0
            max_retries = 3

            while not connected and retries < max_retries:
                try:
                    resp = self.socket.recv(2048).decode(errors="ignore")
                    print(f"[IRC] {resp.strip()}")

                    if "004" in resp or "Welcome" in resp:
                        connected = True
                    elif "433" in resp:  # Nickname in use
                        self.nickname = self._generate_random_nickname()
                        print(f"[IRC] Trying new nickname: {self.nickname}")
                        self.socket.send(f"NICK {self.nickname}\r\n".encode())
                        retries += 1
                    elif "ERROR" in resp:
                        raise Exception(f"IRC connection error: {resp}")

                except socket.timeout:
                    retries += 1
                    print(f"[IRC] Connection timeout, retry {retries}/{max_retries}")

            if not connected:
                raise Exception("Failed to connect after maximum retries")

            # Join channel
            self.socket.send(f"JOIN {self.channel}\r\n".encode())
            print(f"[IRC] Joined channel {self.channel}")

            self.connected = True
            self._update_status({"connected": True, "nickname": self.nickname})

            # Start background listener for responses
            self._start_response_listener()

            return True

        except Exception as e:
            error_msg = f"Failed to connect to IRC: {str(e)}"
            print(f"[IRC] {error_msg}")
            self._update_status({"connected": False, "errors": [error_msg]})
            if self.socket:
                self.socket.close()
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
        """Process IRC responses for search results and DCC offers."""
        lines = response.strip().split("\n")

        for line in lines:
            line = line.strip()

            # Check for DCC SEND offers
            if DCCHandler.is_dcc_message(line):
                self._handle_dcc_offer(line)

            # Store potential search results
            if self._is_potential_search_result(line):
                self._store_search_result(line)

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

    def search_books(self, author: str, title: Optional[str] = None) -> List[Dict]:
        """Search for books using @search command with enhanced parsing."""
        if not self.connected or not self.socket:
            raise Exception("Not connected to IRC")

        self._enforce_rate_limit()

        # Clear previous search results
        self._search_results = []
        self._dcc_offers = []

        # Format search command (based on openbooks patterns)
        if title:
            search_query = f"@search {author} {title}"
        else:
            search_query = f"@search {author}"

        print(f"[IRC] Searching: {search_query}")

        # Send search command
        self.socket.send(f"PRIVMSG {self.channel} :{search_query}\r\n".encode())

        # Wait for search results (longer timeout like openbooks)
        print("[IRC] Waiting for search results...")
        time.sleep(15)  # Give more time for results to come in

        # Parse collected results
        if hasattr(self, "_search_results") and self._search_results:
            books, parse_errors = self.search_parser.parse_search_results(
                self._search_results
            )

            # Filter results if specific criteria provided
            if author or title:
                filter_term = f"{author} {title}".strip()
                books = self.search_parser.filter_results(
                    books, author_filter=filter_term
                )

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
                    }
                )

            # Log parsing errors for debugging
            if parse_errors:
                print(f"[IRC] {len(parse_errors)} parsing errors occurred")
                for error in parse_errors[:5]:  # Log first 5 errors
                    print(f"[IRC] Parse error: {error.error} - {error.line[:100]}")

            self._update_status({"total_searches": self._status["total_searches"] + 1})

            print(f"[IRC] Search completed. Found {len(results)} books.")
            return results

        else:
            print("[IRC] No search results received")
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
        self.socket.settimeout(60)  # 1 minute timeout for DCC offer

        start_time = time.time()
        while time.time() - start_time < 60:
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
            downloaded_size = DCCHandler.download_file(dcc_offer, file_path)

            if downloaded_size > 0:
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
                }
            else:
                error_msg = "DCC download failed - no data received"
                print(f"[IRC] {error_msg}")
                return {"success": False, "error": error_msg}

        except Exception as e:
            error_msg = f"DCC download failed: {str(e)}"
            print(f"[IRC] {error_msg}")
            return {"success": False, "error": error_msg}

    def _extract_zip(self, zip_path: str) -> List[str]:
        """Extract a zip file and return list of extracted files."""
        extracted_files = []
        try:
            extract_dir = os.path.splitext(zip_path)[0] + "_extracted"
            os.makedirs(extract_dir, exist_ok=True)

            with zipfile.ZipFile(zip_path, "r") as zip_file:
                zip_file.extractall(extract_dir)
                extracted_files = [
                    os.path.join(extract_dir, name) for name in zip_file.namelist()
                ]

            print(f"[IRC] Extracted {len(extracted_files)} files to {extract_dir}")

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
        self._update_status({"connected": False})
        print(f"[IRC] Disconnected session {self.session_id}")


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
        if session.connect():
            print(f"[IRC] Session {session.session_id} connected successfully")
        else:
            print(f"[IRC] Session {session.session_id} failed to connect")

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
