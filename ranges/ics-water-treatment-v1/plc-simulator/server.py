"""Safe, deterministic PLC process simulator for the local training range."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATE_PATH = Path("/data/state.json")
LOCK = threading.RLock()


def fresh_state():
    now = time.time()
    return {
        "scenario": "water-treatment-v1", "simulation": True,
        "tank_level_pct": 58.0, "pump_running": False,
        "alarm": None, "acknowledged": False, "last_tick": now,
        "events": [{"at": now, "kind": "system", "message": "模拟 PLC 已启动"}],
    }


def load_state():
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        state.setdefault("events", [])
        state["last_tick"] = time.time()
        return state
    except (FileNotFoundError, json.JSONDecodeError):
        return fresh_state()


STATE = load_state()


def event(kind, message):
    STATE["events"].append({"at": time.time(), "kind": kind, "message": message})
    STATE["events"] = STATE["events"][-30:]


def tick():
    now = time.time()
    seconds = min(now - STATE.get("last_tick", now), 30)
    STATE["last_tick"] = now
    delta = 1.25 if STATE["pump_running"] else -0.45
    STATE["tank_level_pct"] = round(max(0, min(100, STATE["tank_level_pct"] + delta * seconds)), 1)
    previous = STATE.get("alarm")
    level = STATE["tank_level_pct"]
    STATE["alarm"] = "HIGH_LEVEL" if level >= 85 else "LOW_LEVEL" if level <= 25 else None
    if STATE["alarm"] and STATE["alarm"] != previous:
        STATE["acknowledged"] = False
        event("alarm", f"液位告警：{STATE['alarm']}")


def snapshot():
    tick()
    STATE_PATH.write_text(json.dumps(STATE, ensure_ascii=False), encoding="utf-8")
    return {key: value for key, value in STATE.items() if key != "last_tick"}


def command(action):
    tick()
    if action == "start_pump":
        STATE["pump_running"] = True
        event("operator", "操作员启动进水泵")
    elif action == "stop_pump":
        STATE["pump_running"] = False
        event("operator", "操作员停止进水泵")
    elif action == "acknowledge_alarm":
        STATE["acknowledged"] = True
        event("operator", "操作员确认当前告警")
    elif action == "reset_scenario":
        STATE.clear()
        STATE.update(fresh_state())
    else:
        raise ValueError("unsupported action")
    return snapshot()


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        with LOCK:
            if self.path == "/health":
                self.respond(200, {"ok": True, "simulation": True})
            elif self.path == "/api/v1/status":
                self.respond(200, snapshot())
            else:
                self.respond(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/v1/command":
            self.respond(404, {"error": "not found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(size) or b"{}")
            with LOCK:
                self.respond(200, command(request.get("action")))
        except (ValueError, json.JSONDecodeError):
            self.respond(400, {"error": "invalid command"})

    def log_message(self, format, *args):
        return


ThreadingHTTPServer(("0.0.0.0", 8081), Handler).serve_forever()