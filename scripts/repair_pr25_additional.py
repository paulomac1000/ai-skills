#!/usr/bin/env python3
"""Apply remaining verified regression alignment for PR 25; deleted before commit."""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "skills/mcp-server-architect/references/python-fastmcp.md",
    "It is **not** an SDK profile and must not be used to choose an implementation by class name.",
    "It is not an SDK profile and must not be used to choose an implementation by class name.",
)
replace_once(
    "tests/test_mcp_migration_standard.py",
    '    assert "mcp==2.0.0" in official\n',
    '    assert "dependency lock and assessment identify the exact package version" in official\n',
)
replace_once(
    "tests/test_post_review_regressions.py",
    '    assert "mcp.streamable_http_app()" in source\n',
    '    assert "mcp.streamable_http_app(" in source\n    assert "stateless_http=True" in source\n',
)
replace_once(
    "tests/test_templates.py",
    '    assert "mapfile -t packages < nupkg/publish-files.txt" in publisher["run"]\n',
    '    assert "mapfile -t packages < nupkg/verified-publish-files.txt" in publisher["run"]\n',
)

base_digest = os.environ.get("PYTHON_BASE_IMAGE_DIGEST", "")
if not DIGEST.fullmatch(base_digest):
    raise RuntimeError("PYTHON_BASE_IMAGE_DIGEST must be an exact sha256 digest")
replace_once(
    "skills/mcp-server-architect/tools/python-template/Dockerfile.template",
    "FROM python:3.12.11-slim-bookworm@sha256:8d8d1a11f5f2e7879d4b9be3ec040b1f48d99b5284942230ca11843bb65c2d4a\n",
    f"FROM python:3.12.11-slim-bookworm@{base_digest}\n",
)
