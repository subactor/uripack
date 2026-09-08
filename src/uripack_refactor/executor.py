"""Materialize into a private staging directory, verify, then publish locally.

No source file is written or deleted, and no Git or package-registry write occurs.
"""
from __future__ import annotations
import os
import ctypes
import errno
from pathlib import Path
import shutil
import time
import uuid
from .common import (checked_root, digest, fail, json_bytes, load_document,
                     read_regular, relative_path, sha256, UripackError)
from .contracts import validate
from .guard import Guard
from .journal import Journal, verify_chain
from .planner import artifact_digest, validate_plan

STATE_PATH = ".uripack/receipt.json"


def _write(root: Path, relative: str, data: bytes, mode: int) -> None:
    parts = relative_path(relative).parts
    parent = root
    for part in parts[:-1]:
        parent = parent / part
        if parent.is_symlink():
            fail("UPK-PATH-001", "Symlink in staging directory")
        parent.mkdir(mode=0o700, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(parent / parts[-1], flags, mode)
    try:
        with os.fdopen(fd, "wb", closefd=False) as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.fchmod(fd, mode)
    finally:
        os.close(fd)


def _save_receipt(root: Path, receipt: dict) -> None:
    receipt = {**receipt,"receipt_sha256":digest(receipt)}
    state = root / ".uripack"
    if state.is_symlink():
        fail("UPK-PATH-001", "Symlink in receipt directory")
    state.mkdir(mode=0o700, exist_ok=True)
    tmp = state / ("receipt-" + uuid.uuid4().hex + ".tmp")
    with tmp.open("xb") as out:
        out.write(json_bytes(receipt))
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, state / "receipt.json")


def _files(root: Path) -> set[str]:
    actual = set()
    for directory, dirs, names in os.walk(root, followlinks=False, onerror=lambda exc: fail("UPK-PATH-001", "Artifact directory cannot be read")):
        for name in dirs + names:
            if (Path(directory)/name).is_symlink():
                fail("UPK-PATH-001", "Symlink found in materialized artifact")
        for name in names:
            actual.add((Path(directory)/name).relative_to(root).as_posix())
    return actual


def verify_artifact(plan: dict, target_root: str | Path | None = None, allow_receipt: bool = True) -> dict:
    validate_plan(plan, reobserve=False)
    root = checked_root(target_root or plan["target_root"])
    expected = {op["target"] for op in plan["operations"]}
    actual = _files(root)
    if allow_receipt:
        actual.discard(STATE_PATH)
    if actual != expected:
        fail("UPK-INTEGRITY-001", "Artifact has missing or unexpected files")
    for op in plan["operations"]:
        data, mode = read_regular(root, op["target"])
        if sha256(data) != op["sha256"] or mode != op["mode"]:
            fail("UPK-INTEGRITY-001", "Artifact content or executable mode differs from the plan")
    return {"schema":"uripack.artifact-verification/v1","status":"passed","plan_sha256":plan["plan_sha256"],
            "artifact_sha256":artifact_digest(plan),"files_verified":len(expected),"behavioral_equivalence_claimed":False}


def _live(response: dict) -> None:
    if response.get("allowed") is not True or response.get("expires_at",0) <= int(time.time()):
        fail("UPK-GUARD-001", "Admission expired or was denied during materialization")



def _publish_no_replace(staging: Path, target: Path) -> None:
    """Linux atomic RENAME_NOREPLACE: never replace even an empty target directory."""
    libc = ctypes.CDLL(None, use_errno=True)
    function = getattr(libc, "renameat2", None)
    if function is None:
        fail("UPK-PLATFORM-001", "Atomic no-replace publication requires Linux renameat2")
    function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    function.restype = ctypes.c_int
    if function(-100, os.fsencode(staging), -100, os.fsencode(target), 1) != 0:
        code = ctypes.get_errno()
        if code in {errno.EEXIST, errno.ENOTEMPTY}:
            fail("UPK-LEASE-001", "Target appeared concurrently; no overwrite performed")
        fail("UPK-PLATFORM-001", "Filesystem rejected atomic no-replace publication")


