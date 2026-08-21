"""Minimal MJPEG-over-HTTP server for the live view stream.

Standard library only: the camera link is the interesting part of this
project, not the web server.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger(__name__)

BOUNDARY = "skyshutterframe"

INDEX_PAGE = b"""<!doctype html>
<title>skyshutter live view</title>
<style>body{margin:0;background:#111;display:flex;height:100vh;align-items:center;
justify-content:center}img{max-width:100%;max-height:100%}</style>
<img src="/stream.mjpg" alt="live view">
"""


class FrameBuffer:
    """Holds the most recent frame and wakes up waiting clients."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._frame: bytes | None = None
        self._sequence = 0
        self._closed = False

    def publish(self, frame: bytes) -> None:
        with self._condition:
            self._frame = frame
            self._sequence += 1
            self._condition.notify_all()

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def frames(self, timeout: float = 5.0) -> Iterator[bytes]:
        last = 0
        while True:
            with self._condition:
                if not self._condition.wait_for(
                    lambda seen=last: self._closed or self._sequence != seen, timeout=timeout
                ):
                    continue
                if self._closed:
                    return
                last = self._sequence
                frame = self._frame
            if frame:
                yield frame


def make_handler(buffer: FrameBuffer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: object) -> None:
            log.debug("%s - %s", self.address_string(), fmt % args)

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(INDEX_PAGE)))
                self.end_headers()
                self.wfile.write(INDEX_PAGE)
            elif self.path.startswith("/stream.mjpg"):
                self._stream()
            else:
                self.send_error(404)

        def _stream(self) -> None:
            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={BOUNDARY}")
            self.end_headers()
            try:
                for frame in buffer.frames():
                    self.wfile.write(f"--{BOUNDARY}\r\n".encode())
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                log.debug("client disconnected")

    return Handler


def serve(buffer: FrameBuffer, host: str = "0.0.0.0", port: int = 8080) -> ThreadingHTTPServer:
    """Start the MJPEG server on a background thread and return it."""
    server = ThreadingHTTPServer((host, port), make_handler(buffer))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name="mjpeg", daemon=True).start()
    return server
