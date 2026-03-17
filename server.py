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
# Helper: MIME type
# ---------------------------------------------------------------------------
def get_content_type(file_path: str) -> str:
    """Return MIME type for file_path based on extension."""
    ext = os.path.splitext(file_path)[1].lower()
    return CONTENT_TYPES.get(ext, "application/octet-stream")


# ---------------------------------------------------------------------------
# Helper: HTTP date formatting (RFC 7231)
# ---------------------------------------------------------------------------
HTTP_DATE_FORMAT = "%a, %d %b %Y %H:%M:%S GMT"


def format_http_date(timestamp: float) -> str:
    """Convert Unix timestamp to RFC 7231 HTTP-date string (always UTC/GMT)."""
    dt = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)
    return dt.strftime(HTTP_DATE_FORMAT)


def parse_http_date(date_str: str):
    """
    Parse an HTTP-date string and return a timezone-aware UTC datetime.
    Returns None if parsing fails (tolerant of malformed client headers).
    """
    for fmt in (HTTP_DATE_FORMAT,
                "%A, %d-%b-%y %H:%M:%S GMT",   # RFC 850 (obsolete)
                "%a %b %d %H:%M:%S %Y"):        # ANSI C asctime()
        try:
            dt = datetime.datetime.strptime(date_str.strip(), fmt)
            return dt.replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Helper: 304 comparison
# ---------------------------------------------------------------------------
def should_send_304(lm_timestamp: float, ims_header: str) -> bool:
    """
    Return True if the file has NOT been modified since ims_header.

    RFC 7232: send 304 when last-modified <= If-Modified-Since.
    HTTP-dates have 1-second granularity, so truncate sub-second mtime.
    """
    ims_dt = parse_http_date(ims_header)
    if ims_dt is None:
        return False
    lm_dt = datetime.datetime.fromtimestamp(lm_timestamp, tz=datetime.timezone.utc)
    lm_dt = lm_dt.replace(microsecond=0)   # truncate to 1-second granularity
    return lm_dt <= ims_dt


# ---------------------------------------------------------------------------
# Helper: safe path resolution (directory traversal prevention)
# ---------------------------------------------------------------------------
def resolve_path(url_path: str):
    """
    Map a URL path to an absolute filesystem path inside WEB_ROOT.

    Returns the absolute path string, or None if:
      - the path escapes WEB_ROOT (traversal attempt)
      - the path contains a null byte
    """
    if "\x00" in url_path:
        return None

    # Percent-decode (e.g. %2e%2e -> ..)
    decoded = urllib.parse.unquote(url_path)

    # Strip leading slash; default to index.html for bare /
    rel = decoded.lstrip("/") or "index.html"

    # Strip query string (already handled by parse_request, but be safe)
    rel = rel.split("?")[0]

    # Resolve to canonical path (follows symlinks — prevents symlink escapes)
    fs_path = os.path.realpath(os.path.join(WEB_ROOT_REAL, rel))

    # Traversal check: canonical path must remain inside WEB_ROOT
    if fs_path != WEB_ROOT_REAL and not fs_path.startswith(WEB_ROOT_REAL + os.sep):
        return None

    return fs_path


# ---------------------------------------------------------------------------
# HTTP request parsing
# ---------------------------------------------------------------------------
def parse_request(raw: bytes):
    """
    Parse raw HTTP request bytes.

    Returns a dict {method, path, version, headers} on success.
    Returns None for any malformed input (caller sends 400).

    Notes:
      - Decodes as latin-1 (ISO-8859-1): never raises on arbitrary bytes.
      - Header names are lowercased for case-insensitive lookup.
      - Query string is stripped from path.
    """
    if not raw:
        return None

    try:
        text = raw.decode("latin-1")
    except Exception:
        return None

    # Split header block from optional body
    sep = "\r\n\r\n" if "\r\n\r\n" in text else "\n\n"
    if sep not in text:
        return None

    header_block = text.split(sep, 1)[0]
    lines = header_block.splitlines()
    if not lines:
        return None

    # --- request line ---
    parts = lines[0].split()        # split() handles any whitespace run
    if len(parts) != 3:
        return None
    method, raw_path, version = parts

    if not version.startswith("HTTP/"):
        return None

    # Strip query string from path
    path = raw_path.split("?")[0]

    # --- headers ---
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            key, _, value = line.partition(":")
            headers[key.strip().lower()] = value.strip()

    return {"method": method, "path": path, "version": version, "headers": headers}


