"""Bounded static shell scope attribution with a documented grammar."""

from __future__ import annotations

import posixpath
import re
import shlex

from agents_md_shell_evidence_impl import (
    _logical_shell_lines,
    _normalize_invocation,
    _strip_command_substitutions,
    _strip_shell_comment,
)

_FUNCTION_DEF = re.compile(r"^\s*(?:function\s+([A-Za-z_][A-Za-z0-9_]*)|([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*\))\s*\{?")
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_SUPPORTED_CD_FLAGS = {"-P", "-L"}
_TRANSITION_COMMANDS = {"cd", "pushd", "popd"}


def _split_ordered(command: str) -> list[tuple[str | None, str]]:
    """Split at unquoted ``;``/``&&``/``||`` preserving order and the preceding operator."""
    ordered: list[tuple[str | None, str]] = []
    operator: str | None = None
    current: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(command):
        character = command[index]
        if escaped:
            current.append(character)
            escaped = False
            index += 1
            continue
        if character == "\\" and quote != "'":
            current.append(character)
            escaped = True
            index += 1
            continue
        if quote is not None:
            current.append(character)
            if character == quote:
                quote = None
            index += 1
            continue
        if character in "'\"":
            quote = character
            current.append(character)
            index += 1
            continue
        separator = ""
        if character == ";":
            separator = ";"
        elif command.startswith("&&", index):
            separator = "&&"
        elif command.startswith("||", index):
            separator = "||"
        if separator:
            segment = "".join(current).strip()
            if segment:
                ordered.append((operator, segment))
            operator = separator
            current = []
            index += len(separator)
            continue
        current.append(character)
        index += 1
    segment = "".join(current).strip()
    if segment:
        ordered.append((operator, segment))
    return ordered


def _static_cd_target(tokens: list[str], current: str) -> str | None:
    """Resolve cd/pushd arguments to a static in-repository directory, else None."""
    flags = [token for token in tokens if token.startswith("-")]
    if any(flag not in _SUPPORTED_CD_FLAGS for flag in flags):
        return None
    operands = [token for token in tokens if not token.startswith("-")]
    if len(operands) != 1:
        return None
    cleaned = operands[0]
    if (
        "$" in cleaned
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


def _segment_scope_kind(segment: str) -> tuple[int, int, str]:
    """Return (leading subshell opens, trailing closes, inner text) for a segment."""
    leading = 0
    index = 0
    while index < len(segment) and segment[index] == "(":
        leading += 1
        index += 1
    trailing = 0
    end = len(segment)
    while end > index and segment[end - 1] == ")":
        trailing += 1
        end -= 1
    return leading, trailing, segment[index:end]


def shell_invocations_with_scope(
    run: str, base_directory: str, scope_label: str
) -> tuple[list[tuple[str, str]], list[str]]:
    """Ordered shell invocations with statically provable directory-scope attribution."""
    scoped: list[tuple[str, str]] = []
    issues: list[str] = []
    current = base_directory
    stack: list[str] = []
    depth = 0
    sub_current = base_directory
    heredoc_end: str | None = None
    defined_functions: set[str] = set()
    function_depth: int | None = None
    last_was_transition = False
    for raw_line in _logical_shell_lines(_strip_command_substitutions(run)):
        if function_depth is not None:
            function_depth += raw_line.count("{") - raw_line.count("}")
            if function_depth <= 0:
                function_depth = None
            continue
        function_match = _FUNCTION_DEF.match(raw_line)
        if function_match is not None:
            defined_functions.add(function_match.group(1) or function_match.group(2))
            function_depth = raw_line.count("{") - raw_line.count("}")
            if function_depth <= 0:
                function_depth = None
            continue
        line = raw_line.strip()
        if heredoc_end is not None:
            if line == heredoc_end:
                heredoc_end = None
            continue
        line = _strip_shell_comment(line).strip()
        if not line:
            continue
        heredoc = _HEREDOC.search(line)
        if heredoc is not None:
            command = line[: heredoc.start()].rstrip()
            for operator, segment in _split_ordered(command):
                del operator
                normalized = _normalize_invocation(segment)
                if normalized is not None:
                    scoped.append((normalized, sub_current if depth else current))
            heredoc_end = heredoc.group(2)
            continue
        for operator, segment in _split_ordered(line):
            opens, closes, inner = _segment_scope_kind(segment)
            if opens:
                depth += opens
                if depth == opens:
                    sub_current = current
            if depth > 0:
                effective = sub_current
            else:
                effective = current
            try:
                tokens = shlex.split(inner)
            except ValueError:
                issues.append(f"workflow segment is not statically parseable at {scope_label}: {segment!r}")
                return scoped, issues
            if not inner and closes:
                depth = max(0, depth - closes)
                if depth == 0:
                    sub_current = current
                continue
            if not tokens:
                continue
            if operator == "||" and last_was_transition:
                issues.append(
                    f"conditional reachability after a directory transition is unresolved at {scope_label}: {segment!r}"
                )
                return scoped, issues
            while tokens and tokens[0] in {"then", "else", "do", "{", "!", "fi", "done"}:
                tokens = tokens[1:]
                inner = " ".join(tokens)
            if not tokens:
                continue
            if tokens[0] in _TRANSITION_COMMANDS:
                if tokens[0] == "popd":
                    if stack and len(tokens) == 1:
                        target = stack.pop()
                    else:
                        target = None
                else:
                    target = _static_cd_target(tokens[1:], effective)
                if target is None:
                    issues.append(f"workflow directory transition is unsupported at {scope_label}: {segment!r}")
                    return scoped, issues
                if tokens[0] == "pushd":
                    stack.append(effective)
                if depth > 0:
                    sub_current = target
                else:
                    current = target
                if depth > 0:
                    sub_current = target
                else:
                    current = target
                if closes:
                    depth = max(0, depth - closes)
                    if depth == 0:
                        sub_current = current
                last_was_transition = True
                continue
            if tokens[0] in defined_functions:
                issues.append(
                    f"shell function {tokens[0]!r} is invoked and its scope effects "
                    f"are not statically resolvable at {scope_label}"
                )
                return scoped, issues
            normalized = _normalize_invocation(inner)
            if normalized is not None:
                scoped.append((normalized, effective))
            last_was_transition = False
            if closes:
                depth = max(0, depth - closes)
                if depth == 0:
                    sub_current = current
    return scoped, issues
