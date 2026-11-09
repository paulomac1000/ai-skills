"""Bounded static shell scope attribution with a documented grammar."""

from __future__ import annotations

import re
import shlex

from agents_md_shell_evidence_impl import (
    _logical_shell_lines,
    _normalize_invocation,
    _strip_command_substitutions,
    _strip_shell_comment,
)
from agents_md_shell_grammar import _segment_scope_kind, _split_ordered, _static_cd_target

_FUNCTION_DEF = re.compile(r"^\s*(?:function\s+([A-Za-z_][A-Za-z0-9_]*)|([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*\))\s*\{?")
_HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_SUPPORTED_CD_FLAGS = {"-P", "-L"}
_TRANSITION_COMMANDS = {"cd", "pushd", "popd"}


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
        if heredoc_end is not None:
            if raw_line.strip() == heredoc_end:
                heredoc_end = None
            continue
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
        line = _strip_shell_comment(line).strip()
        if not line:
            continue
        if line.startswith(("while ", "for ", "until ")) or line in {"while", "for", "until"}:
            issues.append(f"unsupported loop control flow is not statically attributable at {scope_label}: {line!r}")
            return scoped, issues
        if if_depth > 0:
            if line == "fi" or line.startswith("fi;") or line.startswith("fi "):
                if_depth -= 1
                continue
            if line.startswith("if ") or line == "if":
                if_depth += 1
                continue
            for operator, segment in _split_ordered(line):
                del operator
                heredoc_in_segment = _HEREDOC.search(segment)
                if heredoc_in_segment is not None:
                    heredoc_end = heredoc_in_segment.group(2)
                    break
                try:
                    tokens = shlex.split(segment) if segment.strip() else []
                except ValueError:
                    issues.append(f"workflow segment is not statically parseable at {scope_label}: {segment!r}")
                    return scoped, issues
                inner = segment
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
            heredoc_match = _HEREDOC.search(segment)
            if heredoc_match is not None:
                heredoc_end = heredoc_match.group(2)
                break
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
            if operator == "||" and last_was_transition:
                issues.append(
                    f"conditional reachability after a directory transition is unresolved at {scope_label}: {segment!r}"
                )
            normalized = _normalize_invocation(inner)
            if normalized is not None:
                scoped.append((normalized, effective))
            last_was_transition = False
            pop_frames(min(closes, len(scopes) - 1))
    return scoped, issues
