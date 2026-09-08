"""New uripack bridge protocol, NOT an assumed native Organism Guard API.

The operator installs an independently protected bridge mapping this protocol to
actual Organism Guard, leases and Subactor tools. No bridge means no CLI apply.
"""
from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time
import uuid
from typing import Any, Protocol
from .common import checked_root, digest, fail, json_bytes, load_document, parse_json, sha256
from .contracts import validate


class Guard(Protocol):
    required_checks: list[str]
    identity: str
    def call(self, action: str, plan: dict, payload: dict | None = None) -> dict: ...


def bounded_run(argv: list[str], payload: bytes, timeout: int = 30, max_bytes: int = 1024 * 1024) -> bytes:
    """Bound output and wall time; no shell, inherited secrets or source-controlled cwd."""
    if os.name != "posix":
        fail("UPK-PLATFORM-001", "The guarded subprocess transport requires POSIX")
    env = {"PATH":os.defpath,"LANG":"C.UTF-8","PYTHONNOUSERSITE":"1","PYTHONDONTWRITEBYTECODE":"1"}
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                cwd="/", env=env, start_new_session=True)
    except OSError:
        fail("UPK-GUARD-001", "Protected bridge could not be started")
    sel = selectors.DefaultSelector()
    stdout = bytearray()
    stderr_bytes = 0
    try:
        assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            os.set_blocking(stream.fileno(), False)
        sel.register(proc.stdin, selectors.EVENT_WRITE, "in")
        sel.register(proc.stdout, selectors.EVENT_READ, "out")
        sel.register(proc.stderr, selectors.EVENT_READ, "err")
        position = 0
        deadline = time.monotonic() + timeout
        while sel.get_map():
            if time.monotonic() >= deadline:
                fail("UPK-GUARD-001", "Protected bridge timed out; outcome may be unknown, no automatic retry")
            for key, _ in sel.select(min(0.1, max(0, deadline - time.monotonic()))):
                stream = key.fileobj
                if key.data == "in":
                    try:
                        n = os.write(stream.fileno(), payload[position:position+65536])
                        position += n
                    except BrokenPipeError:
                        position = len(payload)
                    if position >= len(payload):
                        sel.unregister(stream)
                        stream.close()
                else:
                    chunk = os.read(stream.fileno(), 65536)
                    if not chunk:
                        sel.unregister(stream)
                        stream.close()
                    elif key.data == "out":
                        stdout.extend(chunk)
                    else:
                        stderr_bytes += len(chunk)
                    if len(stdout) + stderr_bytes > max_bytes:
                        fail("UPK-LIMIT-001", "Protected bridge output limit exceeded")
        code = proc.wait(timeout=max(0.01, deadline - time.monotonic()))
        if code != 0:
            fail("UPK-GUARD-001", "Protected bridge failed; raw output withheld")
        return bytes(stdout)
    finally:
        sel.close()
        # A bridge request may not leave detached descendants holding its pipes.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        if proc.poll() is None:
            proc.wait()
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream and not stream.closed:
                stream.close()


