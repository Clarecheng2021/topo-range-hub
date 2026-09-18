"""Build visual device-box candidates for topology diagrams.

This baseline detector combines OCR labels with the blue/red device artwork
used by the demo diagrams.  It is intentionally an adapter boundary: a trained
YOLO detector can later replace ``colour_components`` without changing link
reconstruction or the topology schema.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import cv2
import numpy as np


TEXT_TYPES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"防火墙"), "firewall"),
    (re.compile(r"工业以太网交换|交换机"), "switch"),
    (re.compile(r"工程师站"), "workstation"),
    (re.compile(r"操作站|HMI", re.IGNORECASE), "hmi"),
    (re.compile(r"PLC", re.IGNORECASE), "plc"),
    (re.compile(r"服务器|数据站"), "server"),
)


def infer_type(text: str) -> str | None:
    for pattern, device_type in TEXT_TYPES:
        if pattern.search(text):
            return device_type
    return None


def read_image(path: Path) -> np.ndarray:
    data = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise SystemExit(f"Image could not be read: {path}")
    return image


def colour_components(image: np.ndarray) -> list[dict[str, object]]:
    """Find blue HMI/switch art and orange firewall art, excluding thin dashes."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    masks = {
        "blue": cv2.inRange(hsv, (90, 85, 35), (130, 255, 255)),
        "firewall": cv2.bitwise_or(
            cv2.inRange(hsv, (0, 105, 80), (22, 255, 255)),
            cv2.inRange(hsv, (170, 105, 80), (180, 255, 255)),
        ),
    }
    candidates: list[dict[str, object]] = []
    for kind, mask in masks.items():
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x, y, width, height = cv2.boundingRect(contour)
            area = width * height
            if area < 600 or width < 28 or height < 16:
                continue
            if kind == "firewall":
                device_type = "firewall"
            elif width / height >= 2.1:
                device_type = "switch"
            else:
                device_type = "hmi"
            candidates.append(
                {
                    "type": device_type,
                    "bbox": {"x": x, "y": y, "width": width, "height": height},
                    "confidence": 0.62,
                    "evidence": {"sources": ["detector"], "notes": ["colour-shape baseline detector"]},
                }
            )
    return candidates


def box_center(box: dict[str, float | int]) -> tuple[float, float]:
    return float(box["x"]) + float(box["width"]) / 2, float(box["y"]) + float(box["height"]) / 2


def distance_to_box(point: tuple[float, float], box: dict[str, float | int]) -> float:
    px, py = point
    x1, y1 = float(box["x"]), float(box["y"])
    x2, y2 = x1 + float(box["width"]), y1 + float(box["height"])
    return math.hypot(max(x1 - px, 0, px - x2), max(y1 - py, 0, py - y2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate device-box candidates from a topology image and OCR JSON.")
    parser.add_argument("image", type=Path)
    parser.add_argument("ocr_json", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts") / "devices" / "device-candidates.json")
    args = parser.parse_args()

    image_path = args.image.expanduser().resolve()
    raw = json.loads(args.ocr_json.expanduser().resolve().read_text(encoding="utf-8"))
    image = read_image(image_path)
    visual_nodes = colour_components(image)

    text_nodes: list[dict[str, object]] = []
    for index, (text, score, box) in enumerate(zip(raw.get("rec_texts", []), raw.get("rec_scores", []), raw.get("rec_boxes", [])), start=1):
        device_type = infer_type(str(text))
        if not device_type or float(score) < 0.45:
            continue
        x1, y1, x2, y2 = (int(value) for value in box)
        text_nodes.append(
            {
                "id": f"ocr-{device_type}-{index:03d}",
                "name": str(text).strip(),
                "type": device_type,
                "bbox": {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1},
                "confidence": round(float(score), 2),
                "evidence": {"sources": ["ocr"], "text": str(text).strip()},
            }
        )

    nodes: list[dict[str, object]] = []
    consumed_text_ids: set[str] = set()
    for index, node in enumerate(visual_nodes, start=1):
        center = box_center(node["bbox"])
        compatible = [item for item in text_nodes if item["type"] == node["type"]]
        nearest = min(compatible, key=lambda item: distance_to_box(center, item["bbox"]), default=None)
        node["id"] = f"visual-{node['type']}-{index:03d}"
        node["name"] = node["type"]
        if nearest and distance_to_box(center, nearest["bbox"]) <= 120:
            node["name"] = nearest["name"]
            node["confidence"] = min(0.9, round(float(node["confidence"]) + 0.2, 2))
            node["evidence"] = {
                "sources": ["detector", "ocr"],
                "text": nearest["name"],
                "notes": ["colour-shape baseline detector matched to OCR label"],
            }
            consumed_text_ids.add(str(nearest["id"]))
        nodes.append(node)

    # PLC boxes are usually monochrome, so retain their OCR box as a fallback
    # candidate with a small expansion.  These boxes can later be replaced by
    # a trained detector without changing consumers.
    for item in text_nodes:
        if item["id"] in consumed_text_ids or item["type"] not in {"plc", "hmi", "workstation", "server"}:
            continue
        box = dict(item["bbox"])
        box["x"] -= 18
        box["y"] -= 14
        box["width"] += 36
        box["height"] += 28
        item["bbox"] = box
        item["evidence"] = {"sources": ["ocr", "rule"], "text": item["name"], "notes": ["expanded OCR fallback box"]}
        nodes.append(item)

    for node in nodes:
        x, y = box_center(node["bbox"])
        node["position"] = {"x": round(x, 1), "y": round(y, 1)}

    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "source_image": str(image_path),
                "nodes": nodes,
                "review_note": "Visual boxes are device candidates, not confirmed assets. Replace this baseline adapter with a trained detector for arbitrary topology artwork.",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Device candidates: {len(nodes)}")
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
