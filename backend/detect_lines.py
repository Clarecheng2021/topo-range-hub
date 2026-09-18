"""Extract conservative line-segment candidates from a topology image.

The output is evidence for later graph reconstruction, not a list of confirmed
network links. Topology images contain device rectangles and zone borders that
look like cables, so a human-review stage remains required.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import cv2
import numpy as np


# Text labels are useful anchors for judging whether a line is likely to be a
# cable.  They are deliberately broad: this is still a candidate generator,
# not a final topology reconstructor.
DEVICE_TEXT = re.compile(
    r"HMI|PLC|交换机|防火墙|工程师站|操作站|数据站|服务器|路由",
    re.IGNORECASE,
)


def point_to_segment_distance(point: tuple[float, float], segment: dict[str, float | int | str]) -> float:
    """Return the Euclidean distance between a point and an axis-aligned segment."""
    px, py = point
    x1, y1 = float(segment["x1"]), float(segment["y1"])
    x2, y2 = float(segment["x2"]), float(segment["y2"])
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def merge_collinear_segments(
    segments: list[dict[str, float | int | str]], coordinate_tolerance: int = 8, gap_tolerance: int = 32
) -> list[dict[str, float | int | str]]:
    """Merge Hough fragments that belong to the same horizontal/vertical cable."""
    merged: list[dict[str, float | int | str]] = []
    for orientation in ("horizontal", "vertical"):
        pool = [item.copy() for item in segments if item["orientation"] == orientation]
        pool.sort(key=lambda item: (float(item["y1"] if orientation == "horizontal" else item["x1"]), float(item["x1"] if orientation == "horizontal" else item["y1"])))
        while pool:
            current = pool.pop(0)
            axis = "y1" if orientation == "horizontal" else "x1"
            start_axis = "x1" if orientation == "horizontal" else "y1"
            end_axis = "x2" if orientation == "horizontal" else "y2"
            changed = True
            while changed:
                changed = False
                for candidate in list(pool):
                    same_row = abs(float(candidate[axis]) - float(current[axis])) <= coordinate_tolerance
                    candidate_start = min(float(candidate[start_axis]), float(candidate[end_axis]))
                    candidate_end = max(float(candidate[start_axis]), float(candidate[end_axis]))
                    current_start = min(float(current[start_axis]), float(current[end_axis]))
                    current_end = max(float(current[start_axis]), float(current[end_axis]))
                    touching = candidate_start <= current_end + gap_tolerance and candidate_end >= current_start - gap_tolerance
                    if not (same_row and touching):
                        continue
                    current[start_axis] = int(min(current_start, candidate_start))
                    current[end_axis] = int(max(current_end, candidate_end))
                    current[axis] = int(round((float(current[axis]) + float(candidate[axis])) / 2))
                    pool.remove(candidate)
                    changed = True
                    break
            if orientation == "horizontal":
                current["y2"] = current["y1"]
            else:
                current["x2"] = current["x1"]
            current["length"] = round(math.hypot(float(current["x2"]) - float(current["x1"]), float(current["y2"]) - float(current["y1"])), 2)
            merged.append(current)
    return merged


def is_probable_box_edge(segment: dict[str, float | int | str], segments: list[dict[str, float | int | str]]) -> bool:
    """Reject short parallel pairs typical of a monitor/PLC/label rectangle."""
    length = float(segment["length"])
    if length > 280:
        return False
    orientation = segment["orientation"]
    for other in segments:
        if other is segment or other["orientation"] != orientation:
            continue
        if abs(float(other["length"]) - length) > max(30, length * 0.35):
            continue
        if orientation == "horizontal":
            separation = abs(float(other["y1"]) - float(segment["y1"]))
            overlap = min(float(other["x2"]), float(segment["x2"])) - max(float(other["x1"]), float(segment["x1"]))
        else:
            separation = abs(float(other["x1"]) - float(segment["x1"]))
            overlap = min(float(other["y2"]), float(segment["y2"])) - max(float(other["y1"]), float(segment["y1"]))
        if 10 <= separation <= 105 and overlap >= min(float(other["length"]), length) * 0.72:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect topology line candidates with OpenCV.")
    parser.add_argument("image", type=Path, help="Original topology image")
    parser.add_argument("ocr_json", type=Path, help="Raw PaddleOCR JSON; used to mask text")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts") / "lines",
        help="Folder for candidate-segment JSON and preview image",
    )
    args = parser.parse_args()

    image_path = args.image.expanduser().resolve()
    ocr_path = args.ocr_json.expanduser().resolve()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    # cv2.imread may fail on Windows when the path contains Chinese characters.
    # Reading bytes through pathlib keeps the path handling in Python/Unicode,
    # then OpenCV only receives an in-memory buffer.
    image_bytes = np.frombuffer(image_path.read_bytes(), dtype=np.uint8)
    image = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)
    if image is None:
        raise SystemExit(f"Image could not be read: {image_path}")

    ocr = json.loads(ocr_path.read_text(encoding="utf-8"))
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # Actual cables in the supplied diagrams are neutral dark strokes.  The
    # cyan dashed zone boundaries and blue switch artwork are saturated, so
    # remove them before line extraction instead of relying only on geometry.
    dark_neutral = cv2.inRange(hsv, (0, 0, 0), (180, 85, 165))
    binary = cv2.bitwise_and(dark_neutral, cv2.inRange(gray, 0, 165))

    # Remove OCR text before looking for long lines.
    boxes = ocr.get("rec_boxes", [])
    for box in boxes:
        x1, y1, x2, y2 = (int(value) for value in box)
        padding = 9
        cv2.rectangle(
            binary,
            (max(0, x1 - padding), max(0, y1 - padding)),
            (min(binary.shape[1], x2 + padding), min(binary.shape[0], y2 + padding)),
            0,
            thickness=-1,
        )

    # Long horizontal and vertical cables are the most reliable first-pass
    # evidence in industrial topology diagrams.  A larger kernel removes the
    # short strokes around labels and device illustrations.
    horizontal = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (55, 1)),
    )
    vertical = cv2.morphologyEx(
        binary,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, 55)),
    )
    cable_mask = cv2.bitwise_or(horizontal, vertical)
    edges = cv2.Canny(cable_mask, 50, 150, apertureSize=3)
    raw_lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=50,
        minLineLength=70,
        maxLineGap=28,
    )

    raw_segments: list[dict[str, float | int | str]] = []
    preview = image.copy()
    if raw_lines is not None:
        for index, values in enumerate(raw_lines[:, 0], start=1):
            x1, y1, x2, y2 = (int(value) for value in values)
            length = math.hypot(x2 - x1, y2 - y1)
            if length < 70:
                continue
            angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
            orientation = "horizontal" if abs(x2 - x1) >= abs(y2 - y1) else "vertical"
            raw_segments.append(
                {
                    "id": f"segment-{index:03d}",
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "length": round(length, 2),
                    "angle": round(angle, 2),
                    "orientation": orientation,
                    "confidence": 0.45,
                    "evidence": "opencv-hough-lines",
                }
            )
    merged_segments = merge_collinear_segments(raw_segments)

    # OCR labels matching a device type become soft spatial anchors.  A line
    # near no device is much more likely to be a frame or decoration.
    anchors: list[tuple[float, float]] = []
    for text, score, box in zip(ocr.get("rec_texts", []), ocr.get("rec_scores", []), ocr.get("rec_boxes", [])):
        if float(score) < 0.45 or not DEVICE_TEXT.search(str(text)):
            continue
        x1, y1, x2, y2 = (float(value) for value in box)
        anchors.append(((x1 + x2) / 2, (y1 + y2) / 2))

    segments: list[dict[str, float | int | str]] = []
    for segment in merged_segments:
        if is_probable_box_edge(segment, merged_segments):
            continue
        nearby_anchors = sum(point_to_segment_distance(anchor, segment) <= 68 for anchor in anchors)
        if nearby_anchors == 0:
            continue
        # Candidate confidence describes visual evidence only; it is not a
        # confirmed network link and must still be reviewed by the editor.
        segment["confidence"] = round(min(0.85, 0.5 + 0.1 * nearby_anchors), 2)
        segment["evidence"] = "opencv-hough-lines+neutral-color+device-anchor"
        segments.append(segment)

    preview = image.copy()
    for segment in segments:
        cv2.line(
            preview,
            (int(segment["x1"]), int(segment["y1"])),
            (int(segment["x2"]), int(segment["y2"])),
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

    result = {
        "source_image": str(image_path),
        "segments": segments,
        "review_note": "Segments are candidate cable evidence only. Saturated zone borders, OCR regions, likely device rectangles, and lines without a nearby device anchor are filtered out.",
    }
    json_path = output / "line-candidates.json"
    preview_path = output / "line-candidates-preview.jpg"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    cv2.imwrite(str(preview_path), preview)

    print(f"Line segments: {len(segments)}")
    print(f"Saved JSON: {json_path}")
    print(f"Saved preview: {preview_path}")


if __name__ == "__main__":
    main()
