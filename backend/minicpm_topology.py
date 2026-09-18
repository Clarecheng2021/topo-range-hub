"""Reconstruct a topology candidate with MiniCPM-V only.

This deliberately does not consume OpenCV/Hough line candidates.  MiniCPM sees
the original diagram in three passes: inventory, visible-link tracing, then an
independent audit.  The result is still a candidate graph and cannot directly
configure the exercise range.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ENDPOINT = "https://api.modelbest.cn/v1/chat/completions"
DEFAULT_MODEL = "MiniCPM-V-4.5-9B"


def image_data_url(image: Path) -> str:
    mime = mimetypes.guess_type(image.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(image.read_bytes()).decode('ascii')}"


def json_from_reply(reply: str) -> dict[str, Any]:
    """Accept JSON returned bare or enclosed in a Markdown code block."""
    reply = reply.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", reply, re.DOTALL)
    if fenced:
        reply = fenced.group(1)
    start, end = reply.find("{"), reply.rfind("}")
    if start < 0 or end < start:
        raise ValueError("MiniCPM reply contains no JSON object")
    value = json.loads(reply[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("MiniCPM JSON root is not an object")
    return value


def call_minicpm(api_key: str, model: str, image_url: str, instruction: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": instruction},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]}],
    }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"MiniCPM request failed ({error.code}): {detail}") from error
    except urllib.error.URLError as error:
        raise SystemExit(f"MiniCPM request failed: {error.reason}") from error
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise SystemExit(f"Unexpected MiniCPM response: {data}") from error
    return json_from_reply(str(content))


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract visible industrial topology using MiniCPM-V.")
    parser.add_argument("image", type=Path, help="Original high-resolution topology image")
    parser.add_argument("--output", type=Path, default=Path("artifacts/topology/minicpm-candidates.topology.json"))
    parser.add_argument("--model", default=os.environ.get("MINICPM_MODEL", DEFAULT_MODEL))
    args = parser.parse_args()

    api_key = os.environ.get("MODELBEST_API_KEY")
    if not api_key:
        raise SystemExit("MODELBEST_API_KEY is not set for this PowerShell session.")
    image = args.image.expanduser().resolve()
    if not image.is_file():
        raise SystemExit(f"Image not found: {image}")
    image_url = image_data_url(image)

    inventory = call_minicpm(api_key, args.model, image_url, """You are reading an industrial network topology diagram. Work only in the requested visible area: the production industrial-control network on the right side. Identify every network device and every labelled PLC/HMI/device box that participates in a visible cable path. Assign stable short IDs (for example switch-01, plc-01), a Chinese name, type, zone, and an approximate pixel bbox [x,y,width,height]. Do NOT output any links yet. Return ONLY valid JSON: {\"zones\":[{\"id\":string,\"name\":string}],\"nodes\":[{\"id\":string,\"name\":string,\"type\":string,\"zone\":string,\"bbox\":[number,number,number,number],\"evidence\":string}]}.""")

    links = call_minicpm(api_key, args.model, image_url, """Trace only black/gray solid cable paths in the production industrial-control network on the right side of this topology diagram. Do not use proximity, text alignment, red markings, dashed zone borders, or implied engineering knowledge. A link is allowed only when one continuous visible path, including all bends, reaches two devices. Use the following device inventory exactly; do not create IDs: """ + json.dumps(inventory.get("nodes", []), ensure_ascii=False) + """. Return ONLY valid JSON: {\"links\":[{\"source\":node_id,\"target\":node_id,\"confidence\":0_to_1,\"evidence\":\"visible path description\"}],\"unresolved\":[string]}.""")

    candidate = {"zones": inventory.get("zones", []), "nodes": inventory.get("nodes", []), "links": links.get("links", [])}
    audited = call_minicpm(api_key, args.model, image_url, """Independently audit this proposed industrial-control topology against the image. Keep only nodes and links visibly supported by the original image. Delete uncertain or inferred links. Correct a source/target only if the complete visible path proves it. Preserve IDs when possible. Return ONLY valid JSON: {\"zones\": [...], \"nodes\": [{\"id\":string,\"name\":string,\"type\":string,\"zone\":string,\"bbox\":[x,y,w,h],\"confidence\":0_to_1,\"evidence\":[string]}], \"links\": [{\"id\":string,\"source\":string,\"target\":string,\"confidence\":0_to_1,\"evidence\":[string]}], \"issues\":[string]}. Proposed graph: """ + json.dumps(candidate, ensure_ascii=False))

    result = {
        "name": image.stem + "-minicpm-candidates",
        "schema_version": "0.3",
        "source": {"kind": "image", "filename": str(image), "model": args.model},
        "isolation": {"production_bridge": False, "internet_egress": False},
        "zones": audited.get("zones", candidate["zones"]),
        "nodes": audited.get("nodes", candidate["nodes"]),
        "links": audited.get("links", candidate["links"]),
        "review": {"status": "unreviewed", "issues": audited.get("issues", links.get("unresolved", []))},
    }
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Candidate nodes: {len(result['nodes'])}")
    print(f"Candidate links: {len(result['links'])}")
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
