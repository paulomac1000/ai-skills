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
    """Ordered invocations with explicit frames, block tracking and fail-closed EOF."""
    scoped: list[tuple[str, str]] = []
    issues: list[str] = []
    last_was_transition = False
    scopes: list[str] = [base_directory]
    pushd_stacks: list[list[str]] = [[]]
    heredoc_end: str | None = None
    defined_functions: set[str] = set()
    function_depth: int | None = None
    if_depth = 0

    def pop_frames(count: int) -> None:
        for _ in range(min(count, len(scopes) - 1)):
            scopes.pop()
            pushd_stacks.pop()

    def emit_segment(segment: str) -> bool:
        """Return False when the segment is an unsupported conditional transition."""
        tokens = shlex.split(segment) if segment.strip() else []
        while tokens and tokens[0] in {"then", "else", "elif", "fi", "done", "do", "{", "!", "if"}:
            tokens = tokens[1:]
            segment = " ".join(tokens)
        if tokens and tokens[0] in _TRANSITION_COMMANDS:
            if last_was_transition:
                issues.append(
                    f"conditional control flow over a directory transition is unsupported at {scope_label}: {segment!r}"
                )
                return False
            target = _static_cd_target(tokens[1:], scopes[-1])
            if target is None:
                issues.append(f"workflow directory transition is unsupported at {scope_label}: {segment!r}")
                return False
            if tokens[0] == "pushd":
                pushd_stacks[-1].append(scopes[-1])
            scopes[-1] = target
            current = scopes[0]
            del current
            return True
        if tokens and tokens[0] in defined_functions:
            issues.append(
                f"shell function {tokens[0]!r} is invoked and its scope effects "
                f"are not statically resolvable at {scope_label}"
            )
            return False
        normalized = _normalize_invocation(segment)
        if normalized is not None:
            scoped.append((normalized, scopes[-1]))
        return True

    for raw_line in _logical_shell_lines(_strip_command_substitutions(run)):
        # 1) heredoc body consumption — before any function/conditional recognition.
        if heredoc_end is not None:
            if raw_line.strip() == heredoc_end:
                heredoc_end = None
            continue
        # 2) function definition tracking — but a line inside an active heredoc never reaches here.
        function_match = _FUNCTION_DEF.match(raw_line)
        if function_match is not None:
            defined_functions.add(function_match.group(1) or function_match.group(2))
            function_depth = raw_line.count("{") - raw_line.count("}")
            remainder = raw_line[raw_line.index("}") + 1 :] if function_depth <= 0 and "}" in raw_line else ""
            if function_depth <= 0:
                function_depth = None
                for operator, segment in _split_ordered(remainder):
                    del operator
                    normalized = _normalize_invocation(segment)
                    if normalized is not None:
                        scoped.append((normalized, scopes[-1]))
            continue
        # 3) comment stripping — before conditional/loop/segment parsing.
        line = _strip_shell_comment(raw_line).strip()
        if if_depth > 0:
            if line == "fi" or line.startswith("fi;") or line.startswith("fi "):
                if_depth -= 1
                remainder = line[2:].lstrip()
                if remainder.startswith(";"):
                    remainder = remainder[1:].strip()
                if remainder and if_depth == 0:
                    for operator, segment in _split_ordered(remainder):
                        del operator
                        normalized = _normalize_invocation(segment)
                        if normalized is not None:
                            scoped.append((normalized, scopes[-1]))
                continue
            if line.startswith("if ") or line == "if":
                if_depth += 1
                continue
        if function_depth is not None:
            function_depth += raw_line.count("{") - raw_line.count("}")
            if function_depth <= 0:
                function_depth = None
            continue
        # 4) loop headers fail closed
        if line.startswith(("while ", "for ", "until ")) or line in {"while", "for", "until"}:
            issues.append(f"unsupported loop control flow is not statically attributable at {scope_label}: {line!r}")
            return scoped, issues
        # 5) conditional opener: balanced one-liner inline, otherwise block depth
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
                inner = segment
                while tokens and tokens[0] in {"then", "else", "elif", "fi", "done", "do", "{", "!", "if"}:
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
            if not one_line_fi:
                if_depth += 1
            continue
        # 6) heredoc detection at segment level
        segments = _split_ordered(line)
        heredoc_index = None
        for position, (_operator, segment) in enumerate(segments):
            if _HEREDOC.search(segment):
                heredoc_index = position
                break
        if heredoc_index is not None:
            if heredoc_index == 0:
                command_part = _HEREDOC.sub("", segments[0][1], count=1).strip()
                if command_part:
                    normalized = _normalize_invocation(command_part)
                    if normalized is not None:
                        scoped.append((normalized, scopes[-1]))
            else:
                for operator, segment in segments[:heredoc_index]:
                    del operator
                    try:
                        tokens = shlex.split(segment) if segment.strip() else []
                    except ValueError:
                        issues.append(f"workflow segment is not statically parseable at {scope_label}: {segment!r}")
                        return scoped, issues
                    inner = segment
                    while tokens and tokens[0] in {"then", "else", "elif", "fi", "done", "do", "{", "!", "if"}:
                        tokens = tokens[1:]
                        inner = " ".join(tokens)
                    if not tokens:
                        continue
                    if tokens and tokens[0] in _TRANSITION_COMMANDS:
                        target = _static_cd_target(tokens[1:], scopes[-1])
                        if target is None:
                            issues.append(f"workflow directory transition is unsupported at {scope_label}: {segment!r}")
                            return scoped, issues
                        scopes[-1] = target
                        continue
                    normalized = _normalize_invocation(inner)
                    if normalized is not None:
                        scoped.append((normalized, scopes[-1]))
            heredoc_match = _HEREDOC.search(segments[heredoc_index][1])
            heredoc_end = heredoc_match.group(2) if heredoc_match else None
            continue
        # 7) ordinary segments
        for operator, segment in segments:
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
            inner = " ".join(tokens) if tokens else inner
            while tokens and tokens[0] in {"then", "else", "elif", "fi", "done", "do", "{", "!"}:
                tokens = tokens[1:]
                inner = " ".join(tokens)
            if not tokens:
                pop_frames(min(closes, len(scopes) - 1))
                continue
            if operator == "||" and last_was_transition:
                issues.append(
                    f"conditional reachability after a directory transition is unresolved at {scope_label}: {segment!r}"
                )
            if tokens[0] in _TRANSITION_COMMANDS and operator not in (None, ";"):
                issues.append(
                    f"conditional control flow over a directory transition is unsupported at {scope_label}: {segment!r}"
                )
                return scoped, issues
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

    # EOF-state diagnostics: no silently complete return with open structures.
    if heredoc_end is not None:
        issues.append(f"heredoc {heredoc_end!r} is unterminated at {scope_label}")
    if if_depth > 0:
        issues.append(f"conditional block is unterminated at {scope_label}")
    if function_depth is not None:
        issues.append(f"function definition is unterminated at {scope_label}")
    if len(scopes) > 1:
        issues.append(f"subshell is unterminated at {scope_label}")
    return scoped, issues
