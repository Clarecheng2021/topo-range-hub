"""Compile a reviewed topology JSON into an isolated Containerlab range package."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

TEMPLATES = {
    "workstation": "operator-workstation", "hmi": "operator-workstation", "scada": "operator-workstation",
    "server": "service-host", "historian": "service-host", "opc_server": "service-host",
    "firewall": "firewall-gateway", "router": "router-gateway",
    "switch": "layer2-switch", "industrial_switch": "layer2-switch",
    "plc": "plc-simulator", "rtu": "plc-simulator", "dcs": "plc-simulator", "sis": "plc-simulator",
}

def safe(value: str) -> str:
    result = re.sub(r"[^a-z0-9-]+", "-", str(value).lower()).strip("-")
    return result[:48] or "node"

def compile_range(topology: dict) -> dict:
    nodes, links = topology.get("nodes"), topology.get("links")
    if not isinstance(nodes, list) or not nodes or not isinstance(links, list):
        raise ValueError("Topology must contain non-empty nodes and a links array.")
    isolation = topology.get("isolation") or {}
    if isolation.get("production_bridge") or isolation.get("internet_egress"):
        raise ValueError("Refusing unsafe topology: production_bridge and internet_egress must both be false.")
    if (topology.get("review") or {}).get("status") != "approved":
        raise ValueError("Topology must be approved before compiling a deployable range.")
    ids = [str(n.get("id", "")) for n in nodes]
    if len(ids) != len(set(ids)) or not all(ids): raise ValueError("Node IDs must be unique and non-empty.")
    known = set(ids)
    for link in links:
        if link.get("source") not in known or link.get("target") not in known:
            raise ValueError(f"Link {link.get('id', '?')} references an unknown node.")
    names, used = {}, set()
    for node in nodes:
        base, suffix = safe(node["id"]), 2
        name = base
        while name in used: name, suffix = f"{base}-{suffix}", suffix + 1
        names[node["id"]] = name; used.add(name)
    ports, yaml = {}, [f"name: {safe(topology.get('name', 'toporangehub-range'))}", "", "mgmt:", "  network: toporangehub-mgmt", "  ipv4-subnet: 172.31.100.0/24", "", "topology:", "  nodes:"]
    inventory = []
    for node in nodes:
        profile = TEMPLATES.get(node.get("type"), "generic-linux")
        inventory.append({"id": node["id"], "container": names[node["id"]], "name": node.get("name"), "type": node.get("type"), "zone": node.get("zone"), "template": profile})
        yaml += [f"    {names[node['id']]}:", "      kind: linux", "      image: alpine:3.20", "      cmd: sleep infinity", "      labels:", f"        toporangehub.name: {json.dumps(node.get('name',''), ensure_ascii=False)}", f"        toporangehub.type: {node.get('type','unknown')}", f"        toporangehub.zone: {json.dumps(node.get('zone',''), ensure_ascii=False)}", f"        toporangehub.template: {profile}"]
    yaml.append("  links:")
    for link in links:
        a,b=link["source"],link["target"]; ports[a]=ports.get(a,0)+1; ports[b]=ports.get(b,0)+1
        yaml.append(f'    - endpoints: ["{names[a]}:eth{ports[a]}", "{names[b]}:eth{ports[b]}"]')
    return {"containerlab": "\n".join(yaml)+"\n", "inventory": {"source_name": topology.get("name"), "isolation": {"production_bridge": False, "internet_egress": False}, "nodes": inventory, "links": links}}

def write_package(topology: dict, output: Path) -> None:
    result=compile_range(topology); output.mkdir(parents=True,exist_ok=True)
    (output/"clab.yml").write_text(result["containerlab"],encoding="utf-8")
    (output/"inventory.json").write_text(json.dumps(result["inventory"],ensure_ascii=False,indent=2),encoding="utf-8")
    (output/"DEPLOY.md").write_text("# TopoRangeHub 靶场包\n\n仅在隔离 Linux 靶场主机运行：`containerlab deploy --topo clab.yml`。\n\n此包拒绝生产桥接和互联网出口配置；所有节点使用通用 Linux 容器模板，后续再由人工为每个设备绑定经过审核的服务镜像。\n",encoding="utf-8")

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("topology"); parser.add_argument("--output",required=True); args=parser.parse_args()
    topology=json.loads(Path(args.topology).read_text(encoding="utf-8")); write_package(topology,Path(args.output)); print(f"Range package written: {args.output}")
if __name__ == "__main__": main()