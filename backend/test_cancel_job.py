"""Cancellation core checks without requiring the web framework locally."""
import ast
import json
import multiprocessing
import re
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path


class HTTPError(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code


class CancelTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name) / "12345678-1234-1234-1234-123456789abc"
        self.directory.mkdir()
        self.process = None
        # Exercise the actual endpoint and file-state functions in isolation
        # from FastAPI, which is installed in the Docker image, not this runtime.
        tree = ast.parse(Path(__file__).with_name("app.py").read_text(encoding="utf-8"))
        names = {"job_path", "write_status", "cancel_job"}
        functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        for node in functions:
            node.decorator_list = []
        self.namespace = dict(Path=Path, re=re, json=json, datetime=datetime, timezone=timezone,
                              HTTPException=HTTPError, DATA_DIR=Path(self.temporary.name),
                              STATUS_LOCK=threading.Lock(), JOB_LOCK=threading.Lock(), JOB_PROCESSES={})
        exec(compile(ast.Module(body=functions, type_ignores=[]), "app.py", "exec"), self.namespace)

    def tearDown(self):
        if self.process and self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=2)
        self.temporary.cleanup()

    def status(self, state):
        self.namespace["write_status"](self.directory, state, state, 0)

    def cancel(self):
        return self.namespace["cancel_job"](self.directory.name)

    def test_stops_blocked_process_and_keeps_artifacts(self):
        self.status("running")
        (self.directory / "source.png").write_bytes(b"original")
        (self.directory / "output.txt").write_text("partial answer", encoding="utf-8")
        self.process = multiprocessing.get_context("spawn").Process(target=time.sleep, args=(30,))
        self.process.start()
        self.namespace["JOB_PROCESSES"][self.directory.name] = self.process
        self.assertEqual(self.cancel()["status"], "cancelled")
        self.assertFalse(self.process.is_alive())
        self.assertEqual((self.directory / "source.png").read_bytes(), b"original")
        self.assertEqual((self.directory / "output.txt").read_text(encoding="utf-8"), "partial answer")
        self.assertEqual(self.cancel()["status"], "cancelled")

    def test_queued_job_can_be_cancelled_before_process_starts(self):
        self.status("queued")
        self.assertEqual(self.cancel()["status"], "cancelled")

    def test_completed_job_is_preserved(self):
        self.status("completed")
        self.assertEqual(self.cancel()["status"], "completed")

    def test_timestamps_survive_terminal_update_and_old_heartbeat_removed(self):
        self.status("queued")
        self.status("running")
        before = json.loads((self.directory / "status.json").read_text(encoding="utf-8"))
        before["events"].append({"stage": "GLM 正在推理，服务仍在等待结构化结果（已等待 5 秒）"})
        (self.directory / "status.json").write_text(json.dumps(before), encoding="utf-8")
        self.status("completed")
        after = json.loads((self.directory / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(after["started_at"], before["started_at"])
        self.assertEqual(after["created_at"], before["created_at"])
        self.assertIsNotNone(after["finished_at"])
        self.assertFalse(any("服务仍在等待结构化结果" in event["stage"] for event in after["events"]))


if __name__ == "__main__":
    unittest.main()
