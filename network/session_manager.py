"""
Session Manager

Manages network sessions for stateful protocol fuzzing.
"""

import socket
import time
import logging
from typing import Optional, Dict


logger = logging.getLogger("fawkes.network.session")


class SessionManager:
    """
    Manages network sessions for protocol fuzzing.

    Features:
    - TCP/UDP connection management
    - Session state tracking
    - Timeout handling
    - Connection pooling
    """

    def __init__(self, host: str, port: int, protocol: str = "TCP", timeout: int = 5):
        """
        Initialize session manager.

        Args:
            host: Target host
            port: Target port
            protocol: Protocol (TCP or UDP)
            timeout: Socket timeout in seconds
        """
        self.host = host
        self.port = port
        self.protocol = protocol.upper()
        self.timeout = timeout
        self.logger = logging.getLogger(f"fawkes.network.session.{host}:{port}")

        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.session_data: Dict = {}

    def connect(self) -> bool:
        """
        Establish connection to target.

        Returns:
            True if connection successful
        """
        try:
            if self.protocol == "TCP":
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            elif self.protocol == "UDP":
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            else:
                self.logger.error(f"Unknown protocol: {self.protocol}")
                return False

            self.socket.settimeout(self.timeout)

            if self.protocol == "TCP":
                self.socket.connect((self.host, self.port))

            self.connected = True
            self.logger.info(f"Connected to {self.host}:{self.port} via {self.protocol}")
            return True

        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            self.connected = False
            return False

    def send(self, data: bytes) -> bool:
        """
        Send data to target.

        Args:
            data: Data to send

        Returns:
            True if send successful
        """
        if not self.connected or not self.socket:
            self.logger.warning("Not connected")
            return False

        try:
            if self.protocol == "TCP":
                self.socket.sendall(data)
            elif self.protocol == "UDP":
                self.socket.sendto(data, (self.host, self.port))

            self.logger.debug(f"Sent {len(data)} bytes")
            return True

        except Exception as e:
            self.logger.error(f"Send failed: {e}")
            self.connected = False
            return False

    def receive(self, size: int = 4096) -> Optional[bytes]:
        """
        Receive data from target.

        Args:
            size: Maximum bytes to receive

        Returns:
            Received data or None on error
        """
        if not self.connected or not self.socket:
            self.logger.warning("Not connected")
            return None

        try:
            if self.protocol == "TCP":
                data = self.socket.recv(size)
            elif self.protocol == "UDP":
                data, addr = self.socket.recvfrom(size)

            self.logger.debug(f"Received {len(data)} bytes")
            return data

        except socket.timeout:
            self.logger.debug("Receive timeout")
            return b""

        except Exception as e:
            self.logger.error(f"Receive failed: {e}")
            self.connected = False
            return None

    def send_and_receive(self, data: bytes, recv_size: int = 4096) -> Optional[bytes]:
        """
        Send data and receive response.

        Args:
            data: Data to send
            recv_size: Maximum bytes to receive

        Returns:
            Received response or None
        """
        if not self.send(data):
            return None

        # Small delay to allow response
        time.sleep(0.1)

        return self.receive(recv_size)

    def close(self):
        """Close connection."""
        if self.socket:
            try:
                self.socket.close()
                self.logger.info("Connection closed")
            except:
                pass

        self.socket = None
        self.connected = False

    def is_connected(self) -> bool:
        """Check if connection is active."""
        return self.connected

    def reset(self):
        """Reset session (close and reconnect)."""
        self.close()
        return self.connect()

    def set_session_data(self, key: str, value):
        """Store session-specific data."""
        self.session_data[key] = value

    def get_session_data(self, key: str, default=None):
        """Retrieve session-specific data."""
        return self.session_data.get(key, default)

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


# Convenience function
def create_session(host: str, port: int, protocol: str = "TCP") -> SessionManager:
    """
    Quick function to create session.

    Args:
        host: Target host
        port: Target port
        protocol: Protocol (TCP/UDP)

    Returns:
        SessionManager instance

    Example:
        >>> with create_session("example.com", 80) as session:
        ...     session.send(b"GET / HTTP/1.1\\r\\n\\r\\n")
        ...     response = session.receive()
    """
    return SessionManager(host, port, protocol)


# Testing
if __name__ == "__main__":
    # Test with example.com (HTTP)
    print("Testing HTTP session:")

    session = SessionManager("example.com", 80, "TCP", timeout=5)

    if session.connect():
        # Send HTTP request
        request = b"GET / HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n"
        response = session.send_and_receive(request, recv_size=1024)

        if response:
            print(f"Received {len(response)} bytes:")
            print(response.decode('utf-8', errors='ignore')[:200])

        session.close()
    else:
        print("Connection failed")

    # Test context manager
    print("\nTesting context manager:")
    with create_session("example.com", 80) as session:
        if session.is_connected():
            print("Connected successfully")