# ---------------------------------------------------------------------------
# Low-level receive loop
# ---------------------------------------------------------------------------
def recv_request(conn: socket.socket):
    """
    Accumulate bytes from conn until the HTTP header terminator is found.

    Returns the raw byte buffer (may contain bytes past \\r\\n\\r\\n).
    Returns None if the client closed the connection (graceful FIN).
    Returns b"" (empty bytes) if headers exceed MAX_HEADER_SIZE — caller sends 400.
    Raises socket.timeout if the keep-alive idle timer fires.
    """
    buf = bytearray()
    while b"\r\n\r\n" not in buf:
        chunk = conn.recv(RECV_SIZE)
        if not chunk:
            return None   # peer closed connection (TCP FIN)
        buf.extend(chunk)
        if len(buf) > MAX_HEADER_SIZE:
            return b""    # request too large; signal 400 to caller
    return bytes(buf)


# ---------------------------------------------------------------------------
# Response building
# ---------------------------------------------------------------------------
def build_error_body(status_code: int, status_msg: str) -> bytes:
    """Return a minimal HTML error page body as UTF-8 bytes."""
    html = (
        f"<!DOCTYPE html><html><head><title>{status_code} {status_msg}</title></head>"
        f"<body><h1>{status_code} {status_msg}</h1></body></html>"
    )
    return html.encode("utf-8")


def send_response(
    conn: socket.socket,
    method: str,
    status_code: int,
    status_msg: str,
    extra_headers: dict,
    body: bytes,
    connection: str,
) -> None:
    """
    Send a complete HTTP response over conn.

    For HEAD requests: headers are sent but body is omitted (RFC 7231).
    For 304 responses: body should be None; no Content-* headers needed.
    connection must be 'keep-alive' or 'close'.
    """
    status_line = f"HTTP/1.1 {status_code} {status_msg}\r\n"
    date_header = f"Date: {format_http_date(datetime.datetime.now(datetime.timezone.utc).timestamp())}\r\n"
    conn_header = f"Connection: {connection}\r\n"

    other_headers = "".join(f"{k}: {v}\r\n" for k, v in extra_headers.items())
    header_block = (status_line + date_header + conn_header + other_headers + "\r\n").encode("latin-1")

    conn.sendall(header_block)

    if method != "HEAD" and body is not None:
        # Chunked file send to avoid loading huge files fully into memory
        view = memoryview(body)
        offset = 0
        while offset < len(body):
            conn.sendall(view[offset: offset + 65536])
            offset += 65536


# ---------------------------------------------------------------------------
# Thread-safe logging
# ---------------------------------------------------------------------------
def write_log(client_ip: str, access_time: str, requested_file: str, response_status: int) -> None:
    """Append one access log entry (thread-safe via log_lock)."""
    entry = f"{client_ip}  {access_time}  {requested_file}  {response_status}\n"
    with log_lock:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry)


# ---------------------------------------------------------------------------
# File serving logic
# ---------------------------------------------------------------------------
def serve_file(method: str, fs_path: str, req_headers: dict) -> tuple:
    """
    Attempt to serve fs_path.

    Returns (status_code, status_msg, response_headers_dict, body_bytes).
    body_bytes may be None (for 304) or an HTML error page (for 4xx).
    send_response() is responsible for omitting body on HEAD requests.
    """
    # 404 — file does not exist
    if not os.path.isfile(fs_path):
        body = build_error_body(404, "Not Found")
        return 404, "Not Found", {
            "Content-Type": "text/html",
            "Content-Length": str(len(body)),
        }, body

    # 403 — file exists but is not readable
    if not os.access(fs_path, os.R_OK):
        body = build_error_body(403, "Forbidden")
        return 403, "Forbidden", {
            "Content-Type": "text/html",
            "Content-Length": str(len(body)),
        }, body

    # File metadata
    lm_timestamp = os.path.getmtime(fs_path)
    last_modified = format_http_date(lm_timestamp)
    content_type = get_content_type(fs_path)

    # 304 — If-Modified-Since check
    ims_str = req_headers.get("if-modified-since")
    if ims_str and should_send_304(lm_timestamp, ims_str):
        return 304, "Not Modified", {"Last-Modified": last_modified}, None

    # 200 — read and send file
    with open(fs_path, "rb") as fh:
        body = fh.read()

    return 200, "OK", {
        "Content-Type": content_type,
        "Content-Length": str(len(body)),
        "Last-Modified": last_modified,
    }, body


