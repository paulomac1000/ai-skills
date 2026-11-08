"""Ordered shell command extraction with statically resolvable directory transitions."""

from __future__ import annotations

import posixpath
import re

from agents_md_shell_evidence_impl import (
    _add_command_segments,
    _logical_shell_lines,
    _strip_shell_comment,
)

_CD_STATEMENT = re.compile(r"^\s*(?:cd|pushd)\s+(?P<target>\S+)(?:\s*&&\s*(?P<rest>\S.*))?$")


def _static_cd_target(target: str, current: str) -> str | None:
    """Return the post-transition directory for a statically resolvable cd/pushd target."""
    cleaned = target.strip("\"'")
    if (
        "$" in cleaned
        or "${" in cleaned
        or "`" in cleaned
        or "*" in cleaned
        or "?" in cleaned
        or cleaned in {"-", ""}
        or cleaned.startswith("~")
        or cleaned.startswith("/")
    ):
        return None
    joined = posixpath.normpath(posixpath.join(current, cleaned))
    if joined == ".." or joined.startswith("../"):
        return None
    return joined


def shell_invocations_with_scope(
    run: str, base_directory: str, scope_label: str
) -> tuple[list[tuple[str, str]], list[str]]:
    """Ordered shell invocations with statically resolvable cd/pushd transitions applied.

    An unresolvable directory transition aborts further attribution and reports a
    blocking issue: subsequent commands cannot be assigned a trustworthy scope.
    """
    scoped: list[tuple[str, str]] = []
    issues: list[str] = []
    current = base_directory
    heredoc_end: str | None = None
    for raw_line in _logical_shell_lines(run):
        line = raw_line.strip()
        if heredoc_end is not None:
            if line == heredoc_end:
                heredoc_end = None
            continue
        line = _strip_shell_comment(line).strip()
        if not line:
            continue
        heredoc = re.search(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1", line)
        if heredoc is not None:
            command = line[: heredoc.start()].rstrip()
            if command:
                segments: set[str] = set()
                _add_command_segments(segments, command)
                scoped.extend((segment, current) for segment in segments)
            heredoc_end = heredoc.group(2)
            continue
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\s*\(\)\s*\{?", line) or re.fullmatch(r"[{}]", line):
            continue
        cd_match = _CD_STATEMENT.match(line)
        if cd_match is not None:
            target = _static_cd_target(cd_match.group("target"), current)
            if target is None:
                issues.append(f"workflow cd transition is unresolved at {scope_label}")
                return scoped, issues
            current = target
            rest = cd_match.group("rest")
            if rest:
                rest_segments: set[str] = set()
                _add_command_segments(rest_segments, rest)
                scoped.extend((segment, current) for segment in rest_segments)
            continue
        line_segments: set[str] = set()
        _add_command_segments(line_segments, line)
        scoped.extend((segment, current) for segment in line_segments)
    return scoped, issues
