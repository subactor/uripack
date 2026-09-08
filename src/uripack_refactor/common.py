"""Strict data boundary and no-follow filesystem reads; no source code imports."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_SAFE_INTEGER = 9007199254740991
IGNORED_DIRS = frozenset({".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".worktrees", "worktrees"})
SECRET_NAMES = frozenset({".env", ".npmrc", ".pypirc", "id_rsa", "id_ed25519", "credentials.json", "secrets.env"})
SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(rb"\b(?:ghp|gho|github_pat)_[A-Za-z0-9_]{24,}\b"),
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b"),
)

class UripackError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def fail(code: str, message: str) -> None:
    raise UripackError(code, message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: Any) -> bytes:
    """uripack.c14n/v1: UTF-16 sorted keys, JSON, integer-only I-JSON subset.

    This is NOT a claim to implement the full RFC8785 or the logs hash profile.
    """
    def emit(v: Any) -> str:
        if v is None:
            return "null"
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            if isinstance(v, float) and (not math.isfinite(v) or not v.is_integer()):
                fail("UPK-DATA-001", "Only safe integer numeric values are supported")
            if abs(v) > MAX_SAFE_INTEGER:
                fail("UPK-DATA-001", "Integer is outside the cross-language safe range")
            return str(int(v))
        if isinstance(v, str):
            try:
                v.encode("utf-8")
            except UnicodeEncodeError:
                fail("UPK-DATA-001", "Unpaired Unicode surrogate")
            return json.dumps(v, ensure_ascii=False)
        if isinstance(v, list):
            return "[" + ",".join(emit(x) for x in v) + "]"
        if isinstance(v, dict) and all(isinstance(k, str) for k in v):
            for k in v:
                emit(k)
            keys = sorted(v, key=lambda k: k.encode("utf-16be"))
            return "{" + ",".join(emit(k) + ":" + emit(v[k]) for k in keys) + "}"
        fail("UPK-DATA-001", "Only JSON objects, arrays, strings, safe integers, booleans and null are supported")
    return emit(value).encode("utf-8")


def digest(value: Any) -> str:
    return sha256(canonical(value))


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result: dict = {}
    for k, v in pairs:
        if k in result:
            fail("UPK-DATA-001", "Duplicate object key")
        result[k] = v
    return result


def parse_json(text: str) -> Any:
    try:
        result = json.loads(text, object_pairs_hook=_pairs,
                            parse_constant=lambda _: fail("UPK-DATA-001", "Non-finite JSON value"))
        canonical(result)
        return result
    except (ValueError, RecursionError) as exc:
        fail("UPK-DATA-001", f"Invalid JSON ({type(exc).__name__})")


def parse_document(data: bytes, suffix: str = ".json") -> Any:
    if len(data) > MAX_FILE_BYTES:
        fail("UPK-LIMIT-001", "Document exceeds size limit")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        fail("UPK-DATA-001", "Document must be UTF-8")
    if suffix not in {".yaml", ".yml"}:
        return parse_json(text)
    import yaml
    # Aliases and duplicate keys are rejected instead of expanded or overwritten.
    class StrictLoader(yaml.SafeLoader):
        pass
    def mapping(loader, node, deep=False):
        pairs = [(loader.construct_object(k, deep=deep), loader.construct_object(v, deep=deep))
                 for k, v in node.value]
        if any(not isinstance(k, str) for k, _ in pairs):
            fail("UPK-DATA-001", "YAML object keys must be strings")
        return _pairs(pairs)
    StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    try:
        if any(isinstance(e, yaml.events.AliasEvent) for e in yaml.parse(text)):
            fail("UPK-DATA-001", "YAML aliases are not accepted at the request boundary")
        result = yaml.load(text, Loader=StrictLoader)
        canonical(result)
        return result
    except (yaml.YAMLError, RecursionError) as exc:
        fail("UPK-DATA-001", f"Invalid YAML ({type(exc).__name__})")


def load_document(path: str | Path) -> Any:
    p = Path(path).absolute()
    root = checked_root(p.parent)
    data, _ = read_regular(root, p.name)
    return parse_document(data, p.suffix)


def json_bytes(value: Any) -> bytes:
    canonical(value)
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def relative_path(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        fail("UPK-PATH-001", "Expected a non-empty relative POSIX path")
    p = PurePosixPath(value)
    if p.is_absolute() or value != p.as_posix() or any(x in {"..", "."} for x in value.split("/")):
        fail("UPK-PATH-001", "Absolute, noncanonical and parent-relative paths are forbidden")
    if any(x in IGNORED_DIRS or x == ".subactor" for x in p.parts):
        fail("UPK-PATH-001", "Path refers to VCS, runtime state or excluded dependencies")
    if ":" in value or any(ord(c) < 32 for c in value):
        fail("UPK-PATH-001", "Control characters and colon are forbidden in paths")
    return p


def checked_root(path: str | Path, exists: bool = True) -> Path:
    p = Path(os.path.abspath(path))
    current = Path(p.anchor)
    for part in p.parts[1:]:
        current = current / part
        if current.is_symlink():
            fail("UPK-PATH-001", "Symlink in root path")
    if exists and not p.is_dir():
        fail("UPK-PATH-001", "Root must be an existing directory")
    return p


def read_regular(root: Path, relative: str, limit: int = MAX_FILE_BYTES) -> tuple[bytes, int]:
    """Walk with directory descriptors on POSIX. No symlink component is followed."""
    parts = relative_path(relative).parts
    if not hasattr(os, "O_NOFOLLOW"):
        fail("UPK-PLATFORM-001", "Secure extraction requires POSIX O_NOFOLLOW")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    file_fd = None
    try:
        for part in parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        st = os.fstat(file_fd)
        if not stat.S_ISREG(st.st_mode):
            fail("UPK-PATH-001", "Only regular files can be read")
        if st.st_size > limit:
            fail("UPK-LIMIT-001", "Source file exceeds limit")
        chunks = []
        remaining = limit + 1
        while remaining:
            part = os.read(file_fd, min(65536, remaining))
            if not part:
                break
            chunks.append(part)
            remaining -= len(part)
        data = b"".join(chunks)
        if len(data) > limit:
            fail("UPK-LIMIT-001", "Source grew beyond limit")
        return data, 0o755 if st.st_mode & stat.S_IXUSR else 0o644
    except OSError as exc:
        fail("UPK-PATH-001", f"Cannot read regular source file ({exc.errno})")
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(fd)


def secret_check(relative: str, data: bytes) -> None:
    if Path(relative).name in SECRET_NAMES or Path(relative).suffix in {".pem", ".key", ".p12", ".pfx"}:
        fail("UPK-SECRET-001", "Sensitive file is outside the extraction scope")
    if any(p.search(data) for p in SECRET_PATTERNS):
        fail("UPK-SECRET-001", "Potential credential material: extraction stopped (value not logged)")


def walk_files(root: Path, includes: list[str]) -> tuple[list[str], list[str]]:
    files: set[str] = set()
    excluded: set[str] = set()
    for value in includes:
        rel = relative_path(value)
        selected = root.joinpath(*rel.parts)
        current = root
        for part in rel.parts:
            current /= part
            if current.is_symlink():
                fail("UPK-PATH-001", "Symlink selected for extraction")
        if selected.is_file():
            files.add(rel.as_posix())
        elif selected.is_dir():
            for folder, dirs, names in os.walk(selected, followlinks=False, onerror=lambda exc: fail("UPK-PATH-001", "Selected source directory cannot be read")):
                dirs.sort()
                for name in list(dirs):
                    child = Path(folder) / name
                    if name in IGNORED_DIRS or name == ".subactor":
                        dirs.remove(name)
                        excluded.add(child.relative_to(root).as_posix())
                    elif child.is_symlink():
                        fail("UPK-PATH-001", "Symlink directory in selected source")
                for name in sorted(names):
                    child = Path(folder) / name
                    if child.is_symlink():
                        fail("UPK-PATH-001", "Symlink file in selected source")
                    relative = child.relative_to(root).as_posix()
                    relative_path(relative)
                    files.add(relative)
        else:
            fail("UPK-PATH-001", "Selected source path does not exist")
    return sorted(files), sorted(excluded)
