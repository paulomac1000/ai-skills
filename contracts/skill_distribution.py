#!/usr/bin/env python3
"""Install governed skills with explicit distribution, provenance, and ownership."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

DistributionMode = Literal["GLOBAL", "VENDORED", "EPHEMERAL"]
STATE_FILENAME = ".ai-skill-installation.json"
EPHEMERAL_ROOT = Path(".ai-skills/ephemeral")
MAX_FILES = 4096
MAX_TOTAL_BYTES = 32 * 1024 * 1024


class DistributionError(ValueError):
    """Raised when a requested installation cannot be performed safely."""


@dataclass(frozen=True)
class OwnedFile:
    path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class InstallationState:
    schema_version: int
    skill_id: str
    canonical_source: str
    source_revision: str
    source_digest: str
    distribution_mode: DistributionMode
    install_scope: str
    install_path: str
    installed_at: str
    managed_by: str
    update_policy: str
    cleanup_policy: str
    owned_files: tuple[OwnedFile, ...]


def _resolved_directory(path: Path) -> Path:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise DistributionError(f"directory cannot be resolved: {path}: {error}") from error
    if not resolved.is_dir():
        raise DistributionError(f"not a directory: {path}")
    return resolved


def _resolved_target(path: Path) -> Path:
    try:
        return path.expanduser().resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise DistributionError(f"target cannot be resolved: {path}: {error}") from error


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _source_inventory(source: Path) -> tuple[tuple[OwnedFile, bytes], ...]:
    rows: list[tuple[OwnedFile, bytes]] = []
    total = 0
    for candidate in sorted(source.rglob("*")):
        relative = candidate.relative_to(source).as_posix()
        if candidate.is_symlink():
            raise DistributionError(f"skill source contains symlink: {relative}")
        if not candidate.is_file():
            continue
        data = candidate.read_bytes()
        total += len(data)
        if len(rows) + 1 > MAX_FILES:
            raise DistributionError(f"skill source exceeds file limit {MAX_FILES}")
        if total > MAX_TOTAL_BYTES:
            raise DistributionError(f"skill source exceeds byte limit {MAX_TOTAL_BYTES}")
        rows.append((OwnedFile(relative, hashlib.sha256(data).hexdigest(), len(data)), data))
    if not rows:
        raise DistributionError("skill source contains no files")
    return tuple(rows)


def _source_digest(inventory: tuple[tuple[OwnedFile, bytes], ...]) -> str:
    digest = hashlib.sha256()
    for item, data in inventory:
        digest.update(item.path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def _gitignore_covers_ephemeral(project_root: Path) -> bool:
    ignore = project_root / ".gitignore"
    if not ignore.is_file() or ignore.is_symlink():
        return False
    patterns = {
        line.strip().lstrip("/")
        for line in ignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    return any(
        pattern.rstrip("/") in {".ai-skills", ".ai-skills/ephemeral"}
        for pattern in patterns
    )


def _validate_scope(mode: DistributionMode, project_root: Path, target: Path) -> None:
    inside = _is_within(target, project_root)
    if mode == "GLOBAL":
        if inside:
            raise DistributionError("GLOBAL installation target must be outside the project worktree")
        return
    if mode == "VENDORED":
        if not inside or target == project_root:
            raise DistributionError("VENDORED installation target must be a project-owned subdirectory")
        return
    if mode == "EPHEMERAL":
        expected = project_root / EPHEMERAL_ROOT
        if not _is_within(target, expected) or target == expected:
            raise DistributionError(
                f"EPHEMERAL installation target must be below {EPHEMERAL_ROOT.as_posix()}/"
            )
        if not _gitignore_covers_ephemeral(project_root):
            raise DistributionError(
                f"EPHEMERAL root {EPHEMERAL_ROOT.as_posix()}/ must be ignored by project .gitignore"
            )
        return
    raise DistributionError(f"unsupported distribution mode: {mode}")


def _load_state(target: Path) -> InstallationState | None:
    state_path = target / STATE_FILENAME
    if not state_path.exists():
        return None
    if state_path.is_symlink() or not state_path.is_file():
        raise DistributionError(f"invalid installation state path: {state_path}")
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        owned = tuple(OwnedFile(**item) for item in raw.pop("owned_files"))
        return InstallationState(owned_files=owned, **raw)
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise DistributionError(f"invalid installation state: {error}") from error


def _verify_owned_files(target: Path, state: InstallationState) -> None:
    expected = {item.path: item for item in state.owned_files}
    for relative, item in expected.items():
        candidate = target / relative
        if candidate.is_symlink() or not candidate.is_file():
            raise DistributionError(f"managed file is missing or replaced: {relative}")
        data = candidate.read_bytes()
        if len(data) != item.size or hashlib.sha256(data).hexdigest() != item.sha256:
            raise DistributionError(f"managed file was modified outside installer ownership: {relative}")

    allowed = set(expected) | {STATE_FILENAME}
    unexpected = [
        path.relative_to(target).as_posix()
        for path in target.rglob("*")
        if path.is_file() and path.relative_to(target).as_posix() not in allowed
    ]
    if unexpected:
        raise DistributionError(
            "installation target contains user/project-owned files: " + ", ".join(sorted(unexpected)[:10])
        )


def _state_json(state: InstallationState) -> str:
    payload = asdict(state)
    payload["owned_files"] = [asdict(item) for item in state.owned_files]
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def install(
    *,
    source: Path,
    target: Path,
    project_root: Path,
    mode: DistributionMode,
    skill_id: str,
    canonical_source: str,
    source_revision: str,
    managed_by: str,
    update_policy: str,
    cleanup_policy: str,
    installed_at: str | None = None,
) -> InstallationState:
    """Install or idempotently update one governed skill."""
    source_root = _resolved_directory(source)
    project = _resolved_directory(project_root)
    target_root = _resolved_target(target)
    _validate_scope(mode, project, target_root)

    inventory = _source_inventory(source_root)
    digest = _source_digest(inventory)
    existing = _load_state(target_root) if target_root.exists() else None

    if existing is not None:
        if existing.skill_id != skill_id or existing.distribution_mode != mode:
            raise DistributionError("existing installation is owned by a different skill or distribution mode")
        _verify_owned_files(target_root, existing)
        if existing.source_digest == digest and existing.source_revision == source_revision:
            return existing
    elif target_root.exists() and any(target_root.iterdir()):
        raise DistributionError("refusing to install into a non-empty unowned target")

    stamp = installed_at or datetime.now(timezone.utc).isoformat()
    state = InstallationState(
        schema_version=1,
        skill_id=skill_id,
        canonical_source=canonical_source,
        source_revision=source_revision,
        source_digest=digest,
        distribution_mode=mode,
        install_scope="machine-user" if mode == "GLOBAL" else "project",
        install_path=str(target_root),
        installed_at=stamp,
        managed_by=managed_by,
        update_policy=update_policy,
        cleanup_policy=cleanup_policy,
        owned_files=tuple(item for item, _data in inventory),
    )

    parent = target_root.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target_root.name}.install-", dir=parent))
    try:
        for item, data in inventory:
            destination = staging / item.path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        (staging / STATE_FILENAME).write_text(_state_json(state), encoding="utf-8")
        if target_root.exists():
            backup = Path(tempfile.mkdtemp(prefix=f".{target_root.name}.backup-", dir=parent))
            backup.rmdir()
            target_root.rename(backup)
            try:
                staging.rename(target_root)
            except Exception:
                backup.rename(target_root)
                raise
            shutil.rmtree(backup)
        else:
            staging.rename(target_root)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return state


def uninstall(*, target: Path, project_root: Path, mode: DistributionMode) -> InstallationState:
    """Remove only an installation whose owned files still match recorded digests."""
    project = _resolved_directory(project_root)
    target_root = _resolved_target(target)
    _validate_scope(mode, project, target_root)
    state = _load_state(target_root)
    if state is None:
        raise DistributionError("no managed installation state found")
    if state.distribution_mode != mode:
        raise DistributionError("requested mode does not match installation state")
    _verify_owned_files(target_root, state)

    for item in sorted(state.owned_files, key=lambda value: value.path.count("/"), reverse=True):
        (target_root / item.path).unlink()
    (target_root / STATE_FILENAME).unlink()
    for directory in sorted(
        (path for path in target_root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        try:
            directory.rmdir()
        except OSError:
            pass
    try:
        target_root.rmdir()
    except OSError as error:
        raise DistributionError("target contains files not owned by installer; refusing cleanup") from error
    return state


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("--source", type=Path, required=True)
    install_parser.add_argument("--target", type=Path, required=True)
    install_parser.add_argument("--project-root", type=Path, required=True)
    install_parser.add_argument("--mode", choices=("GLOBAL", "VENDORED", "EPHEMERAL"), required=True)
    install_parser.add_argument("--skill-id", required=True)
    install_parser.add_argument("--canonical-source", required=True)
    install_parser.add_argument("--source-revision", required=True)
    install_parser.add_argument("--managed-by", required=True)
    install_parser.add_argument("--update-policy", required=True)
    install_parser.add_argument("--cleanup-policy", required=True)

    uninstall_parser = subparsers.add_parser("uninstall")
    uninstall_parser.add_argument("--target", type=Path, required=True)
    uninstall_parser.add_argument("--project-root", type=Path, required=True)
    uninstall_parser.add_argument("--mode", choices=("GLOBAL", "VENDORED", "EPHEMERAL"), required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if args.command == "install":
            state = install(
                source=args.source,
                target=args.target,
                project_root=args.project_root,
                mode=args.mode,
                skill_id=args.skill_id,
                canonical_source=args.canonical_source,
                source_revision=args.source_revision,
                managed_by=args.managed_by,
                update_policy=args.update_policy,
                cleanup_policy=args.cleanup_policy,
            )
        else:
            state = uninstall(
                target=args.target,
                project_root=args.project_root,
                mode=args.mode,
            )
    except DistributionError as error:
        print(json.dumps({"verdict": "fail", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps({"verdict": "pass", "state": asdict(state)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
