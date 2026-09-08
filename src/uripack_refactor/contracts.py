from __future__ import annotations
from importlib.resources import files
from typing import Any
import json
from jsonschema import Draft202012Validator
from .common import canonical, fail


def resource_json(name: str) -> Any:
    return json.loads(files("uripack_refactor").joinpath("resources", name).read_text("utf-8"))


def validate(name: str, value: Any) -> None:
    canonical(value)
    if name in {"request", "plan"} and isinstance(value, dict) and value.get("schema") == f"uripack.refactor-{name}/v2":
        name += "-v2"
    errors = list(Draft202012Validator(resource_json(name + ".schema.json")).iter_errors(value))
    if errors:
        # Do not interpolate offending values; they can contain credentials.
        error = sorted(errors, key=lambda x: str(list(x.absolute_path)))[0]
        pointer = "/".join(str(x) for x in error.absolute_path)
        fail("UPK-CONTRACT-001", f"{name} contract rejected at /{pointer}: {error.validator}")
