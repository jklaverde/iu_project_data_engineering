import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .latency_tracker import LatencyTracker
from .metrics import render_prometheus_text
from .query_progress import QueryProgressTracker

logger = logging.getLogger(__name__)


def _make_handler(tracker: QueryProgressTracker, latency_tracker: LatencyTracker):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            if self.path == "/state":
                body = json.dumps(tracker.as_dict()).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/metrics":
                body = render_prometheus_text(tracker.as_dict(), latency_tracker.as_dict())
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/healthz":
                body = json.dumps({"status": "ok"}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

    return Handler


def start_state_server(tracker: QueryProgressTracker, latency_tracker: LatencyTracker, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("0.0.0.0", port), _make_handler(tracker, latency_tracker))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(json.dumps({"event": "state_server_started", "port": port}))
    return server
