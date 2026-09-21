"""Internal-only Docker range runtime. Never mounts the host Docker socket."""
import json, os, re, time, urllib.parse, urllib.request
from fastapi import FastAPI, HTTPException

app=FastAPI(title="TopoRangeHub Range Engine",docs_url=None,redoc_url=None)
BASE=os.getenv("RANGE_DOCKER_HOST","http://range-docker:2375").rstrip("/")

def call(method,path,payload=None):
    data=None if payload is None else json.dumps(payload).encode()
    req=urllib.request.Request(BASE+path,data=data,method=method,headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=20) as r:
            raw = r.read()
            # Image pulls return JSON Lines; ordinary Docker API replies return
            # one JSON object. Return the final valid item in either form.
            for line in reversed(raw.splitlines()):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
            return {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace").strip()
        raise HTTPException(e.code, detail or f"Docker API error {e.code}") from e
    except Exception as e:
        raise HTTPException(503, f"range runtime unavailable: {e}") from e
def sid(v): return re.sub('[^a-z0-9-]+','-',str(v).lower()).strip('-')[:42] or 'node'
def ready():
    call("POST","/images/create?fromImage=alpine&tag=3.20")
def validate(t):
    if (t.get("review")or{}).get("status")!="approved":raise HTTPException(422,"Topology must be approved before deployment")
    iso=t.get("isolation")or{}
    if iso.get("production_bridge") or iso.get("internet_egress"):raise HTTPException(422,"Production bridge and internet egress are forbidden")
    if not t.get("nodes"):raise HTTPException(422,"Topology needs nodes")
@app.get("/health")
def health():
    call("GET","/_ping");return {"status":"ok","runtime":"nested-docker"}
@app.post("/deployments")
def deploy(topology: dict):
    validate(topology)
    ready()
    rid = "trh-" + sid(topology.get("name", "range")) + "-" + str(int(time.time()))
    nodes = {node["id"]: node for node in topology["nodes"]}
    node_networks = {node_id: [] for node_id in nodes}
    networks = []

    # Build all private link segments first. A node is born on an internal
    # segment, rather than on Docker's default bridge, so it never gets a
    # fallback outbound route.
    for link in topology.get("links", []):
        source, target = link.get("source"), link.get("target")
        if source not in nodes or target not in nodes:
            raise HTTPException(422, "Link references unknown node")
        name = f"{rid}-{sid(link.get('id', 'link'))}"
        net = call("POST", "/networks/create", {
            "Name": name, "Driver": "bridge", "Internal": True,
            "Labels": {"toporangehub.range": rid, "toporangehub.link": str(link.get("id", ""))},
        })
        item = {"id": link.get("id"), "network": name, "network_id": net["Id"], "source": source, "target": target}
        networks.append(item)
        node_networks[source].append(item)
        if target != source:
            node_networks[target].append(item)

    # Give an unlinked node its own closed segment instead of a default bridge.
    for node_id, attached in node_networks.items():
        if attached:
            continue
        name = f"{rid}-{sid(node_id)}-isolated"
        net = call("POST", "/networks/create", {
            "Name": name, "Driver": "bridge", "Internal": True,
            "Labels": {"toporangehub.range": rid, "toporangehub.isolated": node_id},
        })
        attached.append({"network": name, "network_id": net["Id"]})

    containers = {}
    for node_id, node in nodes.items():
        attached = node_networks[node_id]
        name = f"{rid}-{sid(node_id)}"
        labels = {
            "toporangehub.range": rid, "toporangehub.node": node_id,
            "toporangehub.type": str(node.get("type", "unknown")), "toporangehub.zone": str(node.get("zone", "")),
        }
        created = call("POST", "/containers/create?name=" + urllib.parse.quote(name), {
            "Image": "alpine:3.20", "Cmd": ["sleep", "infinity"], "Labels": labels,
            "HostConfig": {"NetworkMode": attached[0]["network"]},
        })
        call("POST", f"/containers/{created['Id']}/start")
        containers[node_id] = {"id": created["Id"], "name": name}

    # Connect extra reviewed links after each node has started on its first
    # private segment. No connection to Docker's default bridge is created.
    for node_id, attached in node_networks.items():
        for network in attached[1:]:
            call("POST", f"/networks/{network['network_id']}/connect", {"Container": containers[node_id]["id"]})

    return {
        "id": rid,
        "nodes": [{"id": key, "container": value["name"], "type": nodes[key].get("type"), "zone": nodes[key].get("zone")} for key, value in containers.items()],
        "links": [{key: value for key, value in link.items() if key != "network_id"} for link in networks],
    }
@app.delete("/deployments/{range_id}")
def destroy(range_id: str):
    if not re.fullmatch(r"trh-[a-z0-9-]+", range_id):
        raise HTTPException(404, "Range not found")
    filters = urllib.parse.quote(json.dumps({"label": [f"toporangehub.range={range_id}"]}))
    for container in call("GET", "/containers/json?all=1&filters=" + filters):
        call("DELETE", f"/containers/{container['Id']}?force=1")
    for network in call("GET", "/networks?filters=" + filters):
        call("DELETE", f"/networks/{network['Id']}")
    return {"id": range_id, "status": "destroyed"}

@app.get("/deployments")
def list_ranges():
    filters=urllib.parse.quote(json.dumps({"label":["toporangehub.range"]}))
    items=call("GET","/containers/json?all=1&filters="+filters);return {"containers":[{"id":x["Id"][:12],"name":x["Names"][0].lstrip('/'),"state":x["State"],"range":x.get("Labels",{}).get("toporangehub.range")} for x in items]}