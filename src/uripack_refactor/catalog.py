"""Coverage of the complete supplied map, without pretending each root is a tool."""
from __future__ import annotations
from .contracts import resource_json
from .discovery import discover


def catalog(root=None) -> dict:
    baseline = resource_json("subactor-map-index.json")
    roles = resource_json("integration-roles.json")
    live = discover(root) if root is not None else None
    packages = live["packages"] if live else []
    records = []
    for item in baseline["roots"]:
        name = item["name"]
        found = [p for p in packages if p["manifest"].split("/")[0] == name]
        records.append({**item, "role":roles.get(name, "source-package-or-consumer; no migration capability assumed"),
                        "evidence":"local-metadata" if found else "map-index-only",
                        "packages":found, "invocation_status":"not-invoked",
                        "integration_contract":"uripack.guard-request/v1:tool (operator binding required)"})
    return {"schema":"uripack.tool-coverage/v1","map_sha256":baseline["input_sha256"],
            "root_count":len(records),"records":records,"unmapped_local_packages":[p for p in packages if p["manifest"].split("/")[0] not in {r["name"] for r in records}],
            "automatic_installation":False,"automatic_script_execution":False}
