#!/usr/bin/env python3
"""
IRC service for Calibre Library Monitor
Handles IRC connections and book searches with download functionality
"""

import os
import random
import re
import socket
import string
import threading
import time
import zipfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

import requests

# Thread-safe IRC search status management
_irc_search_status = {}
_status_lock = threading.RLock()


def _get_search_status_safe(search_id: str) -> dict:
    """Thread-safe getter for search status."""
    with _status_lock:
        return _irc_search_status.get(search_id, {}).copy()


def _update_search_status_safe(search_id: str, updates: dict) -> None:
    """Thread-safe updater for search status."""
    with _status_lock:
        if search_id not in _irc_search_status:
            _irc_search_status[search_id] = {}
        _irc_search_status[search_id].update(updates)


def _set_search_status_safe(search_id: str, status: dict) -> None:
    """Thread-safe setter for search status."""
    with _status_lock:
        _irc_search_status[search_id] = status.copy()


def connect_to_irc(
    server: str,
    port: int,
    channel: str,
    nickname: str = "WebDarkHorse",
    realname: str = "WebDarkHorse",
    password: str | None = None,
) -> socket.socket:
    """Connect to IRC server and join channel."""
    irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    print(f"[IRC] Connecting to {server}:{port}...")
    irc.connect((server, port))
    irc.send(f"NICK {nickname}\r\n".encode())
    irc.send(f"USER {nickname} 0 * :{realname or nickname}\r\n".encode())
    if password:
        irc.send(f"PASS {password}\r\n".encode())
    connected = False
    while not connected:
        resp = irc.recv(2048).decode(errors="ignore")
        print(f"[IRC] {resp.strip()}")
        if "004" in resp or "Welcome" in resp:
            connected = True
        elif "433" in resp:
            print(f"[IRC] Nickname {nickname} is already in use.")
            nickname = nickname + "_"
            irc.send(f"NICK {nickname}\r\n".encode())
    irc.send(f"JOIN {channel}\r\n".encode())
    print(f"[IRC] Joined channel {channel}")
    return irc


def search_author_on_irc_and_download_zip(
    irc: socket.socket, author: str, download_dir: str = "downloads"
) -> Set[str]:
    """Search for an author by name on IRC and download the zip file with book listings."""
    # Search by author name (not book title)
    search_cmd = f"@find {author}\r\n"
    irc.send(search_cmd.encode())
    print(f"[IRC] Searching for AUTHOR: '{author}' (not individual book titles)")
    print(f"[IRC] Sent search command: {search_cmd.strip()}")

    link = None
    irc.settimeout(60)
    try:
        while True:
            resp = irc.recv(4096).decode(errors="ignore")
            print(f"[IRC] {resp.strip()}")
            match = re.search(r"(https?://\S+\.zip)", resp)
            if match:
                link = match.group(1)
                print(f"[IRC] Found zip link for author '{author}': {link}")
                break
    except socket.timeout:
        print(f"[IRC] Timeout waiting for zip link for author '{author}'.")
        return set()

    if not link:
        print(f"[IRC] No zip link found for author '{author}'.")
        return set()

    os.makedirs(download_dir, exist_ok=True)
    zip_path = os.path.join(download_dir, f"{author.replace(' ', '_')}.zip")
    print(f"[DOWNLOAD] Downloading zip file for author '{author}' to {zip_path} ...")

    try:
        r = requests.get(link, timeout=30)
        with open(zip_path, "wb") as f:
            f.write(r.content)
        print(f"[DOWNLOAD] Download complete for author '{author}'.")
    except Exception as e:
        print(f"[DOWNLOAD] Error downloading zip for author '{author}': {e}")
        return set()

    found_titles = set()
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            for name in z.namelist():
                if name.lower().endswith(".txt"):
                    with z.open(name) as txtfile:
                        text = txtfile.read().decode(errors="ignore")
                        for line in text.splitlines():
                            line = line.strip()
                            if (
                                3 < len(line) < 120
                                and not line.islower()
                                and not line.isupper()
                            ):
                                found_titles.add(line.lower())
    except Exception as e:
        print(f"[PARSE] Error parsing zip file for author '{author}': {e}")
        return set()

    print(
        f"[PARSE] Found {len(found_titles)} possible titles in downloaded text files for author '{author}'."
    )
    return found_titles


def start_irc_search(author: str) -> str:
    """Start IRC search for an author in a separate thread."""
    search_id = f"{author}_{int(time.time())}"

    # Initialize search status using thread-safe function
    _set_search_status_safe(
        search_id,
        {
            "status": "starting",
            "author": author,
            "message": "Initializing IRC search...",
            "start_time": time.time(),
        },
    )

    def search_thread():
        try:
            _update_search_status_safe(
                search_id, {"status": "connecting", "message": "Connecting to IRC..."}
            )

            # Connect to IRC
            irc = connect_to_irc("irc.irchighway.net", 6667, "#ebooks")

            _update_search_status_safe(
                search_id,
                {"status": "searching", "message": f"Searching for {author}..."},
            )

            # Search and download
            found_titles = search_author_on_irc_and_download_zip(irc, author)

            irc.close()

            _update_search_status_safe(
                search_id,
                {
                    "status": "completed",
                    "message": f"Found {len(found_titles)} titles",
                    "found_titles": list(found_titles),
                },
            )

        except Exception as e:
            _update_search_status_safe(
                search_id, {"status": "error", "message": f"Error: {str(e)}"}
            )

    thread = threading.Thread(target=search_thread)
    thread.daemon = True
    thread.start()

    return search_id


def get_search_status(search_id: str) -> dict:
    """Get the status of an IRC search."""
    return _get_search_status_safe(search_id) or {
        "status": "not_found",
        "message": "Search not found",
    }
