"""Shared helpers for the temporary PR #18 source transformation."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def replace_between(text: str, start: str, end: str, replacement: str, *, label: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        raise RuntimeError(f"{label}: start marker not found")
    end_index = text.find(end, start_index + len(start))
    if end_index < 0:
        raise RuntimeError(f"{label}: end marker not found")
    if text.find(start, start_index + len(start)) >= 0:
        raise RuntimeError(f"{label}: start marker is not unique")
    return text[:start_index] + replacement + text[end_index:]


def write_atomically(outputs: dict[str, str]) -> None:
    staged: list[tuple[Path, Path]] = []
    try:
        for relative, content in outputs.items():
            destination = ROOT / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            mode = stat.S_IMODE(destination.stat().st_mode) if destination.exists() else 0o644
            descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(mode)
            staged.append((temporary, destination))
        for temporary, destination in staged:
            os.replace(temporary, destination)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