class GuardBridge:
    """Pinned local executable is the trust boundary for this transport.

    Pinning is not a sandbox. The operator must protect config, executable,
    dependencies and lease store from the agent, using OS-level isolation.
    """
    def __init__(self, config_path: str | Path, source_root: str | Path, target_root: str | Path):
        self.config_path = Path(config_path).absolute()
        self.source = checked_root(source_root)
        self.target = checked_root(target_root, exists=False)
        self._outside(self.config_path)
        config = load_document(self.config_path)
        validate("guard-config", config)
        self.config = config
        self.config_bytes_sha256 = sha256(self.config_path.read_bytes())
        self.identity = "protected-stdio:" + digest(config)
        self.required_checks = sorted(config["required_checks"])
        if not self.required_checks:
            fail("UPK-GUARD-001", "Protected integration needs at least one independent required check")
        if not Path(config["argv"][0]).is_absolute():
            fail("UPK-GUARD-001", "Bridge executable must have an absolute path")
        if config["argv"][0] not in config["pinned_files"]:
            fail("UPK-GUARD-001", "Bridge executable is not pinned")
        for arg in config["argv"]:
            if Path(arg).is_absolute():
                self._outside(Path(arg))
                if Path(arg).is_file() and arg not in config["pinned_files"]:
                    fail("UPK-GUARD-001", "Executable or wrapper argument is not pinned")
        self.lease: tuple[str,int] | None = None
        self._verify_pins()

    def _outside(self, path: Path) -> None:
        p = path.resolve()
        for root in (self.source, self.target):
            if p == root or root in p.parents:
                fail("UPK-GUARD-001", "Guard configuration and implementation must live outside both repositories")

    def _verify_pins(self) -> None:
        if sha256(self.config_path.read_bytes()) != self.config_bytes_sha256:
            fail("UPK-INTEGRITY-001", "Guard configuration changed during execution")
        for filename, expected in self.config["pinned_files"].items():
            p = Path(filename)
            if not p.is_absolute() or not p.is_file():
                fail("UPK-GUARD-001", "Pinned bridge file is not available")
            self._outside(p)
            if sha256(p.read_bytes()) != expected:
                fail("UPK-INTEGRITY-001", "Protected bridge file digest mismatch")

    def call(self, action: str, plan: dict, payload: dict | None = None) -> dict:
        self._verify_pins()
        if action not in {"admit","tool","publish","complete"}:
            fail("UPK-GUARD-001", "Unknown bridge action")
        request = {"schema":"uripack.guard-request/v1","request_id":str(uuid.uuid4()),"action":action,
                   "subject_sha256":plan["plan_sha256"],"source_root":plan["source_root"],"target_root":plan["target_root"],
                   "plan":plan if action == "admit" else None,"payload":payload or {}}
        raw = bounded_run(self.config["argv"], json_bytes(request), self.config.get("timeout_seconds",30))
        try:
            response = parse_json(raw.decode("utf-8"))
        except UnicodeDecodeError:
            fail("UPK-GUARD-001", "Bridge response is not UTF-8 JSON")
        validate("guard-response", response)
        if response["request_id"] != request["request_id"] or response["subject_sha256"] != request["subject_sha256"]:
            fail("UPK-GUARD-001", "Bridge response does not match this request and exact plan")
        if response["allowed"] is not True:
            fail("UPK-GUARD-001", "Organism Guard bridge denied the operation")
        if response["expires_at"] <= int(time.time()):
            fail("UPK-GUARD-001", "Guard admission expired")
        current_lease = (response["lease_ref"],response["fencing_token"])
        if self.lease is not None and self.lease != current_lease:
            fail("UPK-GUARD-001", "Lease or fencing token changed; a new admission is required")
        self.lease = current_lease
        return response


def invoke_tool(guard: GuardBridge, plan: dict, tool_id: str, operation: str, domain_request: dict) -> dict:
    """Invoke any operator-registered Subactor capability through the same boundary.

    The bridge, not this package, MUST validate the native request schema and
    resolve the actual tool/API. A response is not interpreted as domain success.
    """
    import re
    from .planner import validate_plan
    validate_plan(plan)
    if not re.fullmatch(r"[a-z][a-z0-9.-]{0,95}",tool_id) or not re.fullmatch(r"[a-z][a-z0-9.-]{0,95}",operation):
        fail("UPK-CONTRACT-001", "Invalid tool or operation identifier")
    if not isinstance(domain_request,dict) or not isinstance(domain_request.get("schema"),str):
        fail("UPK-CONTRACT-001", "A native versioned DSL request is required")
    answer = guard.call("tool",plan,{"tool_id":tool_id,"operation":operation,
                                    "domain_request":domain_request,"domain_request_sha256":digest(domain_request)})
    return {"schema":"uripack.tool-invocation/v1","status":"protected-response-received",
            "domain_success_inferred":False,"tool_id":tool_id,"operation":operation,
            "domain_request_sha256":digest(domain_request),"guard_response":answer}
