from __future__ import annotations
import json
from pathlib import Path
import time
import pytest
from uripack_refactor.common import fail
from uripack_refactor.planner import artifact_digest, build_plan

class RecordingGuard:
    identity = "test-protocol-fake:not-live-organism"
    required_checks = ["tests.independent"]
    def __init__(self, deny=None, hook=None):
        self.calls = []
        self.deny = deny
        self.hook = hook
    def call(self, action, plan, payload=None):
        self.calls.append((action,payload))
        if self.hook:
            self.hook(action,plan,payload)
        if action == self.deny:
            fail("UPK-GUARD-001","test denial")
        result = {"schema":"uripack.check-result/v1","status":"passed","subject_sha256":plan["plan_sha256"],
                  "artifact_sha256":artifact_digest(plan),"evidence_refs":["test:independent"]}
        return {"allowed":True,"decision_ref":"test:decision","lease_ref":"test:lease","fencing_token":7,
                "expires_at":int(time.time())+90,"result":result}

@pytest.fixture
def sample(tmp_path):
    source = tmp_path/"source"
    (source/"unit").mkdir(parents=True)
    (source/"unit/process.json").write_text(json.dumps({"process_uri":"demo://repository/query/count"}))
    (source/"unit/main.py").write_text('URI = "demo://repository/query/count"\ndef work(x):\n    return len(x)\n')
    (source/"unit/main.ts").write_text('export const uri = "demo://repository/query/count";\n')
    (source/"unit/pyproject.toml").write_text('[project]\nname="demo-python"\nversion="0.1.0"\n[project.scripts]\ncount="demo:main"\n')
    (source/"unit/package.json").write_text(json.dumps({"name":"demo-node","version":"0.1.0","scripts":{"postinstall":"echo never-run"}}))
    (source/"unrelated.txt").write_text("foreign work must survive")
    request={"schema":"uripack.refactor-request/v1","operation":"plan","namespace":"subactor",
             "units":[{"id":"count","include":["unit"],"public_uris":["demo://repository/query/count"]}]}
    target=tmp_path/"uripack"
    return source,target,request

@pytest.fixture
def plan(sample):
    return build_plan(sample[2],sample[0],sample[1])

@pytest.fixture
def guard():
    return RecordingGuard()
