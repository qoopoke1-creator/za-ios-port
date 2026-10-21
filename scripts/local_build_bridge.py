#!/usr/bin/env python3
"""Temporary authenticated loopback bridge for one cloud build, no directory listing."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('config', type=Path)
    args = ap.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8'))
    source, dest = Path(config['input']), Path(config['output'])
    token = config['token']

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def authorized(self):
            return hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token)

        def do_GET(self):
            if not self.authorized() or self.path != '/input':
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Length', str(source.stat().st_size))
            self.end_headers()
            with source.open('rb') as f:
                while chunk := f.read(1024 * 1024):
                    self.wfile.write(chunk)

        def do_PUT(self):
            if not self.authorized() or self.path != '/output':
                self.send_error(404)
                return
            try:
                length = int(self.headers.get('Content-Length', '-1'))
            except ValueError:
                length = -1
            if not 0 < length <= 4 * 2**30:
                self.send_error(413)
                return
            temp = dest.with_suffix('.partial')
            left = length
            with temp.open('wb') as f:
                while left:
                    data = self.rfile.read(min(left, 1024 * 1024))
                    if not data:
                        self.send_error(400)
                        return
                    f.write(data)
                    left -= len(data)
            temp.replace(dest)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')

    ThreadingHTTPServer(('127.0.0.1', config['port']), Handler).serve_forever()


if __name__ == '__main__':
    main()
