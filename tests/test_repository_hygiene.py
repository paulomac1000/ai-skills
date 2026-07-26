"""Repository keeps one current implementation without numbered iteration names."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ITERATION_NAME = re.compile(r"(?:^|[-_.])v[0-9]+(?=[-_.]|$)", re.IGNORECASE)
ACTION_VERSION_COMMENT = re.compile(r"(?m)^\s*uses:\s+[^#\n]+\s+#\s+v[0-9]+(?:[.][0-9]+)*\s*$", re.IGNORECASE)
DOCUMENTED_FORMAT_VERSION = re.compile(r"\b(?:schema\s+v[0-9]+|schema-version\s+[0-9]+)\b", re.IGNORECASE)


def tracked_files() -> list[Path]:
    return [
        path for path in ROOT.rglob("*") if path.is_file() and ".git" not in path.parts and ".venv" not in path.parts
    ]


def test_no_numbered_iteration_filenames_remain() -> None:
    offenders = [path.relative_to(ROOT).as_posix() for path in tracked_files() if ITERATION_NAME.search(path.name)]
    assert offenders == []


def test_workflows_do_not_use_human_version_alias_comments() -> None:
    offenders: list[str] = []
    for path in tracked_files():
        if path.suffix.lower() not in {".yml", ".yaml", ".j2", ".template"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if ACTION_VERSION_COMMENT.search(text):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_current_evidence_format_has_no_numbered_public_name() -> None:
    offenders: list[str] = []
    for path in tracked_files():
        if path.suffix.lower() not in {".md", ".py", ".yaml", ".yml", ".json"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if DOCUMENTED_FORMAT_VERSION.search(text):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


def test_coverage_database_is_local_only() -> None:
    assert not (ROOT / ".coverage").exists()
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".coverage" in ignore
    assert ".coverage.*" in ignore
