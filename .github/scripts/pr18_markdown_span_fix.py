#!/usr/bin/env python3
"""Apply the final Markdown code-span regression fix for PR #18."""

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"{path}: expected exactly one occurrence of {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    Path("skills/agents-md-architect/tools/agents_md_parse.py"),
    """        else:
            return
        yield line[end:closing].strip(), index, closing + width
""",
    """        else:
            index = end
            continue
        yield line[end:closing].strip(), index, closing + width
""",
)

replace_once(
    Path("tests/test_final_audit_regressions.py"),
    """def test_recursive_yaml_alias_fails_closed_without_recursion_error() -> None:
""",
    """def test_unmatched_backtick_run_does_not_hide_a_later_code_span() -> None:
    line = "Read ``unfinished and then `missing.md`."
    assert list(parser.iter_references([(1, line)])) == [(1, "missing.md")]


def test_recursive_yaml_alias_fails_closed_without_recursion_error() -> None:
""",
)
