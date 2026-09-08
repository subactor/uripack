"""Compile explicit service profiles into inert, per-process Docker contexts."""
from __future__ import annotations

import json
from pathlib import PurePosixPath

from .common import fail, relative_path
from .contracts import validate


def service_files(unit: dict, files: list[dict]) -> tuple[dict[str, bytes], dict]:
    profile = unit["service"]
    validate("service", profile)
    if len(unit.get("public_uris", [])) != 1:
        fail("UPK-URI-001", "A standalone service requires exactly one public URI")
    if unit.get("depends_on"):
        fail("UPK-DEPENDENCY-001", "A standalone service cannot depend on another extracted tree; supply native dependencies or explicit service clients")
    selected = {item["path"]: item for item in files}
    workdir = profile["workdir"]
    if workdir != ".":
        relative_path(workdir)
        if PurePosixPath(workdir).as_posix() != workdir:
            fail("UPK-PATH-001", "Service workdir must be a canonical relative path")
        if not any(path.startswith(workdir + "/") for path in selected):
            fail("UPK-DEPENDENCY-001", "Service workdir has no selected files")
    dependency = profile["dependency_file"]
    relative_path(dependency)
    if PurePosixPath(dependency).as_posix() != dependency or dependency not in selected:
        fail("UPK-DEPENDENCY-001", "Dependency file must be an exact selected source path")
    root = "/app/tree"
    working = root if workdir == "." else root + "/" + workdir
    dependency_paths = [dependency]
    if profile["language"] == "python":
        install = ["python", "-m", "pip", "install", "--no-cache-dir",
                   "--disable-pip-version-check", "--require-hashes", "--only-binary=:all:",
                   "-r", root + "/" + dependency]
    else:
        prefix = "" if workdir == "." else workdir + "/"
        if dependency != prefix + "package-lock.json" or prefix + "package.json" not in selected:
            fail("UPK-DEPENDENCY-001", "Node services require package.json and package-lock.json in their selected workdir")
        dependency_paths.append(prefix + "package.json")
        install = ["npm", "ci", "--omit=dev", "--ignore-scripts", "--no-audit", "--no-fund"]

    # Values interpolated into Docker syntax have a restricted schema alphabet.
    # Commands use JSON exec form. No selected source or install command runs here.
    lines = [f"FROM {profile['base_image']}", "WORKDIR /app/tree",
             'COPY --chown=65532:65532 ["tree/", "/app/tree/"]', f"WORKDIR {working}",
             "RUN " + json.dumps(install), "USER 65532:65532"]
    ports = sorted(profile.get("ports", []))
    if ports:
        lines.append("EXPOSE " + " ".join(map(str, ports)))
    lines.extend(["ENTRYPOINT " + json.dumps(profile["command"]), "CMD []"])
    generated = {
        "Dockerfile": ("\n".join(lines) + "\n").encode(),
        ".dockerignore": b"**\n!Dockerfile\n!tree/\n!tree/**\n",
    }
    runtime = {
        "schema": "uripack.service-runtime/v1",
        "identity_ref": "#/layers/identity/public_uris/0",
        "profile": profile,
        "build": {"context": ".", "dockerfile": "Dockerfile", "executed": False},
        "dependencies": [{"path": path, "sha256": selected[path]["sha256"]}
                         for path in dependency_paths],
        "user": "65532:65532",
        "production_binding_verified": False,
    }
    return generated, runtime
