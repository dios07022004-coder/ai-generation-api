"""Тестовый приёмник callback'ов: проверяет HMAC-подпись и печатает результат.
Только для проверки доставки в dev. Слушает :9000, секрет из WEBHOOK_SIGNING_SECRET.
"""
import hashlib
import hmac
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

SECRET = os.environ["WEBHOOK_SIGNING_SECRET"].encode()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        ts = self.headers.get("X-Webhook-Timestamp", "")
        sig = self.headers.get("X-Webhook-Signature", "")
        expected = hmac.new(SECRET, f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
        ok = hmac.compare_digest(expected, sig)
        print(f"CALLBACK_RECEIVED signature_valid={ok} body={body.decode()}", flush=True)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *a):
        pass


HTTPServer(("0.0.0.0", 9000), Handler).serve_forever()
