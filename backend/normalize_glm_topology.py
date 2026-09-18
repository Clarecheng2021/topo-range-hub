"""Normalize a GLM topology candidate into the project's topology IR.

The GLM visual-analysis output is useful evidence, but it is not directly
importable: it uses ``endpoints`` instead of ``source``/``target`` and expresses
bounding boxes as image-coordinate arrays.  This tool performs only explicit,
auditable transformations; it does not invent topology.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


TYPE_MAP = {
    "workstation": "workstation", "server": "server", "firewall": "firewall",
    "switch": "switch", "industrial_switch": "industrial_switch", "hmi-tag": "hmi",
    "hmi": "hmi", "plc-station": "plc", "plc-substation": "plc", "plc": "plc",
}

# L17 is the same visible ProfiNet bus already represented by L15 and L16.
# Keeping all three turns one shared segment into an incorrect direct edge.
REMOVED_LINKS = {"L17": "重复表达 PLC1 ProfiNet 母线；由 L15 和 L16 保留其两条分支。"}
LOW_CONFIDENCE = {
    "L08": (0.85, "防火墙图标遮挡了中段，保留为需要图上复核的候选边。"),
    **{f"L{number}": (0.85, "ProfiNet 干线分支短，需保留审核标记。") for number in range(25, 32)},
}


def as_bbox(value: Any) -> dict[str, float] | None:
    """Convert GLM [x0, y0, x1, y1] to the schema's x/y/width/height."""
    if not isinstance(value, list) or len(value) != 4:
        return None
    x0, y0, x1, y1 = (float(item) for item in value)
    if x1 < x0 or y1 < y0:
        return None
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


def infer_link_metadata(link: dict[str, Any]) -> tuple[str | None, str]:
    text = " ".join(str(link.get(key, "")) for key in ("path", "style", "evidence"))
    if "ProfiNet" in text:
        return "Profinet", "fieldbus"
    if "光纤" in text or link.get("id") in {"L10", "L11", "L12", "L13"}:
        return "fiber-ring", "fiber"
    return None, "ethernet"


def evidence(note: str | None, extra: list[str] | None = None) -> dict[str, Any]:
    notes = [item for item in [note, *(extra or [])] if item]
    return {"sources": ["vlm", "rule"], "notes": notes}


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    zones: list[dict[str, Any]] = []
    for zone in raw.get("zones", []):
        item = {"id": zone["id"], "name": zone["name"], "confidence": 0.9,
                "evidence": evidence(str(zone.get("basis", "")))}
        if box := as_bbox(zone.get("bbox")):
            item["bbox"] = box
        zones.append(item)

    node_ids: set[str] = set()
    nodes: list[dict[str, Any]] = []
    for node in raw.get("nodes", []):
        node_id = str(node["id"])
        if node_id in node_ids:
            raise ValueError(f"Duplicate node id: {node_id}")
        node_ids.add(node_id)
        box = as_bbox(node.get("bbox"))
        item: dict[str, Any] = {
            "id": node_id,
            "name": node.get("label", node_id),
            "type": TYPE_MAP.get(node.get("type"), "unknown"),
            "zone": node.get("zone", "unknown"),
            "confidence": 0.9,
            "evidence": evidence(str(node.get("note", ""))),
        }
        if box:
            item["bbox"] = box
            item["position"] = {"x": box["x"] + box["width"] / 2, "y": box["y"] + box["height"] / 2}
        if node.get("type") not in TYPE_MAP:
            item["attributes"] = {"glm_type": node.get("type")}
        nodes.append(item)

    issues = [*REMOVED_LINKS.values()]
    links: list[dict[str, Any]] = []
    seen_pairs: set[frozenset[str]] = set()
    for raw_link in raw.get("links", []):
        link_id = str(raw_link["id"])
        if link_id in REMOVED_LINKS:
            continue
        endpoints = raw_link.get("endpoints", [])
        if not isinstance(endpoints, list) or len(endpoints) != 2:
            issues.append(f"{link_id} 缺少两个端点，未导入。")
            continue
        source, target = (str(value) for value in endpoints)
        if source not in node_ids or target not in node_ids or source == target:
            issues.append(f"{link_id} 端点无效，未导入。")
            continue
        pair = frozenset((source, target))
        if pair in seen_pairs:
            issues.append(f"{link_id} 与已有链路重复，未导入。")
            continue
        seen_pairs.add(pair)
        protocol, medium = infer_link_metadata(raw_link)
        confidence, review_note = LOW_CONFIDENCE.get(link_id, (0.9, None))
        item: dict[str, Any] = {
            "id": link_id, "source": source, "target": target, "medium": medium,
            "confidence": confidence,
            "evidence": evidence(str(raw_link.get("evidence", "")), [review_note] if review_note else None),
        }
        if protocol:
            item["protocol"] = protocol
        if raw_link.get("via"):
            item["attributes"] = {"via": raw_link["via"]}
        links.append(item)

    return {
        "name": raw.get("diagram_title", raw.get("name", "glm-topology")),
        "title": raw.get("diagram_title", "GLM 拓扑候选"),
        "schema_version": "0.3", "version": "0.3",
        "source": {
            "kind": "image",
            "filename": raw.get("source_image", raw.get("source", {}).get("filename", "")),
            "model": raw.get("generated_by", "GLM visual analysis"),
            "image_size": raw.get("image_size", {}),
        },
        "isolation": {"production_bridge": False, "internet_egress": False},
        "zones": zones, "nodes": nodes, "links": links,
        "review": {"status": "in_review", "issues": issues},
    }


def validate(topology: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    node_ids = [node["id"] for node in topology["nodes"]]
    if len(node_ids) != len(set(node_ids)):
        errors.append("存在重复节点 ID。")
    node_set = set(node_ids)
    link_ids: set[str] = set()
    for link in topology["links"]:
        if link["id"] in link_ids:
            errors.append(f"重复链路 ID: {link['id']}")
        link_ids.add(link["id"])
        if link["source"] not in node_set or link["target"] not in node_set:
            errors.append(f"{link['id']} 引用了不存在的节点。")
        if not 0 <= float(link["confidence"]) <= 1:
            errors.append(f"{link['id']} 置信度超出 0~1。")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize a GLM candidate into the project topology IR.")
    parser.add_argument("input", type=Path, help="Raw GLM topology JSON")
    parser.add_argument("--output", type=Path, default=Path("artifacts/topology/test1-glm-normalized.topology.json"))
    args = parser.parse_args()
    raw = json.loads(args.input.expanduser().resolve().read_text(encoding="utf-8"))
    topology = normalize(raw)
    errors = validate(topology)
    if errors:
        raise SystemExit("Normalization validation failed:\n- " + "\n- ".join(errors))
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(topology, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Normalized zones: {len(topology['zones'])}")
    print(f"Normalized nodes: {len(topology['nodes'])}")
    print(f"Normalized links: {len(topology['links'])}")
    print(f"Review status: {topology['review']['status']}")
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