def apply_plan(plan: dict, guard: Guard) -> dict:
    """Library callers must supply a trusted Guard; CLI exposes no bypass flag."""
    validate_plan(plan)
    target = checked_root(plan["target_root"], exists=False)
    source = checked_root(plan["source_root"])
    if target.exists():
        verify_artifact(plan)
        state = target / STATE_PATH
        if not state.is_file():
            fail("UPK-RECONCILE-001", "Target exists without an extraction receipt; no overwrite performed")
        receipt = load_document(state)
        if receipt.get("receipt_sha256") != digest({k:v for k,v in receipt.items() if k != "receipt_sha256"}):
            fail("UPK-INTEGRITY-001", "Receipt digest mismatch")
        if receipt.get("plan_sha256") != plan["plan_sha256"] or not verify_chain(receipt.get("events",[])):
            fail("UPK-INTEGRITY-001", "Receipt does not match this plan")
        if receipt.get("status") != "EXTRACTED":
            fail("UPK-RECONCILE-001", "Artifact exists but protected completion is unresolved; inspect and reconcile, do not replay effects")
        # No effect is repeated and this does not extend or re-authorize any lease.
        return {**{k:v for k,v in receipt.items() if k != "receipt_sha256"},"replayed":False,"already_materialized":True,"authority_revalidated":False}
    staging = target.parent / ("." + target.name + ".uripack-stage-" + uuid.uuid4().hex)
    lock = target.parent / ("." + target.name + ".uripack-writer.lock")
    journal = Journal(plan["plan_sha256"])
    checks = sorted(set(plan["checks"]) | set(guard.required_checks))
    admission = guard.call("admit", plan, {"artifact_sha256":artifact_digest(plan),"staging_root":str(staging),
                                          "writer_lock":str(lock),"checks":checks,"mode":"extract-only"})
    _live(admission)
    journal.append("extraction.admitted", "ACCEPTED", admission["decision_ref"])
    try:
        lock_fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        fail("UPK-LEASE-001", "Another writer lock exists; no stale-lock deletion is attempted")
    lock_identity = os.fstat(lock_fd)
    published = False
    results = []
    try:
        with os.fdopen(lock_fd, "wb") as out:
            out.write(json_bytes({"plan_sha256":plan["plan_sha256"],"lease_ref":admission["lease_ref"],
                                  "fencing_token":admission["fencing_token"]}))
        staging.mkdir(mode=0o700)
        for op in plan["operations"]:
            _live(admission)
            if op["kind"] == "copy":
                data, mode = read_regular(source, op["source"])
                if sha256(data) != op["sha256"] or mode != op["mode"]:
                    fail("UPK-DRIFT-001", "Source changed after admission")
            else:
                data = op["content"].encode("utf-8")
            _write(staging, op["target"], data, op["mode"])
        verify_artifact(plan, staging, allow_receipt=False)
        journal.append("extraction.staged", "SUCCEEDED", "sha256:" + artifact_digest(plan))
        for tool_id in checks:
            answer = guard.call("tool", plan, {"tool_id":tool_id,"operation":"verify-extraction",
                               "source_root":str(source),"staging_root":str(staging),"artifact_sha256":artifact_digest(plan)})
            _live(answer)
            result = answer.get("result")
            validate("check-result", result)
            if result["status"] != "passed" or result["subject_sha256"] != plan["plan_sha256"] or result["artifact_sha256"] != artifact_digest(plan):
                fail("UPK-CHECK-001", "A required independent check failed or returned evidence for another artifact")
            results.append({"tool_id":tool_id, **result})
            journal.append("extraction.checked", "SUCCEEDED", result["evidence_refs"][0])
        validate_plan(plan)  # Detect additions/deletions and changes in the selected tree.
        verification = verify_artifact(plan, staging, allow_receipt=False)
        permit = guard.call("publish", plan, {"staging_root":str(staging),"artifact_sha256":artifact_digest(plan),
                                              "checks":results,"verification":verification})
        _live(permit)
        # Check again after the external boundary; a verifier may not modify the artifact.
        validate_plan(plan)
        verify_artifact(plan, staging, allow_receipt=False)
        receipt = {"schema":"uripack.extraction-receipt/v1","status":"MATERIALIZED_PENDING_COMPLETION",
                   "plan_sha256":plan["plan_sha256"],"artifact_sha256":artifact_digest(plan),
                   "source_sha256":plan["source_sha256"],"source_modified_by_uripack":False,
                   "source_files_copied":sum(o["kind"]=="copy" for o in plan["operations"]),
                   "guard":guard.identity,"checks":results,"events":journal.events,
                   "production_cutover":False,"git_effects":False,"registry_publication":False}
        _save_receipt(staging, receipt)
        if target.exists() or target.is_symlink():
            fail("UPK-LEASE-001", "Target appeared before local publication; no overwrite performed")
        # Advisory clone-local writer lock + Guard lease. Not a distributed filesystem lock.
        _publish_no_replace(staging, target)
        published = True
        parent_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        completion = guard.call("complete", plan, {"artifact_sha256":artifact_digest(plan),"receipt_ref":str(target/STATE_PATH)})
        _live(completion)
        journal.append("extraction.completed", "SUCCEEDED", completion["decision_ref"])
        receipt = {**receipt,"status":"EXTRACTED","events":journal.events}
        _save_receipt(target, receipt)
        verify_artifact(plan)
        return {**receipt,"already_materialized":False}
    except (UripackError, OSError):
        if published:
            fail("UPK-RECONCILE-001", "Artifact was materialized, but completion or final verification failed; inspect the target and reconcile without replay")
        raise
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)
        # Only the lock created by this call is removed. No foreign state cleanup.
        if lock.exists():
            observed_lock = lock.lstat()
            if (observed_lock.st_dev, observed_lock.st_ino) == (lock_identity.st_dev, lock_identity.st_ino):
                lock.unlink()
