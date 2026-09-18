"""Direct GLM vision adapter for the topology service.

This is application code, not a Claude Code or MCP integration.  It sends an
uploaded diagram to the configured Zhipu Open Platform model and normalizes the
candidate into the local topology IR.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from backend.normalize_glm_topology import normalize, validate


DEFAULT_ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
DEFAULT_MODEL = "glm-5.3-flash"


def _image_url(image: Path) -> str:
    mime = mimetypes.guess_type(image.name)[0] or "image/png"
    data = base64.b64encode(image.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _json_from_content(content: str) -> dict[str, Any]:
    clean = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", clean, flags=re.DOTALL)
    if match:
        clean = match.group(1)
    start, end = clean.find("{"), clean.rfind("}")
    if start < 0 or end < start:
        raise ValueError("GLM did not return a JSON object")
    value = json.loads(clean[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("GLM JSON root must be an object")
    return value


def analyze(image: Path, scope: str = "生产工控网", progress: Callable[[str, int], None] | None = None, output: Callable[[str], None] | None = None, reasoning_effort: str = "low") -> dict[str, Any]:
    if reasoning_effort not in {"low", "high", "max"}:
        raise ValueError("思考强度必须为 low、high 或 max")
    report = progress or (lambda _stage, _percent: None)
    api_key = os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        raise RuntimeError("ZHIPUAI_API_KEY is not configured on the service.")
    model = os.environ.get("ZHIPU_VISION_MODEL", DEFAULT_MODEL)
    endpoint = os.environ.get("ZHIPU_API_ENDPOINT", DEFAULT_ENDPOINT)
    prompt = f"""你是工业网络拓扑识别服务。只识别图片中的「{scope}」。
沿可见的黑色或灰色实线完整追踪设备间链路，可穿过直角拐点；绝不能按文字位置、图形邻近或工控常识补全不可见连接。虚线边界和设备框边线不是链路。
仅在图片有明确区域划分或区域标签时输出 zones；没有划分则 zones 为 []，节点 zone 为 ""，不要自行添加区域。

仅输出一个 JSON 对象，不要 Markdown。使用如下候选格式：
{{
  "diagram_title": "string",
  "image_size": {{"width": number, "height": number}},
  "zones": [{{"id":"zone-id","name":"区域名","bbox":[x0,y0,x1,y1],"basis":"可见依据"}}],
  "nodes": [{{"id":"stable-id","label":"设备中文名","type":"workstation|server|firewall|switch|hmi-tag|plc-station|plc-substation|unknown","zone":"zone-id","bbox":[x0,y0,x1,y1],"note":"可见依据"}}],
  "links": [{{"id":"L01","endpoints":["node-a","node-b"],"path":"可见路径描述","style":"black solid","evidence":"端点与路径证据"}}]
}}

每个 bbox 使用原图像素 [x0,y0,x1,y1]。只输出有明确图形证据的设备与连线；对不确定边直接省略。"""
    payload = {
        "model": model,
        "temperature": 0,
        "reasoning_effort": reasoning_effort,
        "stream": True,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": _image_url(image)}},
        ]}],
    }
    report(f"正在调用 {model}（思考强度 {reasoning_effort}）识别区域、设备和可见连线", 25)
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            content = ""
            if "text/event-stream" in response.headers.get("Content-Type", ""):
                for line in response:
                    line = line.decode("utf-8").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    if chunk.get("error"):
                        raise RuntimeError(f"GLM streaming error: {chunk['error']}")
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    # Only publish the answer stream, never internal reasoning.
                    delta = choices[0].get("delta", {}).get("content")
                    if isinstance(delta, str) and delta:
                        content += delta
                        if output:
                            output(content)
            else:
                response_data = json.loads(response.read().decode("utf-8"))
                content = response_data["choices"][0]["message"]["content"]
                if output:
                    output(content)
        if not content:
            raise RuntimeError("GLM 未返回识别结果正文")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GLM API request failed ({error.code}): {detail}") from error
    except (urllib.error.URLError, KeyError, IndexError, TypeError) as error:
        raise RuntimeError(f"GLM API request failed: {error}") from error

    report("GLM 已返回结果，正在解析结构化 JSON", 72)
    raw = _json_from_content(str(content))
    raw["source_image"] = str(image)
    raw["generated_by"] = model
    report("正在标准化节点、区域与链路", 84)
    topology = normalize(raw)
    report("正在校验节点、端点和置信度", 94)
    errors = validate(topology)
    if errors:
        raise RuntimeError("GLM result failed local validation: " + "; ".join(errors))
    return topology
