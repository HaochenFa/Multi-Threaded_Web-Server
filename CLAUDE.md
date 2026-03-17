# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

COMP2322 Computer Networking — Multi-threaded Web Server (due April 26, 2026, 11:59 pm).

Build a multi-threaded HTTP web server from scratch in Python using raw socket programming. **Do NOT use Python's `http.server` / `HTTPServer` class** — use `socket` module directly.

## Running the Server

```bash
python server.py [port]        # Start server (default port 8080)
python server.py 8080
```

Test with browser at `http://127.0.0.1:8080/` or use curl:

```bash
curl -v http://127.0.0.1:8080/index.html          # GET text file
curl -v http://127.0.0.1:8080/image.jpg           # GET image file
curl -I http://127.0.0.1:8080/index.html          # HEAD request
curl -H "If-Modified-Since: Sat, 01 Jan 2000 00:00:00 GMT" http://127.0.0.1:8080/index.html  # 304 test
curl -H "Connection: close" http://127.0.0.1:8080/index.html   # non-persistent
```

## Required HTTP Features (Graded — 70 marks total)

| Feature | Marks | Status Codes |
|---------|-------|-------------|
| Multi-threaded (one thread per connection) | 5 | — |
| Proper request/response message format | 5 | — |
| GET text files | 5 | 200 OK |
| GET image files | 5 | 200 OK |
| HEAD command | 5 | 200 OK (no body) |
| 200 OK | 5 | — |
| 400 Bad Request | 5 | — |
| 403 Forbidden | 5 | — |
| 404 Not Found | 5 | — |
| 304 Not Modified | 5 | — |
| Last-Modified response header | 5 | — |
| If-Modified-Since request header | 5 | — |
| Connection: keep-alive (persistent) | 5 | — |
| Connection: close (non-persistent) | 5 | — |

**Only these 5 status codes are allowed:** 200, 304, 400, 403, 404.

## Architecture

- **Main thread**: listens on TCP socket, accepts connections, spawns a new thread per connection
- **Worker thread**: parses HTTP request, serves file, writes to log, closes or keeps connection
- **Log file** (`server.log`): one line per request — `client_IP  access_time  requested_file  response_status`
- **Web root**: `www/` directory containing served files (HTML + at least one image)

## Key Implementation Details

- Parse `Last-Modified` response header and `If-Modified-Since` request header for 304 logic; compare dates to decide whether to send 200 or 304
- `Connection: keep-alive` → loop reading requests on same socket until `Connection: close` or timeout; `Connection: close` → close socket after response
- Binary mode (`rb`) for reading files — handles both text and images correctly; send response headers as encoded bytes then file bytes
- Set `Content-Type` based on file extension: `.html`/`.htm` → `text/html`, `.jpg`/`.jpeg` → `image/jpeg`, `.png` → `image/png`, `.gif` → `image/gif`, `.css` → `text/css`, etc.
- Thread safety: use a `threading.Lock` when writing to the shared `server.log`
- 400 Bad Request: malformed request line (wrong format, missing method/path/version)
- 403 Forbidden: file exists but is not readable (check with `os.access(path, os.R_OK)`)
- 404 Not Found: file does not exist at the requested path

## Submission Checklist

- [ ] `server.py` — complete source with comments
- [ ] `www/` — sample web files for testing (HTML + at least one image)
- [ ] `server.log` — example log from a test run
- [ ] `README.txt` — how to compile/run
- [ ] Project report (PDF) — cover page, design summary, screenshots of all features, log file sample
