"""Extract a reviewable industrial topology graph with a multimodal model.

Unlike ``detect_lines.py``, this adapter asks a vision-capable model to reason
about devices and complete cable paths together.  PaddleOCR evidence is passed
alongside the image so small Chinese labels remain available to the model.

The model output is a candidate graph, never a deployment instruction.  It is
kept isolated from the range compiler until a reviewer approves it.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import urllib.error
import urllib.request
from pathlib import Path


TOPOLOGY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "zones", "nodes", "links", "review"],
    "properties": {
        "name": {"type": "string"},
        "zones": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "name", "confidence"],
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "confidence": {"type": "number"},
                },
            },
        },
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "name", "type", "zone", "bbox", "confidence", "evidence"],
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": [
                            "internet", "firewall", "router", "switch", "industrial_switch", "server",
                            "workstation", "hmi", "scada", "historian", "opc_server", "plc", "rtu",
                            "dcs", "sis", "camera", "security", "display", "sensor", "actuator",
                            "drive", "robot", "io", "unknown",
                        ],
                    },
                    "zone": {"type": "string"},
                    "bbox": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["x", "y", "width", "height"],
                        "properties": {
                            "x": {"type": "number"}, "y": {"type": "number"},
                            "width": {"type": "number"}, "height": {"type": "number"},
                        },
                    },
                    "confidence": {"type": "number"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "links": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "source", "target", "confidence", "evidence"],
                "properties": {
                    "id": {"type": "string"}, "source": {"type": "string"},
                    "target": {"type": "string"}, "confidence": {"type": "number"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "review": {
            "type": "object",
            "additionalProperties": False,
            "required": ["status", "issues"],
            "properties": {
                "status": {"type": "string", "enum": ["unreviewed"]},
                "issues": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
}


def load_ocr_evidence(path: Path | None) -> list[dict[str, object]]:
    if path is None:
        return []
    raw = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    evidence: list[dict[str, object]] = []
    for text, score, box in zip(raw.get("rec_texts", []), raw.get("rec_scores", []), raw.get("rec_boxes", [])):
        if str(text).strip() and float(score) >= 0.45:
            evidence.append({"text": str(text).strip(), "score": round(float(score), 2), "box": [int(value) for value in box]})
    return evidence


def data_url(image: Path) -> str:
    mime_type = mimetypes.guess_type(image.name)[0] or "image/png"
    encoded = base64.b64encode(image.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def request_body(model: str, image: Path, ocr_evidence: list[dict[str, object]]) -> dict[str, object]:
    instruction = """You are an industrial network-topology analyst. Inspect the supplied topology image as a graph, not as a collection of arbitrary straight lines. Return only devices and links visibly supported by the image. Trace each link through bends before choosing source and target. Do not infer invisible links, credentials, IP addresses, protocols, vendor details, or production configuration. Use OCR evidence only as supporting text; prefer the image when OCR conflicts. For every link, evidence must state the visible device names and a concise description of the observed path. Omit uncertain links rather than guessing. The output is always unreviewed."""
    return {
        "model": model,
        "instructions": instruction,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Extract a topology graph from this image. OCR evidence follows:\n" + json.dumps(ocr_evidence, ensure_ascii=False),
                    },
                    {"type": "input_image", "image_url": data_url(image), "detail": "high"},
                ],
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "industrial_topology_candidate",
                "strict": True,
                "schema": TOPOLOGY_SCHEMA,
            }
        },
        "store": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract a candidate topology graph with a multimodal model.")
    parser.add_argument("image", type=Path, help="PNG, JPEG, WebP, or SVG topology image")
    parser.add_argument("--ocr-json", type=Path, help="Optional PaddleOCR result JSON")
    parser.add_argument("--output", type=Path, default=Path("artifacts") / "topology" / "vlm-candidates.topology.json")
    parser.add_argument("--model", default=os.environ.get("OPENAI_VISION_MODEL", "gpt-5"))
    parser.add_argument("--endpoint", default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1/responses"))
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set. Set it for this shell before running the VLM parser.")

    image = args.image.expanduser().resolve()
    if not image.is_file():
        raise SystemExit(f"Image not found: {image}")
    ocr_path = args.ocr_json.expanduser().resolve() if args.ocr_json else None
    payload = json.dumps(request_body(args.model, image, load_ocr_evidence(ocr_path)), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        args.endpoint,
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            raw_response = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Vision API request failed ({error.code}): {detail}") from error
    except urllib.error.URLError as error:
        raise SystemExit(f"Vision API request failed: {error.reason}") from error

    output_text = raw_response.get("output_text")
    if not output_text:
        raise SystemExit("Vision API returned no structured output.")
    topology = json.loads(output_text)
    topology["schema_version"] = "0.3"
    topology["source"] = {"kind": "image", "filename": str(image)}
    topology["isolation"] = {"production_bridge": False, "internet_egress": False}
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(topology, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Candidate zones: {len(topology['zones'])}")
    print(f"Candidate nodes: {len(topology['nodes'])}")
    print(f"Candidate links: {len(topology['links'])}")
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
