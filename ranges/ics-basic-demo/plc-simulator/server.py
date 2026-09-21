"""Deliberately small, read-only PLC status simulator for an isolated lab."""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

STATUS = {
    "name": os.getenv("PLC_NAME", "PLC-01"),
    "area": os.getenv("PLC_AREA", "Pretreatment"),
    "mode": "simulation",
    "running": True,
    "tags": {"pump_01": "stopped", "tank_level_pct": 62.5, "alarm": False},
}

class StatusHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/health", "/api/status"):
            self.send_error(404)
            return
        payload = json.dumps(STATUS).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        return

HTTPServer(("0.0.0.0", 8081), StatusHandler).serve_forever()
