"""Static discovery. A declaration or URI literal is not an executable grant."""
from __future__ import annotations
import ast
from collections import Counter
from pathlib import Path
import re
import tomllib
from typing import Any
from .common import (IGNORED_DIRS, SECRET_NAMES, UripackError, checked_root, digest,
                     parse_document, read_regular, sha256, walk_files, secret_check)

URI = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s\"'<>`\\]+")
IMPORT_TS = re.compile(r'''(?:\bfrom\s*|\bimport\s*\(|\brequire\s*\(|\bimport\s*)["']([^"']+)["']''')
EXPORT_TS = re.compile(r"\bexport\s+(?:async\s+)?(?:function|class|const|let|interface|type|enum)\s+([A-Za-z_$][\w$]*)")
URI_KEYS = {"uri", "process_uri", "processUri", "uriTemplate", "process_ref", "processRef"}


def _strings(v: Any, key: str = ""):
    if isinstance(v, str):
        yield key, v
    elif isinstance(v, list):
        for x in v:
            yield from _strings(x, key)
    elif isinstance(v, dict):
        for k, x in v.items():
            yield from _strings(x, k)


def analyze(relative: str, data: bytes) -> dict:
    suffix = Path(relative).suffix
    result: dict = {"path": relative, "sha256": sha256(data), "size": len(data),
                    "language": {".py":"python", ".ts":"typescript", ".tsx":"typescript",
                                 ".mjs":"javascript", ".js":"javascript", ".cjs":"javascript"}.get(suffix, "data"),
                    "imports": [], "exports": [], "uris": [], "notes": []}
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        result["notes"] = ["binary file: no semantic inspection"]
        return result
    candidates = {m.group(0).rstrip(",;)") for m in URI.finditer(text)}
    declared: set[str] = set()
    document = None
    if suffix in {".json", ".yaml", ".yml"}:
        try:
            document = parse_document(data, suffix)
            for key, value in _strings(document):
                if URI.fullmatch(value):
                    candidates.add(value)
                    if key in URI_KEYS:
                        declared.add(value)
        except UripackError:
            result["notes"].append("document not parsed by the strict data profile")
    if suffix == ".py":
        try:
            tree = ast.parse(text)
            result["exports"] = [node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    result["imports"].extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    result["imports"].append("." * node.level + (node.module or ""))
            if "importlib" in text or "__import__" in text:
                result["notes"].append("dynamic Python import requires a runtime dependency check")
        except SyntaxError:
            result["notes"].append("Python source not understood by the current AST parser")
    elif suffix in {".ts", ".tsx", ".mjs", ".js", ".cjs"}:
        result["imports"] = sorted(set(IMPORT_TS.findall(text)))
        result["exports"] = sorted(set(EXPORT_TS.findall(text)))
        result["notes"].append("JS/TS lexical inventory only; not a complete compiler analysis")
    if Path(relative).name == "pyproject.toml":
        try:
            doc = tomllib.loads(text)
            project = doc.get("project", {})
            result["package"] = {"ecosystem":"python", "name":project.get("name"),
                                 "version":project.get("version"), "dependencies":project.get("dependencies", []),
                                 "scripts":project.get("scripts", {}), "entry_points":project.get("entry-points", {})}
        except tomllib.TOMLDecodeError:
            result["notes"].append("invalid pyproject.toml")
    if Path(relative).name == "package.json" and isinstance(document, dict):
        result["package"] = {"ecosystem":"node", "name":document.get("name"), "version":document.get("version"),
                             "dependencies":document.get("dependencies", {}), "dev_dependencies":document.get("devDependencies", {}),
                             "scripts":document.get("scripts", {}), "bin":document.get("bin", {}),
                             "exports":document.get("exports", {})}
    # Never show URI userinfo or potential query secrets in inventory output.
    safe = []
    for uri in sorted(candidates):
        if "@" in uri.split("://", 1)[1].split("/", 1)[0] or re.search(r"(?i)(token|password|secret|api[_-]?key)=", uri):
            result["notes"].append("credential-bearing URI omitted from inventory")
            continue
        safe.append({"uri":uri, "evidence":"declared-field" if uri in declared else "literal-candidate",
                     "binding_verified":False})
    result["uris"] = safe
    return result


def discover(root: str | Path, includes: list[str] | None = None) -> dict:
    source = checked_root(root)
    if includes is None:
        includes = sorted(p.name for p in source.iterdir() if p.name not in IGNORED_DIRS and p.name != ".subactor")
    paths, exclusions = walk_files(source, includes)
    items = []
    omitted = []
    for path in paths:
        if Path(path).name in SECRET_NAMES or Path(path).suffix in {".key", ".pem", ".p12", ".pfx"}:
            omitted.append(path)
            continue
        if Path(path).suffix not in {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".json", ".toml", ".yaml", ".yml"}:
            continue
        try:
            data, _ = read_regular(source, path)
            secret_check(path, data)
            items.append(analyze(path, data))
        except UripackError as exc:
            omitted.append(f"{path} ({exc.code})")
    packages = [{"manifest":i["path"], **i["package"], "execution_status":"discovered-not-invoked"}
                for i in items if "package" in i]
    # Keep npm scripts and Python entry points as metadata, NEVER turn them into shell commands.
    return {"schema":"uripack.inventory/v1", "source_root":str(source), "files":items,
            "packages":packages, "exclusions":exclusions, "omitted":omitted,
            "inventory_sha256":digest(items), "source_code_imported":False,
            "complete_runtime_dependency_graph":False}


def index_map(path: str | Path) -> dict:
    """Read only the M[...] module section of a code2llm map (not ordinary YAML)."""
    raw = Path(path).read_bytes()
    rows = []
    active = False
    for line in raw.decode("utf-8").splitlines():
        if re.fullmatch(r"M\[\d+\]:", line):
            active = True
            continue
        if not active:
            continue
        if not line.startswith("  "):
            break
        match = re.fullmatch(r"  (.*),(\d+)", line)
        if not match:
            break
        rows.append((match.group(1), int(match.group(2))))
    if not rows:
        from .common import fail
        fail("UPK-MAP-001", "No code2llm module section was found")
    counts = Counter(p.split("/")[0] for p, _ in rows if "/" in p)
    metadata = [p for p, _ in rows if Path(p).name in {"pyproject.toml", "package.json", "dsl-manifest.json", "connector.manifest.json"}]
    return {"schema":"uripack.map-index/v1", "input_sha256":sha256(raw), "module_count":len(rows),
            "root_count":len(counts), "roots":[{"name":k,"module_count":v} for k,v in sorted(counts.items())],
            "metadata_paths":metadata, "evidence_level":"index-only", "tools_executed":0,
            "warning":"An indexed root is not necessarily a tool; paths do not prove callable APIs or installed runtimes."}
