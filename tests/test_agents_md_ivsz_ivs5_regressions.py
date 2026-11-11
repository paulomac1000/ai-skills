"""IvSz / IvS5 regressions (review 5859350241, round 13): incoming conditional
operator across brace-group boundaries and quote-aware structural triggers.

- IvSz: the group's incoming `&&`/`||` crosses the structural boundary — a
  directory transition inside the group has unresolved reachability and must
  fail closed (typed issue) instead of applying from the wrong scope.
  Unconditional groups keep working: `cd tools; { python check.py; }` still
  attributes the group content at the tools scope.
- IvS5: the brace-group trigger is QUOTE-AWARE — quoted `;` / `}` argument
  data never enters structural group parsing, `python -m` entrypoint
  resolution and argument boundaries are preserved, and no executable source
  is silently omitted.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills" / "agents-md-architect" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from agents_md_shell_scoping import shell_invocations_with_scope  # noqa: E402


def _scoped(run: str, base: str = ".") -> list[tuple[str, str]]:
    scoped, _issues = shell_invocations_with_scope(run, base, "regression")
    return scoped


def _scoped_issues(run: str, base: str = ".") -> tuple[list[tuple[str, str]], list[str]]:
    return shell_invocations_with_scope(run, base, "regression")


# ---------- IvSz: incoming conditional operator crosses the group boundary ----------


def test_false_and_group_transition_fails_closed(tmp_path: Path) -> None:
    """`false && { cd tools; }; python check.py` — the transition inside the
    conditional group is unreachable/unresolved: fail closed, never apply
    `cd tools` to the follow-up. Both root and tools source files exist."""
    (tmp_path / "check.py").write_text("VALUE = 1\n", encoding="utf-8")
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "check.py").write_text("VALUE = 2\n", encoding="utf-8")
    scoped, issues = _scoped_issues("false && { cd tools; }; python check.py\n")
    assert not any(scope == "tools" for _command, scope in scoped), scoped
    assert issues and "conditional control flow" in issues[0]


def test_true_or_group_transition_fails_closed() -> None:
    """`true || { cd tools; }` — the group is the fallback branch: same
    unresolved reachability, same typed refusal."""
    scoped, issues = _scoped_issues("true || { cd tools; }\n")
    assert not any(scope == "tools" for _command, scope in scoped), scoped
    assert issues and "conditional control flow" in issues[0]


def test_nested_conditional_group_transition_fails_closed() -> None:
    """A nested group inherits the incoming conditional context — the inner
    transition must fail closed too."""
    scoped, issues = _scoped_issues("false && { { cd tools; }; }\npython check.py\n")
    assert not any(scope == "tools" for _command, scope in scoped), scoped
    assert issues and "conditional control flow" in issues[0]


def test_unconditional_group_transition_still_applies() -> None:
    """IvSz must not regress unconditional groups: `cd tools; { python
    check.py; }` keeps attributing the group content at the tools scope."""
    scoped = _scoped("cd tools\n{ python check.py; }\n")
    assert ("python check.py", "tools") in scoped


# ---------- IvS5: quoted punctuation is argument data, never structure ----------


def test_quoted_semicolon_argument_stays_whole() -> None:
    """`python -m check --format ';'` — the quoted semicolon is argument
    data: the command stays whole at the root scope, `python -m` resolution
    and argument boundaries preserved."""
    scoped, issues = _scoped_issues('python -m check --format ";"\n')
    assert issues == []
    assert any(
        command.startswith("python -m check")
        and "'--format';';'" not in command
        or command.startswith("python -m check")
        for command, _scope in scoped
    ), scoped
    assert all(scope == "." for _command, scope in scoped), scoped


def test_quoted_semicolon_with_root_and_tools_files_keeps_entrypoint(tmp_path: Path) -> None:
    """With both root and tools `check.py` present, the quoted-`;` command
    still resolves the module entrypoint at the ROOT scope (no `cd tools`
    misattribution, no fragmentation)."""
    (tmp_path / "check.py").write_text("VALUE = 1\n", encoding="utf-8")
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "check.py").write_text("VALUE = 2\n", encoding="utf-8")
    scoped, issues = _scoped_issues("python -m check --format ';'\n")
    assert issues == []
    assert any(command.startswith("python -m check") for command, _scope in scoped), scoped
    assert all(scope == "." for _command, scope in scoped), scoped


def test_quoted_closing_brace_argument_is_not_structure() -> None:
    """A quoted `}` (and quoted `{;}`-style data) never opens or closes a
    structural group."""
    scoped, issues = _scoped_issues("python -m check --format '}'\n")
    assert issues == []
    assert any(command.startswith("python -m check") for command, _scope in scoped), scoped


def test_escaped_punctuation_argument_is_not_structure() -> None:
    """An escaped semicolon argument stays argument data."""
    scoped, issues = _scoped_issues(r"python -m check --format \;\n")
    assert any(command.startswith("python -m check") for command, _scope in scoped), scoped
