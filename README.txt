COMP2322 Multi-threaded Web Server
===================================

Requirements
------------
Python 3.9 or later (standard library only -- no external packages required)

How to Run
----------
  python server.py            # uses default port 8080
  python server.py 8080       # explicit port

Open a browser at:  http://127.0.0.1:8080/

Setup for Testing
-----------------
  # Generate www/image.png if missing (run once)
  python make_image.py

  # Prepare secret.txt for the 403 Forbidden test
  echo "This file is used to test HTTP 403 Forbidden." > www/secret.txt
  chmod 000 www/secret.txt
  # Restore after testing:
  chmod 644 www/secret.txt

How to Test
-----------
  # GET text file (200 OK)
  curl -v http://127.0.0.1:8080/index.html

  # GET CSS file (200 OK, Content-Type: text/css)
  curl -v http://127.0.0.1:8080/style.css

  # GET image file (200 OK)
  curl -v http://127.0.0.1:8080/image.png

  # HEAD request (200 OK, no body)
  curl -I http://127.0.0.1:8080/index.html

  # 304 Not Modified
  curl -H "If-Modified-Since: Sat, 01 Jan 2030 00:00:00 GMT" \
       http://127.0.0.1:8080/index.html

  # 404 Not Found
  curl http://127.0.0.1:8080/doesnotexist.html

  # 403 Forbidden (requires www/secret.txt with chmod 000 -- see Setup above)
  curl http://127.0.0.1:8080/secret.txt

  # 400 Bad Request (macOS-compatible -- nc lacks -q flag on macOS)
  python3 -c "import socket; s=socket.create_connection(('127.0.0.1',8080)); s.sendall(b'BADREQUEST\r\n\r\n'); print(s.recv(4096).decode())"

  # Connection: close (non-persistent)
  curl -H "Connection: close" -v http://127.0.0.1:8080/index.html

  # Connection: keep-alive (persistent, HTTP/1.1 default)
  curl -v http://127.0.0.1:8080/index.html http://127.0.0.1:8080/image.png

Log File
--------
server.log is created automatically. Format:
  client_IP  access_time  requested_file  response_status

Example:
  127.0.0.1  2026-03-17 12:00:00  /index.html  200
