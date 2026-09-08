"""Deterministic, copy-preserving extraction at whole-file/package granularity."""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path, PurePosixPath
import re
from .common import (checked_root, digest, fail, json_bytes, read_regular, relative_path,
                     secret_check, sha256, walk_files)
from .contracts import validate
from .discovery import analyze
from .services import service_files

SEMANTICS = "copy-preserving-extraction; no cutover; behavioral verification separate"


def _graph(units: list[dict]) -> None:
    ids = [u["id"] for u in units]
    if len(ids) != len(set(ids)):
        fail("UPK-COLLISION-001", "Unit identifiers must be unique")
    by_id = {u["id"]:u for u in units}
    active: set[str] = set()
    done: set[str] = set()
    def visit(key: str):
        if key not in by_id:
            fail("UPK-DEPENDENCY-001", "Unknown unit dependency")
        if key in active:
            fail("UPK-DEPENDENCY-001", "Cyclic unit dependency")
        if key in done:
            return
        active.add(key)
        for dep in by_id[key].get("depends_on", []):
            visit(dep)
        active.remove(key)
        done.add(key)
    for key in ids:
        visit(key)


def _relative_import_warnings(items: list[dict], all_selected: set[str]) -> list[str]:
    warnings = []
    for item in items:
        for imp in item["imports"]:
            if not imp.startswith("."):
                continue
            if item["language"] in {"typescript", "javascript"}:
                base = PurePosixPath(item["path"]).parent
                # Normalize relative lexical imports without reading outside the source root.
                parts = list(base.parts)
                for piece in imp.split("/"):
                    if piece == "..":
                        if parts:
                            parts.pop()
                        else:
                            parts = ["__outside_root__"]
                            break
                    elif piece not in {".", ""}:
                        parts.append(piece)
                rel = PurePosixPath(*parts).as_posix()
                variants = {rel, *(rel + ext for ext in (".ts", ".tsx", ".js", ".mjs", ".json", "/index.ts", "/index.js"))}
                if rel.endswith(".js"):
                    variants.add(rel[:-3] + ".ts")
                if not variants.intersection(all_selected):
                    warnings.append(f"Unresolved local JS/TS import: {item['path']} -> {imp}")
            else:
                warnings.append(f"Relative Python imports need package-context validation: {item['path']}")
    return sorted(set(warnings))


