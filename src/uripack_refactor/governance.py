"""Read-only adoption inventory. Official validators remain authoritative."""
from __future__ import annotations
from pathlib import Path
from .common import checked_root, sha256

TARGET_MARKERS = (
    ".governance/manifest.json", ".governance/manifest.lock.json",
    ".governance/governance_check.py", ".subactor/manifest.json",
    "project/new-ticket.sh", "project/governance-check.sh", "project.sh",
    "AGENTS.md", "dsl-manifest.json",
)


def adoption_audit(root: str | Path) -> dict:
    base = checked_root(root)
    records = []
    for relative in TARGET_MARKERS:
        p = base / relative
        symlink = any((base.joinpath(*Path(relative).parts[:n])).is_symlink()
                      for n in range(1,len(Path(relative).parts)+1))
        present = p.is_file() and not symlink
        records.append({"path":relative,"present":present,"sha256":sha256(p.read_bytes()) if present else None,
                        "symlink_rejected":symlink})
    return {"schema":"uripack.adoption-audit/v1","files":records,"official_validator_executed":False,
            "conformance":"not-established","adoption_performed":False,
            "next_boundary":"Run the pinned wellmanifest validator and managed adoption/allocator through a protected tool binding; do not forge a governance lock or ticket."}
