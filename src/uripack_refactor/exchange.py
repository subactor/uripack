"""Prepare a request-only LLM boundary without contacting any model or service."""
from __future__ import annotations
from .common import digest, fail
from .contracts import resource_json, validate


def llm_exchange(inventory: dict, intent: str) -> dict:
    if not isinstance(inventory, dict) or not isinstance(inventory.get("files"), list) or not isinstance(intent, str):
        fail("UPK-CONTRACT-001", "LLM exchange requires an inventory object and text intent")
    for item in inventory["files"]:
        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) for k in ("path", "language", "sha256")) or not isinstance(item.get("uris"), list):
            fail("UPK-CONTRACT-001", "Inventory item is not valid metadata")
    # The model receives metadata only; this is not a shell or authorization envelope.
    return {"schema":"uripack.llm-exchange/v1","operation":"propose-extraction",
            "source":{"kind":"untrusted-user-intent","text":intent},
            "inventory_ref":"sha256:" + digest(inventory),
            "candidates":[{"path":f["path"],"language":f["language"],"sha256":f["sha256"],
                           "uris":f["uris"]} for f in inventory.get("files",[])],
            "output_contract":resource_json("request.schema.json"),
            "execution_authority":False,"allowed_response_operation":"plan",
            "provider_binding":"operator-selected Subactor subllm/LLM gateway; not invoked by this command"}


def accept_proposal(proposal: dict) -> dict:
    validate("request", proposal)
    return proposal
