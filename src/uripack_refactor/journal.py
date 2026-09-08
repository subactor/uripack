"""Local, non-authoritative evidence. Not a wellmanifest/logs wire implementation."""
from __future__ import annotations
import time
from .common import digest

class Journal:
    def __init__(self, plan_sha256: str):
        self.plan_sha256 = plan_sha256
        self.events: list[dict] = []

    def append(self, event_type: str, outcome: str, evidence_ref: str) -> dict:
        value = {"schema":"uripack.local-event/v1","sequence":len(self.events)+1,
                 "previous_hash":self.events[-1]["event_hash"] if self.events else "0"*64,
                 "plan_sha256":self.plan_sha256,"timestamp":int(time.time()),"event_type":event_type,
                 "outcome":outcome,"evidence_ref":evidence_ref,"authoritative":False}
        value["event_hash"] = digest(value)
        self.events.append(value)
        return value


def verify_chain(events: list[dict]) -> bool:
    previous = "0"*64
    for n, event in enumerate(events,1):
        if event.get("sequence") != n or event.get("previous_hash") != previous:
            return False
        if digest({k:v for k,v in event.items() if k != "event_hash"}) != event.get("event_hash"):
            return False
        previous = event["event_hash"]
    return True
