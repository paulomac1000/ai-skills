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
from agents_md_shell_grammar import (
    _segment_scope_kind,
    _split_ordered,
    _static_cd_target,
    _structural_brace_delta,
    _structural_close_index,
)

_FUNCTION_DEF = re.compile(r"^\s*(?:function\s+([A-Za-z_][A-Za-z0-9_]*)|([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*\))\s*\{?")
_HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_KEYWORDS = {"then", "else", "elif", "fi", "done", "do", "{", "!", "if"}
_TRANSITION_COMMANDS = {"cd", "pushd", "popd"}
_MAX_SUBSTITUTION_DEPTH = 4
_MAX_SUBSTITUTION_CHARS = 2048


def shell_invocations_with_scope(
    run: str, base_directory: str, scope_label: str, *, _depth: int = 0
) -> tuple[list[tuple[str, str]], list[str]]:
    """Ordered invocations with explicit frames, block tracking and fail-closed EOF."""
    scoped: list[tuple[str, str]] = []
    issues: list[str] = []
    scopes: list[str] = [base_directory]
    pushd_stacks: list[list[str]] = [[]]
    conditional_frames: list[bool] = []
    last_was_transition = False
    heredoc_end: str | None = None
    defined_functions: set[str] = set()
    function_depth: int | None = None
    pending_function_brace = False
    if_depth = 0

    def pop_frames(count: int) -> None:
        for _ in range(min(count, len(scopes) - 1)):
            scopes.pop()
            pushd_stacks.pop()

    def fail(message: str) -> bool:
        issues.append(message)
        return False

    def run_engine(
        segments: list[tuple[str | None, str]], substitutions: list[str], inline_state: dict[str, int]
    ) -> bool:
        """The single ordered scope engine shared by every segment source."""
        nonlocal last_was_transition
        pending = list(substitutions)
        for operator, segment in segments:
            opens, closes, inner = _segment_scope_kind(segment)
            for _ in range(opens):
                scopes.append(scopes[-1])
                pushd_stacks.append(list(pushd_stacks[-1]))
            effective = scopes[-1]
            conditional_context = conditional_frames[-1] if conditional_frames else False
            for _ in range(segment.count("SUBST$")):  # substitution bodies are isolated scopes
                if not pending:
                    break
                substitution = pending.pop(0)
                if not substitution.strip():
                    continue
                if _depth + 1 > _MAX_SUBSTITUTION_DEPTH or len(substitution) > _MAX_SUBSTITUTION_CHARS:
                    return fail(
                        f"command substitution exceeds the bounded static analysis envelope "
                        f"at {scope_label}: {substitution!r}"
                    )
                nested_scoped, nested_issues = shell_invocations_with_scope(
                    substitution, effective, f"{scope_label} substitution", _depth=_depth + 1
                )
                scoped.extend(nested_scoped)
                issues.extend(nested_issues)
            try:
                tokens = shlex.split(inner) if inner.strip() else []
            except ValueError:
                return fail(f"workflow segment is not statically parseable at {scope_label}: {segment!r}")
            command = shlex.join(tokens)
            while tokens and tokens[0] in _KEYWORDS:
                head = tokens[0]
                tokens = tokens[1:]
                if head == "if":  # ordered frames: opening pushes the conditional context (F1/F3)
                    inline_state["depth"] += 1
                    conditional_frames.append(True)
                elif head == "fi":  # closing restores the parent frame context (F3)
                    inline_state["depth"] -= 1
                    if conditional_frames:
                        conditional_frames.pop()
                    if inline_state["depth"] <= 0:
                        inline_state["depth"] = 0
                command = shlex.join(tokens) if tokens else ""
            if not tokens:
                pop_frames(min(closes, len(scopes) - 1))
                continue
            if operator == "||" and last_was_transition:
                return fail(
                    f"conditional reachability after a directory transition is unresolved at {scope_label}: {segment!r}"
                )
            if tokens[0] in _TRANSITION_COMMANDS and (operator not in (None, ";") or conditional_context):
                return fail(
                    f"conditional control flow over a directory transition is unsupported at {scope_label}: {segment!r}"
                )
            if tokens[0] in _TRANSITION_COMMANDS:
                if tokens[0] == "popd":
                    target = pushd_stacks[-1].pop() if pushd_stacks[-1] and len(tokens) == 1 else None
                else:
                    target = _static_cd_target(tokens[1:], effective)
                if target is None:
                    return fail(f"workflow directory transition is unsupported at {scope_label}: {segment!r}")
                if tokens[0] == "pushd":
                    pushd_stacks[-1].append(effective)
                scopes[-1] = target
                pop_frames(min(closes, len(scopes) - 1))
                last_was_transition = True
                continue
            if tokens[0] in defined_functions:
                return fail(
                    f"shell function {tokens[0]!r} is invoked and its scope effects "
                    f"are not statically resolvable at {scope_label}"
                )
            normalized = _normalize_invocation(command)
            if normalized is not None:
                scoped.append((normalized, effective))
            last_was_transition = False
            pop_frames(min(closes, len(scopes) - 1))
        return True

    def run_segments(segments: list[tuple[str | None, str]], substitutions: list[str]) -> bool:
        """Engine pass that folds residual conditional opens into the block depth."""
        nonlocal if_depth
        inline_state = {"depth": 0}
        if not run_engine(segments, substitutions, inline_state):
            return False
        if_depth += inline_state["depth"]
        return True

    def run_line(line: str, substitutions: list[str]) -> bool:
        return run_segments(_split_ordered(line), substitutions)

    def definition_suffix(line: str, substitutions: list[str]) -> bool:
        """Route a closed definition's same-line suffix through the ordered engine."""
        close = _structural_close_index(line)
        if close is None:
            return True
        suffix = line[close:].strip()
        return not suffix or run_line(suffix, substitutions)

    def heredoc_strip(segments: list[tuple[str | None, str]]) -> tuple[list[tuple[str | None, str]], int] | None:
        """Strip the first heredoc operator, record its delimiter, keep every segment in order."""
        nonlocal heredoc_end
        for position, (_operator, segment) in enumerate(segments):
            opener = _HEREDOC.search(segment)
            if opener is None:
                continue
            heredoc_end = opener.group(2)
            stripped = [
                (operator, _HEREDOC.sub("", segment, count=1) if index == position else segment)
                for index, (operator, segment) in enumerate(segments)
            ]
            return stripped, position
        return None

    pending_substitution: list[str] | None = None
    for raw_line in _logical_shell_lines(run):
        if heredoc_end is not None:  # heredoc bodies are data: consumed before comment stripping
            if raw_line.strip() == heredoc_end:
                heredoc_end = None
            continue
        if pending_substitution is not None:  # a multi-line substitution span consumes continuation lines
            pending_substitution.append(_strip_shell_comment(raw_line).strip())
            folded, substitutions, unterminated = _strip_command_substitutions("\n".join(pending_substitution))
            if unterminated:
                continue
            pending_substitution = None
        else:
            line = _strip_shell_comment(raw_line).strip()  # comments before structure matching
            if not line:
                continue
            folded, substitutions, unterminated = _strip_command_substitutions(line)
            if unterminated:  # span opens across lines: fold continuations before attribution
                pending_substitution = [line]
                continue
        line = folded.strip()
        if not line:
            continue
        if len(_HEREDOC.findall(line)) > 1:  # multiple heredoc redirections are outside the bounded grammar
            fail(f"multiple heredoc redirections are unsupported at {scope_label}: {line!r}")
            return scoped, issues
        if pending_function_brace:  # ok_b: a named definition awaits its opening brace
            if line == "{":
                function_depth = 1
                pending_function_brace = False
                continue
            fail(f"function definition is missing its opening brace at {scope_label}: {line!r}")
            return scoped, issues
        if function_depth is not None:  # inside a definition body
            opener = _HEREDOC.search(line)
            if opener is not None:  # a body heredoc is data: consume delimiter + body; the uncalled
                heredoc_end = opener.group(2)  # definition's opener command is never attributed (qpx3)
                continue
            function_depth += _structural_brace_delta(line)  # quoted braces are data (5839793113)
            if function_depth <= 0:
                function_depth = None
                if not definition_suffix(line, substitutions):
                    return scoped, issues
            continue
        definition = _FUNCTION_DEF.match(line)
        if definition is not None:
            defined_functions.add(definition.group(1) or definition.group(2))
            delta = _structural_brace_delta(line)
            if delta > 0:
                function_depth = delta  # same-line opening brace: body follows
            elif delta < 0:
                fail(f"function definition brace balance is unsupported at {scope_label}: {line!r}")
                return scoped, issues
            elif "{" in line:
                function_depth = None  # inline closed definition
                if not definition_suffix(line, substitutions):
                    return scoped, issues
            else:
                pending_function_brace = True  # ok_b: opening brace expected on a following line
            continue
        if line.startswith(("while ", "for ", "until ")) or line in {"while", "for", "until"}:
            issues.append(f"unsupported loop control flow is not statically attributable at {scope_label}: {line!r}")
            return scoped, issues
        if if_depth > 0:
            if line == "fi" or line.startswith("fi;") or line.startswith("fi "):
                if_depth -= 1
                if conditional_frames:  # the closing fi restores its parent conditional frame (F3)
                    conditional_frames.pop()
                suffix = line[2:].strip()
                if suffix.startswith(";"):
                    suffix = suffix[1:].strip()
                # qpx-: an inner fi's suffix runs with the INHERITED frame context — never
                # silently dropped while an outer conditional is still open, and never made
                # unconditional by the inner close.
                if suffix and not run_line(suffix, substitutions):
                    return scoped, issues
                continue
            opener = _HEREDOC.search(line)
            if opener is not None:  # a body heredoc isolates its data from scope parsing
                heredoc_end = opener.group(2)
                prefix = _HEREDOC.sub("", line, count=1).strip()
                if prefix and not run_line(prefix, substitutions):
                    return scoped, issues
                continue
            if not run_line(line, substitutions):  # body invocations kept; conditional context from frames
                return scoped, issues
            continue
        stripped = heredoc_strip(segments := _split_ordered(line))
        if stripped is not None:  # heredoc recognition precedes ordinary parsing
            if not run_segments(stripped[0], substitutions):
                return scoped, issues
            continue
        if not run_segments(segments, substitutions):
            return scoped, issues

    if heredoc_end is not None:
        issues.append(f"heredoc {heredoc_end!r} is unterminated at {scope_label}")
    if pending_substitution is not None:
        issues.append(f"command substitution is unterminated at {scope_label}")
    if pending_function_brace:
        issues.append(f"function definition is missing its opening brace at {scope_label}")
    if if_depth > 0:
        issues.append(f"conditional block is unterminated at {scope_label}")
    if conditional_frames:
        issues.append(f"conditional block is unterminated at {scope_label}")
    if function_depth is not None:
        issues.append(f"function definition is unterminated at {scope_label}")
    if len(scopes) > 1:
        issues.append(f"subshell is unterminated at {scope_label}")
    return scoped, issues
