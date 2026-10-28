#!/usr/bin/env python3
"""Serve the CQL Cleanroom standalone (WASM) build.

The bare SPA boots the CleanroomDemo scratch by default; the public
surfaces open the featured CMS125 example (the website embed sets
`cms125-workspace` through the host handoff, and this server mirrors
that for direct/bare hosting via the `?example=` parameter the app
already honors).

Usage: serve_cleanroom_wasm.py <dir> [--port N] [--example NAME]
"""
from __future__ import annotations

import argparse
import functools
import http.server
import os
import socketserver
from urllib.parse import parse_qs, urlparse


def make_handler(directory: str, example: str | None):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (stdlib naming)
            parsed = urlparse(self.path)
            if example and parsed.path in ("/", "/index.html") and not parsed.query:
                # One redirect: the app reads ?example= at boot.
                self.send_response(302)
                self.send_header("Location", f"/?example={example}")
                self.end_headers()
                return
            super().do_GET()

        def end_headers(self):
            # COOP/COEP for duckdb-wasm shared-memory (the app also ships
            # coi-serviceworker as a fallback when hosted without them).
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
            self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
            super().end_headers()

        def log_message(self, fmt, *args):  # keep the journal quiet
            return

    return functools.partial(Handler, directory=directory)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("directory")
    ap.add_argument("--port", type=int, default=5178)
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--example", default="cms125-workspace")
    ap.add_argument("--no-example", action="store_true")
    args = ap.parse_args()
    example = None if args.no_example else (args.example or None)
    if not os.path.isdir(args.directory):
        raise SystemExit(f"not a directory: {args.directory}")
    handler = make_handler(args.directory, example)
    with socketserver.ThreadingTCPServer((args.bind, args.port), handler) as httpd:
        print(
            f"cleanroom standalone on http://{args.bind}:{args.port}/ "
            f"(default example: {example or 'none'})",
            flush=True,
        )
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
