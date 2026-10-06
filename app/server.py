"""Small dependency-free demo service. No user commands or file access."""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class Handler(BaseHTTPRequestHandler):
    server_version = "DevSecOpsDemo"
    sys_version = ""

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/health":
            status, payload = 200, {"status": "healthy"}
        elif path == "/":
            status, payload = 200, {"project": "AWS DevSecOps", "version": "1.0"}
        else:
            status, payload = 404, {"error": "not found"}
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # JSON encoding prevents attacker-controlled URLs forging log records.
        print(json.dumps({"event": "http", "message": fmt % args}), flush=True)


def main():
    ThreadingHTTPServer((os.getenv("HOST", "127.0.0.1"), int(os.getenv("PORT", "8080"))), Handler).serve_forever()


if __name__ == "__main__":
    main()
