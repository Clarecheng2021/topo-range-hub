"""Contract checks for the streaming answer adapter, without paid API calls."""
import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.glm_topology import analyze


class Response(io.BytesIO):
    def __init__(self, body, content_type="text/event-stream"):
        super().__init__(body)
        self.headers = {"Content-Type": content_type}


class StreamingTests(unittest.TestCase):
    @patch.dict(os.environ, {"ZHIPUAI_API_KEY": "test-only"})
    def test_incremental_answer_ignores_reasoning(self):
        chunks = [
            {"choices": [{"delta": {"reasoning_content": "private reasoning"}}]},
            {"choices": [{"delta": {"content": '{"nodes":'}}]},
            {"choices": [{"delta": {"content": '[],"links":[]}'}}]},
        ]
        body = ("\n\n".join("data: " + json.dumps(c) for c in chunks) + "\n\ndata: [DONE]\n\n").encode()
        seen = []
        with patch("backend.glm_topology._image_url", return_value="data:image/png;base64,test"), \
             patch("backend.glm_topology.urllib.request.urlopen", return_value=Response(body)) as request, \
             patch("backend.glm_topology.normalize", side_effect=lambda raw: raw), \
             patch("backend.glm_topology.validate", return_value=[]):
            result = analyze(Path("test.png"), output=seen.append)
        self.assertEqual(seen, ['{"nodes":', '{"nodes":[],"links":[]}'])
        self.assertEqual(result["nodes"], [])
        self.assertTrue(json.loads(request.call_args.args[0].data)["stream"])
        self.assertEqual(json.loads(request.call_args.args[0].data)["reasoning_effort"], "low")

    @patch.dict(os.environ, {"ZHIPUAI_API_KEY": "test-only"})
    def test_stream_error_is_not_success(self):
        body = b'data: {"error":{"message":"invalid model"}}\n\n'
        with patch("backend.glm_topology._image_url", return_value="test"), \
             patch("backend.glm_topology.urllib.request.urlopen", return_value=Response(body)):
            with self.assertRaisesRegex(RuntimeError, "invalid model"):
                analyze(Path("test.png"))

    @patch.dict(os.environ, {"ZHIPUAI_API_KEY": "test-only"})
    def test_selected_effort_reaches_upstream(self):
        for effort in ("low", "high", "max"):
            with self.subTest(effort=effort), \
                 patch("backend.glm_topology._image_url", return_value="test"), \
                 patch("backend.glm_topology.urllib.request.urlopen", return_value=Response(b'{"choices":[{"message":{"content":"{}"}}]}', "application/json")) as request, \
                 patch("backend.glm_topology.normalize", return_value={}), \
                 patch("backend.glm_topology.validate", return_value=[]):
                analyze(Path("test.png"), reasoning_effort=effort)
                self.assertEqual(json.loads(request.call_args.args[0].data)["reasoning_effort"], effort)
        with self.assertRaises(ValueError):
            analyze(Path("test.png"), reasoning_effort="medium")


if __name__ == "__main__":
    unittest.main()
