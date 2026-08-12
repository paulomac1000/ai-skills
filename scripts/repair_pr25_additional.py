#!/usr/bin/env python3
"""Apply remaining verified regression alignment for PR 25; deleted before commit."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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
