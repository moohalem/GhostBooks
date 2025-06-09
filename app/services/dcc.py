#!/usr/bin/env python3
"""
DCC (Direct Client-to-Client) Protocol Implementation
Based on the openbooks project DCC implementation
"""

import re
import socket
import struct
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class DCCDownload:
    """Container for DCC download information."""

    filename: str
    ip: str
    port: str
    size: int
    raw_line: str


class DCCHandler:
    """Handles DCC protocol for file transfers."""

    # Regex pattern for DCC SEND messages
    # Pattern matches: DCC SEND "filename" ip port size
    DCC_REGEX = re.compile(r'DCC SEND "?(.+[^"])"?\s+(\d+)\s+(\d+)\s+(\d+)\s*')

    @classmethod
    def parse_dcc_string(cls, text: str) -> Optional[DCCDownload]:
        """
        Parse DCC SEND message to extract download information.

        Args:
            text: IRC message containing DCC SEND

        Returns:
            DCCDownload object or None if parsing fails
        """
        match = cls.DCC_REGEX.search(text)
        if not match:
            return None

        try:
            filename = match.group(1)
            ip_int = int(match.group(2))
            port = match.group(3)
            size = int(match.group(4))

            # Convert integer IP to dotted decimal notation
            ip = cls._int_to_ip(ip_int)

            return DCCDownload(
                filename=filename, ip=ip, port=port, size=size, raw_line=text
            )

        except (ValueError, IndexError) as e:
            print(f"[DCC] Error parsing DCC string: {e}")
            return None

    @classmethod
    def _int_to_ip(cls, ip_int: int) -> str:
        """
        Convert 32-bit integer to IP address string.

        Args:
            ip_int: IP address as 32-bit integer

        Returns:
            IP address in dotted decimal notation
        """
        try:
            # Pack as big-endian 32-bit unsigned integer, then unpack as 4 bytes
            packed = struct.pack("!I", ip_int)
            return socket.inet_ntoa(packed)
        except (struct.error, socket.error) as e:
            print(f"[DCC] Error converting IP {ip_int}: {e}")
            return "0.0.0.0"

    @classmethod
    def download_file(
        cls, dcc: DCCDownload, output_path: str, progress_callback=None
    ) -> Dict:
        """
        Download file using DCC protocol.

        Args:
            dcc: DCCDownload object with connection info
            output_path: Local path to save the file
            progress_callback: Optional callback for progress updates

        Returns:
            Dictionary with download result
        """
        try:
            print(f"[DCC] Connecting to {dcc.ip}:{dcc.port} for {dcc.filename}")

            # Connect to DCC server
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(30)  # 30 second timeout
            sock.connect((dcc.ip, int(dcc.port)))

            # Download file
            received = 0
            buffer_size = 4096  # 4KB chunks for optimal performance

            with open(output_path, "wb") as f:
                while received < dcc.size:
                    # Read data
                    data = sock.recv(min(buffer_size, dcc.size - received))
                    if not data:
                        break

                    # Write to file
                    f.write(data)
                    received += len(data)

                    # Progress callback
                    if progress_callback:
                        progress = (received / dcc.size) * 100
                        progress_callback(received, dcc.size, progress)

            sock.close()

            # Verify download completed
            if received != dcc.size:
                return {
                    "success": False,
                    "error": f"Download incomplete: {received}/{dcc.size} bytes",
                    "received": received,
                    "expected": dcc.size,
                }

            print(f"[DCC] Successfully downloaded {dcc.filename} ({received} bytes)")

            return {
                "success": True,
                "filename": dcc.filename,
                "file_path": output_path,
                "size": received,
                "ip": dcc.ip,
                "port": dcc.port,
            }

        except Exception as e:
            error_msg = f"DCC download failed: {str(e)}"
            print(f"[DCC] {error_msg}")
            return {"success": False, "error": error_msg, "filename": dcc.filename}

    @classmethod
    def is_dcc_message(cls, text: str) -> bool:
        """
        Check if a message contains a DCC SEND command.

        Args:
            text: IRC message text

        Returns:
            True if message contains DCC SEND
        """
        return "DCC SEND" in text and cls.DCC_REGEX.search(text) is not None


# Utility functions for testing
def test_dcc_parsing():
    """Test DCC parsing with sample messages."""
    test_cases = [
        ":SearchOok!ook@only.ook PRIVMSG evan_28 :DCC SEND SearchOok_results_for__hp_lovecraft.txt.zip 1543751478 2043 784",
        ":Search!Search@ihw-4q5hcb.dyn.suddenlink.net PRIVMSG evan_bot :DCC SEND SearchBot_results_for__stephen_king.txt.zip 2907707975 4342 1116",
        ':DV8!HandyAndy@ihw-39fkft.ip-164-132-173.eu PRIVMSG user :DCC SEND "Douglas Adams - Hitchhiker\'s Guide.epub" 2760158537 2050 2321788',
    ]

    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest case {i}:")
        print(f"Input: {test_case}")

        dcc = DCCHandler.parse_dcc_string(test_case)
        if dcc:
            print("Parsed successfully:")
            print(f"  Filename: {dcc.filename}")
            print(f"  IP: {dcc.ip}")
            print(f"  Port: {dcc.port}")
            print(f"  Size: {dcc.size} bytes")
        else:
            print("Failed to parse")


if __name__ == "__main__":
    test_dcc_parsing()
