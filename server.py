#!/usr/bin/env python3
"""
COMP2322 Computer Networking — Multi-threaded Web Server

Uses raw socket programming only. No http.server / HTTPServer.
Run: python server.py [port]   (default port 8080)
"""
import socket
import threading
import os
import sys
import datetime
import urllib.parse

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_PORT    = 8080
WEB_ROOT        = os.path.join(os.path.dirname(os.path.abspath(__file__)), "www")
WEB_ROOT_REAL   = os.path.realpath(WEB_ROOT)   # resolved once; used in traversal check
LOG_FILE        = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.log")
KEEP_ALIVE_TIMEOUT = 30    # seconds before idle persistent connection is closed
RECV_SIZE       = 4096     # bytes per recv() call
MAX_HEADER_SIZE = 65536    # reject requests whose headers exceed 64 KB

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------
log_lock = threading.Lock()   # serialises writes to server.log

# ---------------------------------------------------------------------------
# MIME type table
# ---------------------------------------------------------------------------
CONTENT_TYPES = {
    ".html": "text/html",      ".htm": "text/html",
    ".css":  "text/css",       ".js":  "application/javascript",
    ".jpg":  "image/jpeg",     ".jpeg":"image/jpeg",
    ".png":  "image/png",      ".gif": "image/gif",
    ".ico":  "image/x-icon",   ".txt": "text/plain",
}

# ---------------------------------------------------------------------------
# Stub worker (replaced in Task 3)
# ---------------------------------------------------------------------------
def handle_connection(conn: socket.socket, addr: tuple) -> None:
    """Worker thread — handles one client connection."""
    try:
        conn.recv(RECV_SIZE)   # discard for now
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT

    if not os.path.isdir(WEB_ROOT):
        print(f"[WARNING] Web root does not exist: {WEB_ROOT}")

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("", port))
    server_sock.listen(128)
    print(f"[server] Listening on port {port}  (web root: {WEB_ROOT})")
    print("[server] Press Ctrl+C to stop.")

    try:
        while True:
            conn, addr = server_sock.accept()
            t = threading.Thread(
                target=handle_connection,
                args=(conn, addr),
                daemon=True,    # dies automatically when main thread exits
            )
            t.start()
    except KeyboardInterrupt:
        print("\n[server] Shutting down.")
    finally:
        server_sock.close()


if __name__ == "__main__":
    main()
