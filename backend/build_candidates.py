"""Convert raw PaddleOCR output into topology node and zone candidates.

This deliberately builds *candidates* only. OCR text cannot prove that two
symbols are linked, so links remain empty until the line-detection and review
stages are complete.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


DEVICE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"防火墙"), "firewall"),
    (re.compile(r"路由|行为管理"), "router"),
    (re.compile(r"工业以太网交换|交换机"), "switch"),
    (re.compile(r"工程师站"), "workstation"),
    (re.compile(r"操作员站|监控工作站"), "hmi"),
    (re.compile(r"HMI", re.IGNORECASE), "hmi"),
    (re.compile(r"PLC", re.IGNORECASE), "plc"),
    (re.compile(r"服务器"), "server"),
    (re.compile(r"摄像头|摄像机"), "camera"),
    (re.compile(r"门禁|车辆识别|访客|报警"), "security"),
    (re.compile(r"Internet|互联网", re.IGNORECASE), "internet"),
)

ZONE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"办公网"), "office"),
    (re.compile(r"安防网"), "security"),
    (re.compile(r"生产工控网|工控网"), "production"),
    (re.compile(r"泵房"), "pump-room"),
    (re.compile(r"活性炭间"), "carbon-room"),
    (re.compile(r"集团"), "group"),
)


def bbox(values: list[int]) -> dict[str, int]:
    x1, y1, x2, y2 = values
    return {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}


def find_rule(text: str, rules: tuple[tuple[re.Pattern[str], str], ...]) -> str | None:
    for pattern, value in rules:
        if pattern.search(text):
            return value
    return None


def safe_id(prefix: str, index: int) -> str:
    return f"{prefix}-{index:03d}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build topology candidates from PaddleOCR JSON.")
    parser.add_argument("ocr_json", type=Path, help="PaddleOCR JSON created by ocr_local.py")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts") / "topology" / "ocr-candidates.topology.json",
        help="Candidate topology JSON output path",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.45,
        help="Ignore OCR results below this confidence score",
    )
    args = parser.parse_args()

    raw_path = args.ocr_json.expanduser().resolve()
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    texts = raw.get("rec_texts", [])
    scores = raw.get("rec_scores", [])
    boxes = raw.get("rec_boxes", [])

    if not (len(texts) == len(scores) == len(boxes)):
        raise SystemExit("OCR result has mismatched text, score and box arrays.")

    zones = [{"id": "unknown", "name": "待确认区域", "level": "unknown"}]
    nodes: list[dict[str, object]] = []
    seen_zone_ids = {"unknown"}

    for index, (text, score, raw_box) in enumerate(zip(texts, scores, boxes), start=1):
        text = str(text).strip()
        confidence = float(score)
        if not text or confidence < args.min_score:
            continue

        text_box = bbox([int(value) for value in raw_box])
        zone_id = find_rule(text, ZONE_RULES)
        if zone_id and zone_id not in seen_zone_ids:
            zones.append(
                {
                    "id": zone_id,
                    "name": text,
                    "bbox": text_box,
                    "confidence": confidence,
                    "evidence": {"sources": ["ocr"], "text": text},
                }
            )
            seen_zone_ids.add(zone_id)

        device_type = find_rule(text, DEVICE_RULES)
        if not device_type:
            continue

        nodes.append(
            {
                "id": safe_id(device_type, index),
                "name": text,
                "type": device_type,
                "zone": "unknown",
                "bbox": text_box,
                "position": {
                    "x": text_box["x"] + text_box["width"] / 2,
                    "y": text_box["y"] + text_box["height"] / 2,
                },
                "confidence": confidence,
                "evidence": {"sources": ["ocr"], "text": text},
            }
        )

    topology = {
        "name": raw_path.stem.replace("_res", "") + "-ocr-candidates",
        "title": "OCR 设备与区域候选（等待人工复核）",
        "schema_version": "0.3",
        "source": {"kind": "image", "filename": raw.get("input_path", "")},
        "isolation": {"production_bridge": False, "internet_egress": False},
        "zones": zones,
        "nodes": nodes,
        "links": [],
        "review": {
            "status": "unreviewed",
            "issues": [
                "当前版本仅使用 OCR 文字生成设备候选。",
                "链路必须等待 OpenCV 连线检测和人工复核，不能由文字结果臆造。",
                "所有设备所属区域默认为待确认区域。",
            ],
        },
    }

    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(topology, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Candidate zones: {len(zones) - 1}")
    print(f"Candidate nodes: {len(nodes)}")
    print("Candidate links: 0 (intentionally deferred to line detection)")
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
