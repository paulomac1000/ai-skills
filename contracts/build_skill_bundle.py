#!/usr/bin/env python3
"""Build a deterministic repository-shaped artifact for one governed skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

BUNDLE_STATE = ".ai-skill-bundle.json"
SKILL_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
MAX_FILES = 8192
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024


class BundleError(ValueError):
    """Raised when a skill bundle cannot be built safely."""


@dataclass(frozen=True)
class BundleFile:
    path: str
    sha256: str
    size: int


def _safe_relative(raw: str) -> Path:
    path = Path(raw)
    if not raw or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise BundleError(f"unsafe repository-relative dependency path: {raw}")
    return path


def _resolved_file(root: Path, relative: Path) -> Path:
    candidate = root / relative
    if candidate.is_symlink():
        raise BundleError(f"bundle input is a symlink: {relative.as_posix()}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as error:
        raise BundleError(f"bundle input cannot be resolved safely: {relative.as_posix()}: {error}") from error
    if not resolved.is_file():
        raise BundleError(f"bundle input is not a regular file: {relative.as_posix()}")
    return resolved


def _tree_paths(root: Path, relative_root: Path) -> set[Path]:
    source = root / relative_root
    if source.is_symlink() or not source.is_dir():
        raise BundleError(f"skill source is not a regular directory: {relative_root.as_posix()}")
    rows: set[Path] = set()
    for candidate in sorted(source.rglob("*")):
        relative = candidate.relative_to(root)
        if candidate.is_symlink():
            raise BundleError(f"bundle input is a symlink: {relative.as_posix()}")
        if candidate.is_file():
            rows.add(relative)
    return rows


def _read_file_bounded(root: Path, relative: Path, remaining: int) -> tuple[BundleFile, bytes]:
    resolved = _resolved_file(root, relative)
    try:
        announced_size = resolved.stat().st_size
    except OSError as error:
        raise BundleError(f"bundle input cannot be inspected: {relative.as_posix()}: {error}") from error
    if announced_size > remaining:
        raise BundleError(f"bundle exceeds byte limit {MAX_TOTAL_BYTES}")
    try:
        with resolved.open("rb") as handle:
            data = handle.read(remaining + 1)
    except OSError as error:
        raise BundleError(f"bundle input cannot be read: {relative.as_posix()}: {error}") from error
    if len(data) > remaining:
        raise BundleError(f"bundle exceeds byte limit {MAX_TOTAL_BYTES}")
    if len(data) != announced_size:
        raise BundleError(f"bundle input changed while being read: {relative.as_posix()}")
    return BundleFile(relative.as_posix(), hashlib.sha256(data).hexdigest(), len(data)), data


def _read_manifest(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise BundleError(f"skill manifest missing: {path}")
    try:
        size = path.stat().st_size
    except OSError as error:
        raise BundleError(f"skill manifest cannot be inspected: {error}") from error
    if size > MAX_MANIFEST_BYTES:
        raise BundleError("skill manifest exceeds maximum supported size")
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_MANIFEST_BYTES + 1)
    except OSError as error:
        raise BundleError(f"skill manifest cannot be read: {error}") from error
    if len(data) > MAX_MANIFEST_BYTES or len(data) != size:
        raise BundleError("skill manifest exceeded size bound or changed while being read")
    try:
        manifest = yaml.safe_load(data)
    except yaml.YAMLError as error:
        raise BundleError(f"skill manifest cannot be read: {error}") from error
    if not isinstance(manifest, dict):
        raise BundleError("skill manifest root must be an object")
    return manifest


def build_bundle(
    *,
    repository_root: Path,
    skill_id: str,
    output: Path,
    source_revision: str,
) -> dict:
    """Build one skill plus its declared repository-level shared resources."""
    if not SKILL_ID.fullmatch(skill_id):
        raise BundleError(f"invalid skill_id: {skill_id}")
    if not source_revision.strip():
        raise BundleError("source_revision must be non-empty")
    try:
        root = repository_root.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise BundleError(f"repository root cannot be resolved: {error}") from error
    if not root.is_dir():
        raise BundleError("repository root is not a directory")

    skill_relative = Path("skills") / skill_id
    manifest_path = root / skill_relative / "manifest.yaml"
    manifest = _read_manifest(manifest_path)
    if manifest.get("name") != skill_id:
        raise BundleError("skill manifest identity does not match requested skill")

    relative_paths = _tree_paths(root, skill_relative)
    shared = (manifest.get("dependencies") or {}).get("shared_resources") or []
    if not isinstance(shared, list):
        raise BundleError("dependencies.shared_resources must be a list")
    for raw in shared:
        if not isinstance(raw, str):
            raise BundleError("shared resource path must be a string")
        relative = _safe_relative(raw)
        candidate = root / relative
        if candidate.is_dir() and not candidate.is_symlink():
            relative_paths.update(_tree_paths(root, relative))
        else:
            _resolved_file(root, relative)
            relative_paths.add(relative)

    ordered_paths = sorted(relative_paths, key=lambda path: path.as_posix())
    if len(ordered_paths) > MAX_FILES:
        raise BundleError(f"bundle exceeds file limit {MAX_FILES}")

    rows: list[tuple[BundleFile, bytes]] = []
    total = 0
    for relative in ordered_paths:
        item, data = _read_file_bounded(root, relative, MAX_TOTAL_BYTES - total)
        total += item.size
        rows.append((item, data))

    target = output.resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError:
        pass
    else:
        raise BundleError("bundle output must be outside the source repository")
    if target.exists():
        if not target.is_dir():
            raise BundleError("bundle output must be a directory")
        if any(target.iterdir()):
            raise BundleError("bundle output must be absent or empty")
    target.mkdir(parents=True, exist_ok=True)

    for item, data in rows:
        destination = target / item.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)

    digest = hashlib.sha256()
    for item, data in rows:
        digest.update(item.path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(data).digest())
    state = {
        "schema_version": 1,
        "skill_id": skill_id,
        "source_revision": source_revision,
        "bundle_digest": digest.hexdigest(),
        "files": [asdict(item) for item, _data in rows],
    }
    (target / BUNDLE_STATE).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return state


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--skill-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()
    try:
        state = build_bundle(
            repository_root=args.repository_root,
            skill_id=args.skill_id,
            output=args.output,
            source_revision=args.source_revision,
        )
    except BundleError as error:
        print(json.dumps({"verdict": "fail", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"verdict": "pass", "bundle": state}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