# ---------------------------------------------------------------------------
# Worker thread — full implementation
# ---------------------------------------------------------------------------
def handle_connection(conn: socket.socket, addr: tuple) -> None:
    """
    Worker thread: handle one client connection (potentially many requests).

    Implements HTTP/1.1 persistent connections (keep-alive) and graceful
    handling of Connection: close, timeouts, and malformed requests.
    """
    client_ip = addr[0]
    conn.settimeout(KEEP_ALIVE_TIMEOUT)

    try:
        while True:
            # ----------------------------------------------------------------
            # 1. Receive request headers
            # ----------------------------------------------------------------
            try:
                raw = recv_request(conn)
            except socket.timeout:
                return   # keep-alive idle timer fired; close silently

            if raw is None:
                return   # client closed connection (graceful FIN)

            access_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if raw == b"":
                # Headers exceeded MAX_HEADER_SIZE — send 400 and close
                body = build_error_body(400, "Bad Request")
                send_response(conn, "GET", 400, "Bad Request",
                              {"Content-Type": "text/html",
                               "Content-Length": str(len(body))},
                              body, "close")
                write_log(client_ip, access_time, "-", 400)
                return

            # ----------------------------------------------------------------
            # 2. Parse request
            # ----------------------------------------------------------------
            parsed = parse_request(raw)
            if parsed is None:
                body = build_error_body(400, "Bad Request")
                send_response(conn, "GET", 400, "Bad Request",
                              {"Content-Type": "text/html",
                               "Content-Length": str(len(body))},
                              body, "close")
                write_log(client_ip, access_time, "-", 400)
                return   # always close after 400

            method  = parsed["method"]
            path    = parsed["path"]
            version = parsed["version"]
            req_hdr = parsed["headers"]

            # ----------------------------------------------------------------
            # 3. Determine connection persistence
            # ----------------------------------------------------------------
            conn_hdr = req_hdr.get("connection", "").lower()
            if version == "HTTP/1.1":
                keep_alive = conn_hdr != "close"
            elif version == "HTTP/1.0":
                keep_alive = conn_hdr == "keep-alive"
            else:
                keep_alive = False
            connection = "keep-alive" if keep_alive else "close"

            # ----------------------------------------------------------------
            # 4. Dispatch by method
            # ----------------------------------------------------------------
            if method not in ("GET", "HEAD"):
                # Unsupported method — respond with 400
                body = build_error_body(400, "Bad Request")
                send_response(conn, "GET", 400, "Bad Request",
                              {"Content-Type": "text/html",
                               "Content-Length": str(len(body))},
                              body, "close")
                write_log(client_ip, access_time, path, 400)
                return

            fs_path = resolve_path(path)
            if fs_path is None:
                # Path traversal attempt → 403
                body = build_error_body(403, "Forbidden")
                send_response(conn, method, 403, "Forbidden",
                              {"Content-Type": "text/html",
                               "Content-Length": str(len(body))},
                              body, connection)
                write_log(client_ip, access_time, path, 403)
            else:
                status, msg, resp_headers, body = serve_file(method, fs_path, req_hdr)
                send_response(conn, method, status, msg, resp_headers, body, connection)
                write_log(client_ip, access_time, path, status)

            # ----------------------------------------------------------------
            # 5. Loop or close
            # ----------------------------------------------------------------
            if not keep_alive:
                return

    except (BrokenPipeError, ConnectionResetError):
        pass   # client disconnected mid-transfer — log nothing, exit cleanly
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
