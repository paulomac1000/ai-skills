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


def _collect_file(root: Path, relative: Path) -> tuple[BundleFile, bytes]:
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
    data = resolved.read_bytes()
    return BundleFile(relative.as_posix(), hashlib.sha256(data).hexdigest(), len(data)), data


def _collect_tree(root: Path, relative_root: Path) -> list[tuple[BundleFile, bytes]]:
    source = root / relative_root
    if source.is_symlink() or not source.is_dir():
        raise BundleError(f"skill source is not a regular directory: {relative_root.as_posix()}")
    rows: list[tuple[BundleFile, bytes]] = []
    for candidate in sorted(source.rglob("*")):
        relative = candidate.relative_to(root)
        if candidate.is_symlink():
            raise BundleError(f"bundle input is a symlink: {relative.as_posix()}")
        if candidate.is_file():
            rows.append(_collect_file(root, relative))
    return rows


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
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise BundleError(f"skill manifest missing: {skill_relative.as_posix()}/manifest.yaml")
    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise BundleError(f"skill manifest cannot be read: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("name") != skill_id:
        raise BundleError("skill manifest identity does not match requested skill")

    rows = _collect_tree(root, skill_relative)
    shared = (manifest.get("dependencies") or {}).get("shared_resources") or []
    if not isinstance(shared, list):
        raise BundleError("dependencies.shared_resources must be a list")

    for raw in shared:
        if not isinstance(raw, str):
            raise BundleError("shared resource path must be a string")
        relative = _safe_relative(raw)
        candidate = root / relative
        if candidate.is_dir() and not candidate.is_symlink():
            rows.extend(_collect_tree(root, relative))
        else:
            rows.append(_collect_file(root, relative))

    dedup: dict[str, tuple[BundleFile, bytes]] = {}
    total = 0
    for item, data in rows:
        dedup[item.path] = (item, data)
    ordered = [dedup[key] for key in sorted(dedup)]
    for item, _data in ordered:
        total += item.size
    if len(ordered) > MAX_FILES:
        raise BundleError(f"bundle exceeds file limit {MAX_FILES}")
    if total > MAX_TOTAL_BYTES:
        raise BundleError(f"bundle exceeds byte limit {MAX_TOTAL_BYTES}")

    target = output.resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError:
        pass
    else:
        raise BundleError("bundle output must be outside the source repository")
    if target.exists() and any(target.iterdir()):
        raise BundleError("bundle output must be absent or empty")
    target.mkdir(parents=True, exist_ok=True)

    for item, data in ordered:
        destination = target / item.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)

    digest = hashlib.sha256()
    for item, data in ordered:
        digest.update(item.path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(data).digest())
    state = {
        "schema_version": 1,
        "skill_id": skill_id,
        "source_revision": source_revision,
        "bundle_digest": digest.hexdigest(),
        "files": [asdict(item) for item, _data in ordered],
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
