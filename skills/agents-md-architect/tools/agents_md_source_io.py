"""Confined reads and public-source surface discovery for gate-source auditing."""

from __future__ import annotations

from pathlib import Path

from agents_md_source_types import MAX_CLASSIFIER_FILE_BYTES, WELL_KNOWN_TASK_RUNNERS
from discover_repository import Discovery


def read_bounded(root: Path, relative: str) -> str:
    path = root / relative
    if path.is_symlink():
        raise ValueError(f"refusing symlink gate source: {relative}")
    resolved = path.resolve(strict=True)
    resolved.relative_to(root)
    if not resolved.is_file():
        raise ValueError(f"gate source is not a regular file: {relative}")
    data = resolved.read_bytes()
    if len(data) > MAX_CLASSIFIER_FILE_BYTES:
        raise ValueError(f"gate source exceeds {MAX_CLASSIFIER_FILE_BYTES} bytes: {relative}")
    return data.decode("utf-8")


def public_task_surfaces(discovery: Discovery) -> set[str]:
    surfaces = set(discovery.ci_files)
    surfaces.update(path for path in discovery.task_runners if Path(path).name in WELL_KNOWN_TASK_RUNNERS)
    surfaces.update(path for path in discovery.manifests if Path(path).name in {"package.json", "pyproject.toml"})
    return surfaces


def command_origin(relative: str, text: str, command: str) -> str:
    for line_number, line in enumerate(text.splitlines(), start=1):
        if command.strip() and command.strip() in line:
            return f"{relative}:{line_number}"
    return relative


def is_executable_shebang_script(root: Path, relative: str) -> bool:
    if not relative.startswith("scripts/"):
        return False
    path = root / relative
    try:
        if path.is_symlink() or path.stat().st_mode & 0o111 == 0:
            return False
        return read_bounded(root, relative).startswith("#!")
    except (OSError, UnicodeError, ValueError):
        return False
