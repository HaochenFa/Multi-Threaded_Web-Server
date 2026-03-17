"""Unit tests for server.py pure helper functions."""
import server
import sys
import os
import datetime
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ===========================================================================
# parse_request
# ===========================================================================

def test_parse_valid_get():
    raw = b"GET /index.html HTTP/1.1\r\nHost: localhost\r\nConnection: keep-alive\r\n\r\n"
    r = server.parse_request(raw)
    assert r is not None
    assert r["method"] == "GET"
    assert r["path"] == "/index.html"
    assert r["version"] == "HTTP/1.1"
    assert r["headers"]["host"] == "localhost"
    assert r["headers"]["connection"] == "keep-alive"


def test_parse_valid_head():
    raw = b"HEAD /page.html HTTP/1.1\r\nHost: localhost\r\n\r\n"
    r = server.parse_request(raw)
    assert r is not None
    assert r["method"] == "HEAD"
    assert r["path"] == "/page.html"


def test_parse_malformed_no_version():
    assert server.parse_request(b"GET /index.html\r\n\r\n") is None


def test_parse_malformed_empty():
    assert server.parse_request(b"") is None


def test_parse_malformed_one_token():
    assert server.parse_request(b"BADREQUEST\r\n\r\n") is None


def test_parse_path_with_query_string():
    raw = b"GET /index.html?foo=bar HTTP/1.1\r\nHost: localhost\r\n\r\n"
    r = server.parse_request(raw)
    assert r is not None
    assert r["path"] == "/index.html"    # query string stripped


def test_parse_headers_case_insensitive():
    raw = b"GET / HTTP/1.1\r\nIf-Modified-Since: Mon, 01 Jan 2024 00:00:00 GMT\r\n\r\n"
    r = server.parse_request(raw)
    assert "if-modified-since" in r["headers"]


# ===========================================================================
# get_content_type
# ===========================================================================

def test_content_type_html():
    assert server.get_content_type("index.html") == "text/html"


def test_content_type_jpeg():
    assert server.get_content_type("photo.jpg") == "image/jpeg"
    assert server.get_content_type("photo.jpeg") == "image/jpeg"


def test_content_type_png():
    assert server.get_content_type("image.png") == "image/png"


def test_content_type_unknown():
    assert server.get_content_type("archive.xyz") == "application/octet-stream"


# ===========================================================================
# format_http_date / parse_http_date
# ===========================================================================

def test_format_http_date():
    # 2026-03-17 12:00:00 UTC → known string
    ts = datetime.datetime(2026, 3, 17, 12, 0, 0,
                           tzinfo=datetime.timezone.utc).timestamp()
    result = server.format_http_date(ts)
    assert result == "Tue, 17 Mar 2026 12:00:00 GMT"


def test_parse_http_date_valid():
    dt = server.parse_http_date("Tue, 17 Mar 2026 12:00:00 GMT")
    assert dt is not None
    assert dt.year == 2026 and dt.month == 3 and dt.day == 17


def test_parse_http_date_invalid():
    assert server.parse_http_date("not-a-date") is None


def test_parse_http_date_whitespace():
    dt = server.parse_http_date("  Tue, 17 Mar 2026 12:00:00 GMT  ")
    assert dt is not None


# ===========================================================================
# should_send_304
# ===========================================================================

def test_304_when_ims_equals_lm():
    ts = datetime.datetime(2026, 1, 1, 0, 0, 0,
                           tzinfo=datetime.timezone.utc).timestamp()
    lm_str = server.format_http_date(ts)
    assert server.should_send_304(ts, lm_str) is True


def test_304_when_ims_after_lm():
    ts = datetime.datetime(
        2020, 1, 1, tzinfo=datetime.timezone.utc).timestamp()
    future = "Sat, 01 Jan 2030 00:00:00 GMT"
    assert server.should_send_304(ts, future) is True


def test_no_304_when_ims_before_lm():
    ts = datetime.datetime(
        2026, 1, 1, tzinfo=datetime.timezone.utc).timestamp()
    past = "Sat, 01 Jan 2000 00:00:00 GMT"
    assert server.should_send_304(ts, past) is False


def test_no_304_when_ims_invalid():
    ts = datetime.datetime(
        2026, 1, 1, tzinfo=datetime.timezone.utc).timestamp()
    assert server.should_send_304(ts, "not-a-date") is False


# ===========================================================================
# resolve_path
# ===========================================================================

def test_resolve_path_normal():
    result = server.resolve_path("/index.html")
    assert result is not None
    assert result.endswith("index.html")
    assert result.startswith(server.WEB_ROOT_REAL)


def test_resolve_path_root_defaults_to_index():
    result = server.resolve_path("/")
    assert result is not None
    assert result.endswith("index.html")


def test_resolve_path_traversal_blocked():
    assert server.resolve_path("/../etc/passwd") is None


def test_resolve_path_encoded_traversal_blocked():
    assert server.resolve_path("/%2e%2e/etc/passwd") is None


def test_resolve_path_null_byte_blocked():
    assert server.resolve_path("/index.html\x00.txt") is None


# ===========================================================================
# serve_file
# ===========================================================================

def test_serve_file_200_html(tmp_path):
    f = tmp_path / "page.html"
    f.write_bytes(b"<html>hello</html>")
    status, msg, headers, body = server.serve_file("GET", str(f), {})
    assert status == 200
    assert headers["Content-Type"] == "text/html"
    assert body == b"<html>hello</html>"


def test_serve_file_head_body_returned(tmp_path):
    """serve_file always returns body; send_response omits it for HEAD."""
    f = tmp_path / "page.html"
    f.write_bytes(b"content")
    status, msg, headers, body = server.serve_file("HEAD", str(f), {})
    assert status == 200
    assert body == b"content"   # caller (send_response) omits for HEAD


def test_serve_file_404(tmp_path):
    status, msg, headers, body = server.serve_file(
        "GET", str(tmp_path / "missing.html"), {})
    assert status == 404


def test_serve_file_403(tmp_path):
    f = tmp_path / "secret.html"
    f.write_bytes(b"secret")
    f.chmod(0o000)
    try:
        status, msg, headers, body = server.serve_file("GET", str(f), {})
        assert status == 403
    finally:
        f.chmod(0o644)


def test_serve_file_304(tmp_path):
    f = tmp_path / "page.html"
    f.write_bytes(b"content")
    lm = server.format_http_date(os.path.getmtime(str(f)))
    status, msg, headers, body = server.serve_file(
        "GET", str(f), {"if-modified-since": lm})
    assert status == 304
    assert body is None


def test_serve_file_200_when_stale(tmp_path):
    f = tmp_path / "page.html"
    f.write_bytes(b"content")
    status, msg, headers, body = server.serve_file(
        "GET", str(f), {"if-modified-since": "Sat, 01 Jan 2000 00:00:00 GMT"}
    )
    assert status == 200
    assert body == b"content"


def test_serve_file_last_modified_in_headers(tmp_path):
    f = tmp_path / "page.html"
    f.write_bytes(b"content")
    _, _, headers, _ = server.serve_file("GET", str(f), {})
    assert "Last-Modified" in headers
