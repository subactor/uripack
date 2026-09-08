"""Synthetic E2E fixture. Never call a simulated admission a live Guard test."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from .common import digest, fail, json_bytes
from .executor import apply_plan, verify_artifact
from .planner import artifact_digest, build_plan

PYTHON_HANDLER = '''import json\nimport sys\nfrom util import count\nURI = "demo://repository/query/count"\nif __name__ == "__main__":\n    value = json.loads(sys.argv[1])\n    print(json.dumps({"uri": URI, "count": count(value["items"])}))\n'''
PYTHON_UTIL = '''def count(items):\n    return len(items)\n'''
TS_HANDLER = '''import { count } from "./util.js";\ndeclare const process: {argv: string[]; stdout: {write(value: string): void}};\nconst value: {items: unknown[]} = JSON.parse(process.argv[2]);\nprocess.stdout.write(JSON.stringify({uri: "demo://repository/query/count", count: count(value.items)}) + "\\n");\n'''
TS_UTIL = '''export function count(items: unknown[]): number { return items.length; }\n'''


def create_fixture(root: Path) -> dict:
    source = root / "subactor-fixture"
    source.mkdir()
    fixture = {
        "python/pyproject.toml": '[project]\nname = "uripack-demo-python"\nversion = "0.1.0"\n',
        "python/src/handler.py":PYTHON_HANDLER,"python/src/util.py":PYTHON_UTIL,
        "typescript/package.json":json.dumps({"name":"uripack-demo-typescript","version":"0.1.0","type":"module"}),
        "typescript/src/handler.ts":TS_HANDLER,"typescript/src/util.ts":TS_UTIL,
        "process-packs/count/process.v1.json":json.dumps({"schema":"demo.process/v1","process_uri":"demo://repository/query/count","effects":[]}),
    }
    for name, text in fixture.items():
        p = source / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text,encoding="utf-8")
    request = {"schema":"uripack.refactor-request/v1","operation":"plan","namespace":"demo",
               "units":[{"id":"count","include":["python","typescript","process-packs/count"],
                         "public_uris":["demo://repository/query/count"]}],"checks":["demo.differential"]}
    return {"source":source,"target":root/"uripack-extracted","request":request}


def _run(argv: list[str]) -> str:
    env = {"PATH":os.defpath,"PYTHONDONTWRITEBYTECODE":"1","LANG":"C.UTF-8"}
    result = subprocess.run(argv, capture_output=True, text=True, timeout=30, env=env, cwd="/", shell=False)
    if result.returncode:
        fail("UPK-DEMO-001", "Synthetic fixture execution failed (use pytest for diagnostics)")
    return result.stdout


def compare_fixture(source: Path, candidate: Path) -> dict:
    node = shutil.which("node")
    tsc = shutil.which("tsc")
    if not node or not tsc:
        fail("UPK-DEMO-001", "The cross-language demo requires installed node and tsc; no automatic download")
    cases = [{"items":[]},{"items":[1,2,3]},{"items":["ą",{"nested":True},None,"😀"]}]
    with tempfile.TemporaryDirectory(prefix="uripack-demo-ts-") as tmp:
        tmp_root = Path(tmp)
        compiled = []
        # Invoke the tsc JS entry through the resolved Node executable. No npm scripts.
        tsc_script = Path(tsc).resolve()
        for label, base in (("source",source),("candidate",candidate)):
            out = tmp_root/label
            _run([node,str(tsc_script),str(base/"typescript/src/handler.ts"),str(base/"typescript/src/util.ts"),
                  "--outDir",str(out),"--module","ES2022","--target","ES2022","--strict"])
            (out/"package.json").write_text('{"type":"module"}')
            compiled.append(out)
        for case in cases:
            inp = json.dumps(case,ensure_ascii=False)
            old_py = json.loads(_run([sys.executable,"-B",str(source/"python/src/handler.py"),inp]))
            new_py = json.loads(_run([sys.executable,"-B",str(candidate/"python/src/handler.py"),inp]))
            old_ts = json.loads(_run([node,str(compiled[0]/"handler.js"),inp]))
            new_ts = json.loads(_run([node,str(compiled[1]/"handler.js"),inp]))
            expected = {"uri":"demo://repository/query/count","count":len(case["items"])}
            if not old_py == new_py == old_ts == new_ts == expected:
                fail("UPK-CHECK-001", "Cross-language or old/new behavioral mismatch")
    return {"python_cases":len(cases),"typescript_cases":len(cases),"cross_language_cases":len(cases),
            "typescript_compiled":True,"real_subactor_tools_executed":0,"live_llm_calls":0,"guard_kind":"synthetic-fixture-only"}


class _FixtureGuard:
    """Only used by demo() with its own freshly created synthetic source."""
    required_checks = ["demo.differential"]
    identity = "synthetic-fixture-only:not-organism-guard"
    def __init__(self, fixture: dict):
        self.fixture = fixture
        self.result = None
    def call(self, action: str, plan: dict, payload: dict | None = None) -> dict:
        if Path(plan["source_root"]) != self.fixture["source"] or Path(plan["target_root"]) != self.fixture["target"]:
            fail("UPK-DEMO-001", "Fixture admission cannot address other roots")
        result = {}
        if action == "tool":
            if payload["tool_id"] != "demo.differential":
                fail("UPK-DEMO-001", "Unknown fixture tool")
            candidate = Path(payload["staging_root"])/"packs/count/tree"
            self.result = compare_fixture(self.fixture["source"],candidate)
            result = {"schema":"uripack.check-result/v1","status":"passed","subject_sha256":plan["plan_sha256"],
                      "artifact_sha256":artifact_digest(plan),"evidence_refs":["demo-evidence:sha256:"+digest(self.result)]}
        return {"allowed":True,"decision_ref":"demo:local:"+action,"lease_ref":"demo:fixture-lease", "fencing_token":1,
                "expires_at":int(time.time())+120,"result":result}


def demo(output: str | Path | None = None) -> dict:
    with tempfile.TemporaryDirectory(prefix="uripack-fixture-") as tmp:
        fixture = create_fixture(Path(tmp))
        plan = build_plan(fixture["request"],fixture["source"],fixture["target"])
        guard = _FixtureGuard(fixture)
        receipt = apply_plan(plan, guard)
        verified = verify_artifact(plan)
        # This rebuild also proves the selected source fixture remained unchanged.
        assert build_plan(fixture["request"],fixture["source"],fixture["target"]) == plan
        report = {"schema":"uripack.demo-report/v1","status":"passed","fixture_only":True,
                  "checks":guard.result,"files_copied":receipt["source_files_copied"],"verification":verified,
                  "source_unchanged":True,"production_cutover":False,"receipt":receipt}
        if output is not None:
            destination = Path(output).absolute()
            if destination.exists():
                fail("UPK-PATH-001", "Demo export destination already exists")
            destination.mkdir(parents=True)
            shutil.copytree(fixture["target"],destination/"extracted")
            (destination/"request.json").write_bytes(json_bytes(fixture["request"]))
            # Plan contains temporary paths and is evidence only, not a reusable apply plan.
            (destination/"plan.evidence-only.json").write_bytes(json_bytes(plan))
            (destination/"report.json").write_bytes(json_bytes(report))
        return report
