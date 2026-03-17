#!/usr/bin/env python3
"""
make_report.py — Generate COMP2322 project report PDF.

Steps:
  1. Start server.py as a background subprocess on port 8080
  2. Run curl/socket commands to capture live demo output
  3. Stop server
  4. Build report.pdf using reportlab Platypus

Usage:
  python make_report.py
"""

import os
import subprocess
import sys
import time

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, inch
from reportlab.platypus import (
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    HRFlowable,
    PageBreak,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Configuration — edit these before generating the final PDF
# ---------------------------------------------------------------------------
STUDENT_NAME = "Billy Fang"
STUDENT_ID   = "22104780"
REPORT_PATH  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report.pdf")
SERVER_PORT  = 8080
BASE_URL     = f"http://127.0.0.1:{SERVER_PORT}"

PROJECT_DIR  = os.path.dirname(os.path.abspath(__file__))
SERVER_PY    = os.path.join(PROJECT_DIR, "server.py")
LOG_FILE     = os.path.join(PROJECT_DIR, "server.log")
SECRET_TXT   = os.path.join(PROJECT_DIR, "www", "secret.txt")

MAX_OUTPUT_LINES = 50   # truncate captured output to keep PDF readable


# ---------------------------------------------------------------------------
# Demo capture
# ---------------------------------------------------------------------------

def run(cmd, shell=False, timeout=15):
    """Run a command, return combined stdout+stderr as a string."""
    result = subprocess.run(
        cmd,
        shell=shell,
        capture_output=True,
        timeout=timeout,
    )
    # Decode with errors='replace' to safely handle binary output (e.g. image bytes)
    stdout = (result.stdout or b"").decode("utf-8", errors="replace")
    stderr = (result.stderr or b"").decode("utf-8", errors="replace")
    return stdout + stderr


def truncate(text, max_lines=MAX_OUTPUT_LINES):
    """Keep first max_lines lines; append note if truncated."""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    kept = lines[:max_lines]
    omitted = len(lines) - max_lines
    kept.append(f"... [{omitted} lines omitted for brevity]")
    return "\n".join(kept)


def wrap_output(text, width=105):
    """Hard-wrap lines longer than width so Preformatted stays within page margins."""
    result = []
    for line in text.splitlines():
        while len(line) > width:
            result.append(line[:width])
            line = "  " + line[width:]   # indent continuation for readability
        result.append(line)
    return "\n".join(result)


def capture_demos():
    """
    Start server, run all demo commands, stop server.
    Returns list of (title, command_str, output_str) tuples.
    """
    demos = []

    # Start server
    print("[make_report] Starting server ...", flush=True)
    server_proc = subprocess.Popen(
        [sys.executable, SERVER_PY, str(SERVER_PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1.5)   # give it time to bind

    try:
        # ---- 1. GET text file (200) ----
        cmd_str = f'curl -v -H "Connection: close" {BASE_URL}/index.html'
        out = run(["curl", "-v", "-H", "Connection: close", f"{BASE_URL}/index.html"])
        demos.append(("GET Text File — 200 OK", cmd_str, truncate(out)))

        # ---- 2. GET image file (200) ----
        cmd_str = f'curl -v -H "Connection: close" {BASE_URL}/image.png  (binary body suppressed)'
        # --output /dev/null so binary data doesn't corrupt the terminal capture
        out = run(["curl", "-v", "-H", "Connection: close", f"{BASE_URL}/image.png",
                   "--output", "/dev/null"])
        demos.append(("GET Image File — 200 OK", cmd_str, truncate(out)))

        # ---- 3. HEAD request (200, no body) ----
        cmd_str = f'curl -I -H "Connection: close" {BASE_URL}/index.html'
        out = run(["curl", "-I", "-H", "Connection: close", f"{BASE_URL}/index.html"])
        demos.append(("HEAD Request — 200 OK (no body)", cmd_str, truncate(out)))

        # ---- 4. 304 Not Modified ----
        cmd_str = (f'curl -v -H "If-Modified-Since: Sat, 01 Jan 2030 00:00:00 GMT" '
                   f'-H "Connection: close" {BASE_URL}/index.html')
        out = run(["curl", "-v",
                   "-H", "If-Modified-Since: Sat, 01 Jan 2030 00:00:00 GMT",
                   "-H", "Connection: close",
                   f"{BASE_URL}/index.html"])
        demos.append(("If-Modified-Since / Last-Modified — 304 Not Modified",
                      cmd_str, truncate(out)))

        # ---- 5. 404 Not Found ----
        cmd_str = f'curl -v -H "Connection: close" {BASE_URL}/doesnotexist.html'
        out = run(["curl", "-v", "-H", "Connection: close",
                   f"{BASE_URL}/doesnotexist.html"])
        demos.append(("404 Not Found", cmd_str, truncate(out)))

        # ---- 6. 403 Forbidden (chmod 000 secret.txt) ----
        os.chmod(SECRET_TXT, 0o000)
        cmd_str = f'curl -v -H "Connection: close" {BASE_URL}/secret.txt'
        out = run(["curl", "-v", "-H", "Connection: close",
                   f"{BASE_URL}/secret.txt"])
        os.chmod(SECRET_TXT, 0o644)   # restore immediately
        demos.append(("403 Forbidden", cmd_str, truncate(out)))

        # ---- 7. 400 Bad Request ----
        cmd_str = ('python3 -c "import socket; s=socket.create_connection'
                   f'((\'127.0.0.1\',{SERVER_PORT})); '
                   's.sendall(b\'BADREQUEST\\r\\n\\r\\n\'); '
                   'print(s.recv(4096).decode())"')
        bad_req_code = (
            "import socket\n"
            f"s = socket.create_connection(('127.0.0.1', {SERVER_PORT}))\n"
            "s.sendall(b'BADREQUEST\\r\\n\\r\\n')\n"
            "print(s.recv(4096).decode())\n"
        )
        out = run([sys.executable, "-c", bad_req_code])
        demos.append(("400 Bad Request", cmd_str, truncate(out)))

        # ---- 8. Connection: keep-alive (persistent — two requests, one connection) ----
        cmd_str = f'curl -v {BASE_URL}/index.html {BASE_URL}/image.png --output /dev/null'
        out = run(["curl", "-v", f"{BASE_URL}/index.html", f"{BASE_URL}/image.png",
                   "--output", "/dev/null"])
        demos.append(("Connection: keep-alive (Persistent)", cmd_str, truncate(out)))

        # ---- 9. Connection: close (non-persistent) ----
        cmd_str = f'curl -v -H "Connection: close" {BASE_URL}/style.css'
        out = run(["curl", "-v", "-H", "Connection: close", f"{BASE_URL}/style.css"])
        demos.append(("Connection: close (Non-persistent)", cmd_str, truncate(out)))

    finally:
        print("[make_report] Stopping server ...", flush=True)
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()
        # ensure secret.txt is always restored
        try:
            os.chmod(SECRET_TXT, 0o644)
        except OSError:
            pass

    return demos


# ---------------------------------------------------------------------------
# PDF building
# ---------------------------------------------------------------------------

def build_pdf(demos):
    margin = 1 * inch
    pre_font_size = 7.5
    code_font_size = 8
    border_pad = 4   # must match code_style / pre_style below

    # Courier character width = 0.6 × font size (600-unit advance in a 1000-unit em)
    # Usable text width = page width − 2 margins − 2× borderPad (left+right)
    _text_w = A4[0] - 2 * margin - 2 * border_pad
    PRE_COLS  = int(_text_w / (0.6 * pre_font_size))   # chars that fit in pre_style
    CODE_COLS = int(_text_w / (0.6 * code_font_size))  # chars that fit in code_style

    doc = SimpleDocTemplate(
        REPORT_PATH,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title="COMP2322 Multi-threaded Web Server — Project Report",
        author=STUDENT_NAME,
    )

    base_styles = getSampleStyleSheet()

    # ---- custom styles ----
    h1 = ParagraphStyle(
        "H1", parent=base_styles["Heading1"],
        fontSize=16, spaceAfter=10, spaceBefore=20,
        textColor=colors.HexColor("#1a3a6b"),
    )
    h2 = ParagraphStyle(
        "H2", parent=base_styles["Heading2"],
        fontSize=13, spaceAfter=6, spaceBefore=14,
        textColor=colors.HexColor("#1a3a6b"),
    )
    h3 = ParagraphStyle(
        "H3", parent=base_styles["Heading3"],
        fontSize=11, spaceAfter=4, spaceBefore=10,
        textColor=colors.HexColor("#2c5282"),
    )
    body = ParagraphStyle(
        "Body", parent=base_styles["Normal"],
        fontSize=10, spaceAfter=6, leading=15,
    )
    code_style = ParagraphStyle(
        "Code", parent=base_styles["Code"],
        fontName="Courier", fontSize=code_font_size,
        backColor=colors.HexColor("#f5f5f5"),
        borderPad=border_pad, spaceAfter=4,
        leftIndent=0,
    )
    pre_style = ParagraphStyle(
        "Pre", parent=base_styles["Code"],
        fontName="Courier", fontSize=pre_font_size,
        backColor=colors.HexColor("#fafafa"),
        borderColor=colors.HexColor("#dddddd"),
        borderWidth=0.5, borderPad=border_pad,
        spaceAfter=8,
        leftIndent=0,
        wordWrap="CJK",        # allow breaking anywhere (needed for long lines)
    )

    story = []

    # ================================================================
    # PAGE 1 — COVER PAGE
    # ================================================================
    story.append(Spacer(1, 4 * cm))
    cover_title = ParagraphStyle(
        "CoverTitle", parent=base_styles["Normal"],
        fontSize=22, fontName="Helvetica-Bold", alignment=1,
        textColor=colors.HexColor("#1a3a6b"), spaceAfter=12,
    )
    cover_sub = ParagraphStyle(
        "CoverSub", parent=base_styles["Normal"],
        fontSize=16, fontName="Helvetica-Bold", alignment=1,
        textColor=colors.HexColor("#2c5282"), spaceAfter=8,
    )
    cover_body = ParagraphStyle(
        "CoverBody", parent=base_styles["Normal"],
        fontSize=12, alignment=1, spaceAfter=6,
    )

    story.append(Paragraph("COMP2322 Computer Networking", cover_title))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Project Report", cover_sub))
    story.append(Paragraph("Multi-threaded Web Server", cover_sub))
    story.append(Spacer(1, 1.5 * cm))
    story.append(HRFlowable(width="60%", thickness=1, color=colors.HexColor("#1a3a6b"), hAlign="CENTER"))
    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph("Submitted by:", cover_body))
    story.append(Paragraph(f"<b>{STUDENT_NAME}</b>", cover_body))
    story.append(Paragraph(f"Student ID: {STUDENT_ID}", cover_body))
    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph("Department of Computing", cover_body))
    story.append(Paragraph("The Hong Kong Polytechnic University", cover_body))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("April 2026", cover_body))
    story.append(PageBreak())

    # ================================================================
    # SECTION 1 — DESIGN SUMMARY
    # ================================================================
    story.append(Paragraph("Section 1 — Design Summary", h1))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
    story.append(Spacer(1, 0.3 * cm))

    # 1.1 Architecture Overview
    story.append(Paragraph("1.1  Architecture Overview", h2))
    story.append(Paragraph(
        "The server is implemented as a single Python file (<b>server.py</b>, ~370 lines) "
        "using the <code>socket</code> module directly — no <code>http.server</code> or "
        "<code>HTTPServer</code> class is used. "
        "The <b>main thread</b> creates a TCP socket, binds it to the configured port "
        "(default 8080), and calls <code>listen()</code>. It then loops calling "
        "<code>accept()</code>; for each incoming connection it spawns a new "
        "<code>threading.Thread</code> targeting <code>handle_connection()</code>. "
        "All worker threads are created with <code>daemon=True</code> so they are "
        "automatically reaped when the main thread exits (e.g., on Ctrl+C). "
        "Key constants: <code>KEEP_ALIVE_TIMEOUT = 30 s</code>, "
        "<code>MAX_HEADER_SIZE = 65 536 B</code>.",
        body,
    ))

    # 1.2 Multi-threading
    story.append(Paragraph("1.2  Multi-threading", h2))
    story.append(Paragraph(
        "Each accepted connection runs in its own daemon thread "
        "(<code>threading.Thread(target=handle_connection, daemon=True)</code>). "
        "This allows the server to handle multiple concurrent clients without blocking. "
        "The only shared mutable state is the log file; access is serialised with a "
        "module-level <code>threading.Lock()</code> called <code>log_lock</code>, "
        "held only during the brief <code>open()</code> + <code>write()</code> call "
        "in <code>write_log()</code>.",
        body,
    ))

    # 1.3 Request/Response Format
    story.append(Paragraph("1.3  Request / Response Format", h2))
    story.append(Paragraph(
        "<b>Receiving:</b> <code>recv_request()</code> accumulates bytes from "
        "<code>conn.recv(4096)</code> calls until the <code>\\r\\n\\r\\n</code> "
        "header terminator is found. It returns <code>None</code> on graceful FIN "
        "and <code>b\"\"</code> if headers exceed 64 KB (signals 400 to the caller). "
        "<br/><br/>"
        "<b>Parsing:</b> <code>parse_request()</code> decodes as latin-1 "
        "(safe for arbitrary bytes), splits the request-line into "
        "<i>method / path / version</i>, and builds a lowercase header dict. "
        "Returns <code>None</code> for any malformed input. "
        "<br/><br/>"
        "<b>Sending:</b> <code>send_response()</code> constructs the status line, "
        "mandatory <code>Date</code> and <code>Connection</code> headers, then "
        "appends caller-supplied extra headers. The header block is sent as "
        "encoded bytes, followed by the body (skipped for HEAD and 304 responses). "
        "Large bodies are sent in 64 KB chunks via <code>memoryview</code> slicing.",
        body,
    ))

    # 1.4 GET Text Files
    story.append(Paragraph("1.4  GET — Text Files", h2))
    story.append(Paragraph(
        "<code>serve_file()</code> opens the file in binary mode (<code>rb</code>), "
        "determines the MIME type via <code>get_content_type()</code> (based on file "
        "extension), and returns a 200 response with "
        "<code>Content-Type: text/html</code>, <code>text/css</code>, "
        "<code>text/plain</code>, etc., <code>Content-Length</code>, and "
        "<code>Last-Modified</code> headers. The complete file bytes are sent as the body.",
        body,
    ))

    # 1.5 GET Image Files
    story.append(Paragraph("1.5  GET — Image Files", h2))
    story.append(Paragraph(
        "Identical code path to text files. "
        "<code>get_content_type()</code> maps <code>.png</code> → "
        "<code>image/png</code>, <code>.jpg</code>/<code>.jpeg</code> → "
        "<code>image/jpeg</code>, <code>.gif</code> → <code>image/gif</code>. "
        "Binary mode reading ensures no byte corruption for image data.",
        body,
    ))

    # 1.6 HEAD Command
    story.append(Paragraph("1.6  HEAD Command", h2))
    story.append(Paragraph(
        "<code>handle_connection()</code> accepts both <code>GET</code> and "
        "<code>HEAD</code> methods. The same <code>serve_file()</code> path runs, "
        "producing identical headers. <code>send_response()</code> checks "
        "<code>method == \"HEAD\"</code> and skips writing the body — "
        "so only the response headers are transmitted, as required by RFC 7231.",
        body,
    ))

    # 1.7 Status Codes
    story.append(Paragraph("1.7  Status Codes", h2))

    status_data = [
        ["Code", "Meaning", "When triggered"],
        ["200 OK", "Success", "File found, readable, not cached (If-Modified-Since check fails)"],
        ["304 Not Modified", "Cached", "should_send_304() returns True (lm ≤ If-Modified-Since)"],
        ["400 Bad Request", "Malformed", "parse_request() returns None, or unsupported HTTP method"],
        ["403 Forbidden", "No read permission", "os.access(path, os.R_OK) is False"],
        ["404 Not Found", "File absent", "os.path.isfile(path) is False"],
    ]
    tbl = Table(status_data, colWidths=[3.2 * cm, 3.8 * cm, 9.5 * cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3a6b")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4fa")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 0.3 * cm))

    # 1.8 Last-Modified / If-Modified-Since
    story.append(Paragraph("1.8  Last-Modified / If-Modified-Since (304 Logic)", h2))
    story.append(Paragraph(
        "<code>format_http_date(timestamp)</code> converts a Unix mtime to an "
        "RFC 7231 HTTP-date string (e.g., <i>Mon, 17 Mar 2026 10:30:00 GMT</i>) "
        "and is used for the <code>Last-Modified</code> response header. "
        "<code>parse_http_date()</code> parses all three HTTP date formats "
        "(RFC 7231, obsolete RFC 850, and ANSI C asctime). "
        "<code>should_send_304(lm_timestamp, ims_header)</code> compares "
        "last-modified (truncated to 1-second granularity) with the parsed "
        "<code>If-Modified-Since</code> value; if lm ≤ IMS it returns <code>True</code> "
        "and the server replies 304 with only the <code>Last-Modified</code> header "
        "and no body.",
        body,
    ))

    # 1.9 Connection keep-alive / close
    story.append(Paragraph("1.9  Connection: keep-alive / close (Persistent Connections)", h2))
    story.append(Paragraph(
        "HTTP/1.1 defaults to persistent connections. "
        "<code>handle_connection()</code> runs a <code>while True</code> loop, "
        "reading, parsing, and responding to successive requests on the same socket. "
        "The loop terminates when: (a) the client sends <code>Connection: close</code> "
        "header, (b) the 30-second idle timeout fires "
        "(<code>socket.settimeout(KEEP_ALIVE_TIMEOUT)</code>), or "
        "(c) the client closes the TCP connection (recv returns <code>None</code>). "
        "For HTTP/1.0 clients, keep-alive requires an explicit "
        "<code>Connection: keep-alive</code> header.",
        body,
    ))

    # 1.10 Logging
    story.append(Paragraph("1.10  Access Logging", h2))
    story.append(Paragraph(
        "<code>write_log(client_ip, access_time, requested_file, response_status)</code> "
        "appends a tab-separated line to <code>server.log</code> for every request "
        "processed. The write is wrapped in <code>with log_lock</code> to prevent "
        "interleaved output from concurrent threads. Log format: "
        "<code>IP  YYYY-MM-DD HH:MM:SS  /path  STATUS</code>.",
        body,
    ))

    story.append(PageBreak())

    # ================================================================
    # SECTION 2 — DEMONSTRATION
    # ================================================================
    story.append(Paragraph("Section 2 — Demonstration", h1))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        "The following captures were produced by running <b>make_report.py</b>, "
        "which starts the server on port 8080 and executes each test command "
        "programmatically. Output is truncated to the first "
        f"{MAX_OUTPUT_LINES} lines for readability.",
        body,
    ))
    story.append(Spacer(1, 0.3 * cm))

    for i, (title, cmd_str, output) in enumerate(demos, start=1):
        story.append(Paragraph(f"2.{i}  {title}", h2))
        story.append(Paragraph("Command:", h3))
        story.append(Preformatted(wrap_output(cmd_str, CODE_COLS), code_style))
        story.append(Paragraph("Output:", h3))
        story.append(Preformatted(wrap_output(output, PRE_COLS) if output.strip() else "(no output)", pre_style))
        story.append(Spacer(1, 0.2 * cm))

    story.append(PageBreak())

    # ================================================================
    # SECTION 3 — LOG FILE
    # ================================================================
    story.append(Paragraph("Section 3 — Log File", h1))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        "Complete contents of <code>server.log</code> from a representative test run. "
        "One line per request: <i>client_IP  access_time  requested_file  response_status</i>.",
        body,
    ))
    story.append(Spacer(1, 0.2 * cm))

    if os.path.isfile(LOG_FILE):
        with open(LOG_FILE, encoding="utf-8") as f:
            log_content = f.read()
    else:
        log_content = "(server.log not found)"

    story.append(Preformatted(wrap_output(log_content, PRE_COLS) if log_content.strip() else "(log is empty)", pre_style))

    # ---- Build ----
    print(f"[make_report] Building {REPORT_PATH} ...", flush=True)
    doc.build(story)
    print(f"[make_report] Done — {REPORT_PATH}", flush=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("[make_report] Capturing live demos ...", flush=True)
    demos = capture_demos()
    build_pdf(demos)