def build_plan(request: dict, source_root: str | Path, target_root: str | Path) -> dict:
    validate("request", request)
    _graph(request["units"])
    source = checked_root(source_root)
    target = checked_root(target_root, exists=False)
    checked_root(target.parent)
    if source == target or source in target.parents or target in source.parents:
        fail("UPK-PATH-001", "Source and target roots must be disjoint")
    limits = request.get("limits", {"max_files":2000, "max_bytes":64 * 1024 * 1024})
    operations: list[dict] = []
    exclusions: set[str] = set()
    warnings: set[str] = set()
    owners: dict[str,str] = {}
    uri_owners: dict[str,str] = {}
    total_bytes = 0
    count = 0
    unit_catalog = []
    file_snapshot = []
    def write(path: str, content: bytes):
        relative_path(path)
        operations.append({"kind":"write", "target":path, "content":content.decode("utf-8"),
                           "sha256":sha256(content), "mode":0o644})
    for unit in sorted(request["units"], key=lambda u:u["id"]):
        paths, skipped = walk_files(source, unit["include"])
        exclusions.update(skipped)
        if not paths:
            fail("UPK-DEPENDENCY-001", "An extraction unit contains no regular files")
        items = []
        unit_files = []
        for path in paths:
            if path in owners:
                fail("UPK-COLLISION-001", "A source file is selected by multiple units; extract a shared unit instead")
            owners[path] = unit["id"]
            data, mode = read_regular(source, path)
            secret_check(path, data)
            total_bytes += len(data)
            count += 1
            if count > limits["max_files"] or total_bytes > limits["max_bytes"]:
                fail("UPK-LIMIT-001", "Extraction exceeds the explicit file or byte budget")
            item = analyze(path, data)
            items.append(item)
            warnings.update(item["notes"])
            record = {"source":path,"sha256":sha256(data),"mode":mode,"size":len(data),"unit":unit["id"]}
            file_snapshot.append(record)
            op = {"kind":"copy", **record, "target":f"packs/{unit['id']}/tree/{path}"}
            operations.append(op)
            unit_files.append({"path":path,"sha256":sha256(data),"mode":mode,"size":len(data)})
        warnings.update(_relative_import_warnings(items, set(paths)))
        observed = {u["uri"] for i in items for u in i["uris"]}
        for uri in unit.get("public_uris", []):
            if uri not in observed:
                fail("UPK-URI-001", "A declared public URI was not found in selected source content")
            if uri in uri_owners:
                fail("UPK-COLLISION-001", "A public URI has multiple extraction owners")
            uri_owners[uri] = unit["id"]
        languages = sorted({i["language"] for i in items if i["language"] != "data"})
        native = [{"path":i["path"],"sha256":i["sha256"],"metadata":i["package"]}
                  for i in items if "package" in i]
        locks = [{"path":i["path"],"sha256":i["sha256"]} for i in items
                 if Path(i["path"]).name.endswith((".lock", "lock.json"))]
        manifests = [i["path"] for i in items if Path(i["path"]).name.startswith(("process.", "recipe.", "operations.", "expectations."))
                     or Path(i["path"]).name in {"connector.manifest.json", "dsl-manifest.json"}]
        pack = {"schema":"uripack.process-package/v1alpha1", "id":unit["id"], "namespace":request["namespace"],
                "layers":{
                    "identity":{"public_uris":unit.get("public_uris", []),"runtime_binding_verified":False},
                    "contracts":{"files":manifests,"format":"preserved-native-formats","poa_conversion_performed":False},
                    "implementations":{"root":"tree", "languages":languages,"native_packages":native},
                    "dependencies":{"unit_refs":unit.get("depends_on", []),"native_locks":locks,"resolution":"not-executed"},
                    "provenance":{"files":unit_files,"selected_tree_sha256":digest(unit_files)},
                    "verification":{"copy_equivalence":"sha256-and-mode","behavioral_equivalence":"requires-protected-checks"}}}
        if "service" in unit:
            generated, runtime = service_files(unit, unit_files)
            pack["layers"]["runtime"] = runtime
            for name, content in generated.items():
                write(f"packs/{unit['id']}/{name}", content)
        pack_path = f"packs/{unit['id']}/uripack.json"
        write(pack_path, json_bytes(pack))
        write(f"packs/{unit['id']}/uri-baseline.json", json_bytes({"schema":"uripack.uri-baseline/v1", "public_uris":unit.get("public_uris", []),
              "observations":[{"path":i["path"],"uris":i["uris"]} for i in items if i["uris"]],"binding_verified":False}))
        unit_catalog.append({"id":unit["id"],"manifest":pack_path,"languages":languages})
    warnings.add("Byte-preserving extraction does not prove runtime equivalence or installability")
    warnings.add("Production routing, source deletion, publishing and automatic semantic rewrites are not implemented")
    snapshot_hash = digest(sorted(file_snapshot, key=lambda x:x["source"]))
    write("uripack.json", json_bytes({"schema":"uripack.catalog/v1alpha1","namespace":request["namespace"],"packs":unit_catalog}))
    write("uripack.lock.json", json_bytes({"schema":"uripack.source-lock/v1","canonicalization":"uripack.c14n/v1","selected_source_sha256":snapshot_hash,"files":sorted(file_snapshot,key=lambda x:x["source"])}))
    write("compatibility/source-aliases.proposed.json", json_bytes({"schema":"uripack.alias-proposal/v1","applied":False,
          "aliases":[{"public_uri":uri,"unit":owner,"action":"retain-existing-binding-until-separate-cutover"} for uri,owner in sorted(uri_owners.items())]}))
    write(".gitignore", b".uripack/\n.subactor/\n.worktrees/\n__pycache__/\nnode_modules/\n.venv/\n")
    write("README.md", ("# uripack — extracted process packages\n\n"
          "This directory was materialized from an exact, guard-admitted extraction plan. "
          "Original files remain unchanged. Original URI strings, native metadata, relative directory layouts and executable bits are preserved.\n\n"
          "Each `packs/<id>/tree/` is a selected projection of the original source root, not an automatically installable universal runtime. "
          "Native package commands must be invoked from their original package root inside that projection, after dependency and environment validation.\n\n"
          "`depends_on` is metadata, not an import resolver. No production routing, source deletion, registry publication or Git effect was performed. "
          "Adopt pinned wellmanifest governance and allocate the target ticket through its managed tools before integrating into a managed repository.\n").encode())
    destinations = [op["target"].casefold() for op in operations]
    if len(destinations) != len(set(destinations)):
        fail("UPK-COLLISION-001", "Case-insensitive destination collision")
    core = {"schema":"uripack.refactor-plan/" + request["schema"].rsplit("/", 1)[1],"source_root":str(source),"target_root":str(target),"request":request,
            "request_sha256":digest(request),"source_sha256":snapshot_hash,"operations":operations,
            "checks":sorted(request.get("checks", [])),"warnings":sorted(warnings),"exclusions":sorted(exclusions),"semantics":SEMANTICS}
    plan = {**core,"plan_sha256":digest(core)}
    validate("plan", plan)
    return plan


def validate_plan(plan: dict, reobserve: bool = True) -> None:
    validate("plan", plan)
    if digest({k:v for k,v in plan.items() if k != "plan_sha256"}) != plan["plan_sha256"]:
        fail("UPK-INTEGRITY-001", "Plan digest mismatch")
    if digest(plan["request"]) != plan["request_sha256"]:
        fail("UPK-INTEGRITY-001", "Request digest mismatch")
    for op in plan["operations"]:
        relative_path(op["target"])
        if op["kind"] == "copy":
            relative_path(op["source"])
        elif sha256(op["content"].encode("utf-8")) != op["sha256"]:
            fail("UPK-INTEGRITY-001", "Generated content digest mismatch")
    if reobserve:
        rebuilt = build_plan(plan["request"], plan["source_root"], plan["target_root"])
        if rebuilt != plan:
            fail("UPK-DRIFT-001", "Selected source, metadata or extraction compiler result changed; replan required")


def artifact_digest(plan: dict) -> str:
    return digest([{"path":o["target"],"sha256":o["sha256"],"mode":o["mode"]} for o in plan["operations"]])
