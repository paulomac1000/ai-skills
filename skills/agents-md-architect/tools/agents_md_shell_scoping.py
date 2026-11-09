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
    """Ordered invocations with a frame stack: each subshell owns directory + pushd state."""
    scoped: list[tuple[str, str]] = []
    issues: list[str] = []
    if_depth = 0
    last_was_transition = False
    scopes: list[str] = [base_directory]
    pushd_stacks: list[list[str]] = [[]]
    heredoc_end: str | None = None
    defined_functions: set[str] = set()
    function_depth: int | None = None

    def pop_frames(count: int) -> None:
        for _ in range(min(count, len(scopes) - 1)):
            scopes.pop()
            pushd_stacks.pop()

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
            if command:
                for operator, segment in _split_ordered(command):
                    del operator
                    normalized = _normalize_invocation(segment)
                    if normalized is not None:
                        scoped.append((normalized, scopes[-1]))
            heredoc_end = heredoc.group(2)
            continue
        if if_depth > 0:
            if line == "fi" or line.startswith("fi;") or line.startswith("fi "):
                if_depth -= 1
                continue
            if line.startswith("if ") or line == "if":
                if_depth += 1
                continue
            for operator, segment in _split_ordered(line):
                del operator
                try:
                    tokens = shlex.split(segment) if segment.strip() else []
                except ValueError:
                    issues.append(f"workflow segment is not statically parseable at {scope_label}: {segment!r}")
                    return scoped, issues
                while tokens and tokens[0] in {"then", "else", "elif", "fi", "done", "{", "!"}:
                    tokens = tokens[1:]
                    inner = " ".join(tokens)
                if not tokens:
                    continue
                if tokens[0] in _TRANSITION_COMMANDS:
                    issues.append(
                        f"conditional control flow over a directory transition is unsupported "
                        f"at {scope_label}: {line!r}"
                    )
                    return scoped, issues
                normalized = _normalize_invocation(inner)
                if normalized is not None:
                    scoped.append((normalized, scopes[-1]))
            continue
        if line.startswith("if ") or line == "if":
            segments = _split_ordered(line)
            last_segment = segments[-1][1] if segments else ""
            one_line_fi = last_segment == "fi" or last_segment.startswith("fi;") or last_segment.startswith("fi ")
            for operator, segment in segments:
                del operator
                try:
                    tokens = shlex.split(segment) if segment.strip() else []
                except ValueError:
                    issues.append(f"workflow segment is not statically parseable at {scope_label}: {segment!r}")
                    return scoped, issues
                while tokens and tokens[0] in {"then", "else", "elif", "fi", "done", "{", "!", "if"}:
                    tokens = tokens[1:]
                    inner = " ".join(tokens)
                if not tokens:
                    continue
                if tokens[0] in _TRANSITION_COMMANDS:
                    issues.append(
                        f"conditional control flow over a directory transition is unsupported at {scope_label}: {segment!r}"
                    )
                    return scoped, issues
                normalized = _normalize_invocation(inner)
                if normalized is not None:
                    scoped.append((normalized, scopes[-1]))
            if one_line_fi:
                continue
            if_depth += 1
            continue
        for operator, segment in _split_ordered(line):
            opens, closes, inner = _segment_scope_kind(segment)
            if opens:
                for _ in range(opens):
                    scopes.append(scopes[-1])
                    pushd_stacks.append(list(pushd_stacks[-1]))
            effective = scopes[-1]
            if not inner and closes:
                pop_frames(min(closes, len(scopes) - 1))
                continue
            try:
                tokens = shlex.split(inner)
            except ValueError:
                issues.append(f"workflow segment is not statically parseable at {scope_label}: {segment!r}")
                return scoped, issues
            if not tokens:
                pop_frames(min(closes, len(scopes) - 1))
                continue
            if tokens[0] in _TRANSITION_COMMANDS and operator not in (None, ";"):
                issues.append(
                    f"conditional control flow over a directory transition is unsupported at {scope_label}: {segment!r}"
                )
                return scoped, issues
            while tokens and tokens[0] in {"then", "else", "do", "{", "!", "fi", "done"}:
                tokens = tokens[1:]
                inner = " ".join(tokens)
            if not tokens:
                pop_frames(min(closes, len(scopes) - 1))
                continue
            if tokens[0] in _TRANSITION_COMMANDS:
                if tokens[0] == "popd":
                    if pushd_stacks[-1] and len(tokens) == 1:
                        target = pushd_stacks[-1].pop()
                    else:
                        target = None
                else:
                    target = _static_cd_target(tokens[1:], effective)
                if target is None:
                    issues.append(f"workflow directory transition is unsupported at {scope_label}: {segment!r}")
                    return scoped, issues
                if tokens[0] == "pushd":
                    pushd_stacks[-1].append(effective)
                scopes[-1] = target
                pop_frames(min(closes, len(scopes) - 1))
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
            pop_frames(min(closes, len(scopes) - 1))
    return scoped, issues
