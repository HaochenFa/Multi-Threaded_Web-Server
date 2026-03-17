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

How to Test
-----------
  # GET text file (200 OK)
  curl -v http://127.0.0.1:8080/index.html

  # GET image file (200 OK)
  curl -v http://127.0.0.1:8080/image.png

  # HEAD request (200 OK, no body)
  curl -I http://127.0.0.1:8080/index.html

  # 304 Not Modified
  curl -H "If-Modified-Since: Sat, 01 Jan 2030 00:00:00 GMT" \
       http://127.0.0.1:8080/index.html

  # 404 Not Found
  curl http://127.0.0.1:8080/doesnotexist.html

  # 403 Forbidden (requires a file with no read permission)
  chmod 000 www/secret.txt
  curl http://127.0.0.1:8080/secret.txt

  # 400 Bad Request
  printf "BADREQUEST\r\n\r\n" | nc 127.0.0.1 8080

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
