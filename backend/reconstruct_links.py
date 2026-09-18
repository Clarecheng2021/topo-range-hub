"""Attach line-segment endpoints to device candidates and emit reviewable links."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np


def read_image(path: Path) -> np.ndarray:
    data = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise SystemExit(f"Image could not be read: {path}")
    return image


def point_to_box_distance(point: tuple[float, float], box: dict[str, float | int]) -> float:
    px, py = point
    x1, y1 = float(box["x"]), float(box["y"])
    x2, y2 = x1 + float(box["width"]), y1 + float(box["height"])
    return math.hypot(max(x1 - px, 0, px - x2), max(y1 - py, 0, py - y2))


def closest_node(point: tuple[float, float], nodes: list[dict[str, object]], maximum_distance: float) -> tuple[dict[str, object] | None, float]:
    nearest: dict[str, object] | None = None
    nearest_distance = maximum_distance + 1
    for node in nodes:
        distance = point_to_box_distance(point, node["bbox"])
        if distance < nearest_distance:
            nearest, nearest_distance = node, distance
    return nearest, nearest_distance


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconstruct reviewable topology links from device and line candidates.")
    parser.add_argument("image", type=Path)
    parser.add_argument("devices_json", type=Path)
    parser.add_argument("lines_json", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts") / "topology" / "link-candidates.json")
    parser.add_argument("--snap-distance", type=float, default=46, help="Maximum endpoint-to-device-box distance in pixels")
    args = parser.parse_args()

    image_path = args.image.expanduser().resolve()
    devices = json.loads(args.devices_json.expanduser().resolve().read_text(encoding="utf-8"))
    lines = json.loads(args.lines_json.expanduser().resolve().read_text(encoding="utf-8"))
    nodes = devices.get("nodes", [])
    links: list[dict[str, object]] = []
    preview = read_image(image_path)

    for segment in lines.get("segments", []):
        start = (float(segment["x1"]), float(segment["y1"]))
        end = (float(segment["x2"]), float(segment["y2"]))
        source, source_distance = closest_node(start, nodes, args.snap_distance)
        target, target_distance = closest_node(end, nodes, args.snap_distance)
        if source is None or target is None or source["id"] == target["id"]:
            continue
        confidence = min(
            0.9,
            round(float(segment.get("confidence", 0.45)) + 0.15 - (source_distance + target_distance) / 500, 2),
        )
        link = {
            "id": f"candidate-link-{len(links) + 1:03d}",
            "source": source["id"],
            "target": target["id"],
            "medium": "unknown",
            "directed": False,
            "path": [{"x": int(start[0]), "y": int(start[1])}, {"x": int(end[0]), "y": int(end[1])}],
            "confidence": confidence,
            "evidence": {
                "sources": ["detector", "line_cv", "rule"],
                "notes": [
                    f"line segment {segment['id']}",
                    f"endpoint distances: {source_distance:.1f}px, {target_distance:.1f}px",
                    "Candidate only; requires manual review.",
                ],
            },
        }
        links.append(link)
        cv2.line(preview, (int(start[0]), int(start[1])), (int(end[0]), int(end[1])), (0, 220, 0), 3, cv2.LINE_AA)

    for node in nodes:
        box = node["bbox"]
        x, y, width, height = (int(box[key]) for key in ("x", "y", "width", "height"))
        cv2.rectangle(preview, (x, y), (x + width, y + height), (255, 190, 0), 2)
        cv2.putText(preview, str(node["id"]), (x, max(16, y - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 130, 0), 1, cv2.LINE_AA)

    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    preview_path = output.with_name(output.stem + "-preview.jpg")
    output.write_text(
        json.dumps(
            {
                "source_image": str(image_path),
                "nodes": nodes,
                "links": links,
                "review": {
                    "status": "unreviewed",
                    "issues": ["Links were created only when both detected endpoints snapped to distinct device candidates."],
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    cv2.imwrite(str(preview_path), preview)
    print(f"Reviewable link candidates: {len(links)}")
    print(f"Saved JSON: {output}")
    print(f"Saved preview: {preview_path}")


if __name__ == "__main__":
    main()
