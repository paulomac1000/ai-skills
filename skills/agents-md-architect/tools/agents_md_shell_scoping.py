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
    _has_structural_brace_group,
    _segment_scope_kind,
    _split_ordered,
    _split_structural_tokens,
    _static_cd_target,
    _structural_brace_delta,
    _structural_close_index,
)

_FUNCTION_DEF = re.compile(r"^\s*(?:function\s+([A-Za-z_][A-Za-z0-9_]*)|([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*\))\s*\{?")
# PRRT_kwDOSYvkl86189AB (round 17): the quoted delimiter may contain dashes
# and other word characters; the unquoted stays an identifier-shaped word.
# Expansion ($), quotes and backslashes inside the delimiter are outside the
# bounded grammar and fail closed at the unrecognized-opener check.
_HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)\s*(['\"]?)((?(2)[^\s'\"$]+|[A-Za-z_][A-Za-z0-9_-]*))\2")


def _heredoc_terminates(raw_line: str, delimiter: str, dashed: bool) -> bool:
    """PRRT_kwDOSYvkl8617Zd7 (round 16) — bash heredoc terminator rules:
    ``<<EOF`` accepts ONLY the delimiter alone on a line; ``<<-EOF`` may
    have LEADING TABS stripped (never spaces). A body line that merely
    strips to the delimiter is data, never a terminator."""
    if dashed:
        return raw_line.lstrip("\t") == delimiter
    return raw_line == delimiter


_KEYWORDS = {"then", "else", "elif", "fi", "done", "do", "{", "!", "if"}
_TRANSITION_COMMANDS = {"cd", "pushd", "popd"}
_LOOP_HEADS = {"while", "for", "until"}
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
    conditional_frames: list[bool] = []  # the single conditional-depth truth (v9hd)
    last_was_transition = False
    heredoc_end: str | None = None
    heredoc_dashed = False
    defined_functions: set[str] = set()
    function_depth: int | None = None
    pending_function_brace = False

    def pop_frames(count: int) -> None:
        for _ in range(min(count, len(scopes) - 1)):
            scopes.pop()
            pushd_stacks.pop()

    def fail(message: str) -> bool:
        issues.append(message)
        return False

    def _analyze_segment_markers(segment_text: str, scope: str) -> bool:
        """Analyze every indexed substitution marker of ONE segment exactly
        once, at the scope that actually executes it (17Zp). Shared by the
        ordinary path and the assignment-prefixed path."""
        for marker_match in re.finditer(r"SUBST\$(\d+)", segment_text):
            marker_index = int(marker_match.group(1))
            if marker_index >= len(substitutions):
                continue
            substitution = substitutions[marker_index]
            if not substitution.strip():
                continue
            if _depth + 1 > _MAX_SUBSTITUTION_DEPTH or len(substitution) > _MAX_SUBSTITUTION_CHARS:
                return fail(
                    f"command substitution exceeds the bounded static analysis envelope "
                    f"at {scope_label}: {substitution!r}"
                )
            nested_scoped, nested_issues = shell_invocations_with_scope(
                substitution, scope, f"{scope_label} substitution", _depth=_depth + 1
            )
            scoped.extend(nested_scoped)
            issues.extend(nested_issues)
        return True

    def run_engine(segments: list[tuple[str | None, str]], substitutions: list[str]) -> bool:
        """The single ordered scope engine shared by every segment source."""
        nonlocal last_was_transition, function_depth, pending_function_brace, heredoc_end
        nonlocal heredoc_dashed  # PRRT_kwDOSYvkl86172Zp (round 17)
        for operator, segment in segments:
            if (
                segment.startswith("{")
                and _structural_close_index(segment) == len(segment)
                and _has_structural_brace_group(segment)
            ):  # 9nj5/9nj_: an outer brace group wrapping the whole segment —
                # strip the group braces and re-dispatch the inner content through
                # the SAME ordered engine: brace-aware splitting keeps definitions
                # whole (bodies inert), quoted arguments never split as separators,
                # and the suffix is attributed at the correct scope.
                wrapped = segment[1:-1].strip()
                if wrapped:
                    if not run_segments(_split_ordered(wrapped), substitutions):
                        return False
                continue
            definition_head = _FUNCTION_DEF.match(segment)
            if definition_head is not None:  # 2BaK: raw-segment match — parens stay intact
                defined_functions.add(definition_head.group(1) or definition_head.group(2))
                opener = _HEREDOC.search(segment)
                if opener is not None:  # 66eF: declaration-line heredoc — contents are data
                    heredoc_end = opener.group(3)
                    heredoc_dashed = opener.group(1) == "-"
                    function_depth = max(1, _structural_brace_delta(segment[: opener.start()]))
                    return True
                close = _structural_close_index(segment)
                if close is not None:  # inline closed: inert body skipped, suffix executed
                    suffix_segments = _split_ordered(segment[close:].strip())
                    if suffix_segments and not run_segments(suffix_segments, substitutions):
                        return False
                    continue
                delta = _structural_brace_delta(segment)
                if delta > 0:  # multiline body opened mid-stream
                    function_depth = delta
                    return True  # subsequent lines route through the body branch
                if delta < 0:
                    return fail(f"function definition brace balance is unsupported at {scope_label}: {segment!r}")
                pending_function_brace = True  # opening brace expected on a following line
                return True
            opens, closes, inner = _segment_scope_kind(segment)
            for _ in range(opens):
                scopes.append(scopes[-1])
                pushd_stacks.append(list(pushd_stacks[-1]))
            effective = scopes[-1]
            conditional_context = bool(conditional_frames)
            # PRRT_kwDOSYvkl86172Zp (round 16) — substitution analysis is
            # DEFERRED past the structural branches (definitions, protected
            # brace groups): those paths recurse with the FULL substitution
            # list, so each indexed marker is analyzed EXACTLY ONCE, in the
            # scope that actually executes its segment. The ordinary
            # invocation path below owns the analysis.
            definition_head = _FUNCTION_DEF.match(inner)
            if definition_head is not None:  # 2BaK: definitions are recognized anywhere in the stream
                defined_functions.add(definition_head.group(1) or definition_head.group(2))
                opener = _HEREDOC.search(inner)
                if opener is not None:  # 66eF: declaration-line heredoc — contents are data
                    # 17Zd7 — the dash mode rides with the delimiter: the
                    # terminator consumes it (tabs-only stripping for <<-).
                    # 17Zd7 — heredoc_dashed is consumed by the terminator
                    # check at the top of the body loop (tabs-only stripping
                    # for <<-); the store precedes the loop re-entry, which
                    # ruff's linear flow does not model.
                    heredoc_end, heredoc_dashed = (  # noqa: F841
                        opener.group(3),
                        opener.group(1) == "-",
                    )
                    function_depth = max(1, _structural_brace_delta(inner[: opener.start()]))
                    return True
                close = _structural_close_index(inner)
                delta = _structural_brace_delta(inner)
                if close is not None:  # inline closed: inert body skipped, suffix executed
                    suffix_inner = inner[close:].strip()
                    if suffix_inner and not run_engine(_split_ordered(suffix_inner), substitutions):
                        return False
                    pop_frames(min(closes, len(scopes) - 1))
                    continue
                if delta > 0:  # multiline body opened mid-stream
                    function_depth = delta
                    return True  # subsequent lines route through the body branch
                if delta < 0:
                    return fail(f"function definition brace balance is unsupported at {scope_label}: {segment!r}")
                pending_function_brace = True  # opening brace expected on a following line
                return True
            try:
                tokens = shlex.split(inner) if inner.strip() else []
            except ValueError:
                return fail(f"workflow segment is not statically parseable at {scope_label}: {segment!r}")
            command = inner  # original slice preserves GH expressions and argument boundaries (ccTD)
            while tokens and tokens[0] in _KEYWORDS:
                head = tokens[0]
                tokens = tokens[1:]
                if head == "if":  # ordered frames: opening pushes the conditional context (F1/F3)
                    conditional_frames.append(True)
                elif head == "fi":  # closing restores the parent frame context (F3)
                    if conditional_frames:
                        conditional_frames.pop()
                command = shlex.join(tokens) if tokens else ""
            if not tokens:
                pop_frames(min(closes, len(scopes) - 1))
                continue
            transition_tokens = tokens
            while transition_tokens and re.match(
                r"^[A-Za-z_][A-Za-z0-9_]*=", transition_tokens[0]
            ):  # 7JU6: assignment-prefixed commands — strip for builtin identification
                name, _, value = transition_tokens[0].partition("=")
                if name == "CDPATH" and value:  # CDPATH alters cd resolution — fail closed
                    return fail(f"CDPATH-qualified directory transition is unsupported at {scope_label}: {segment!r}")
                transition_tokens = transition_tokens[1:]
            if not transition_tokens:
                # 17Zp — an assignment-only statement still EXECUTES its
                # value's substitutions at the current scope: analyze the
                # segment's markers before continuing.
                if not _analyze_segment_markers(segment, effective):
                    return False
                pop_frames(min(closes, len(scopes) - 1))
                continue
            builtin_wrapped = transition_tokens[0] in {"command", "builtin"}
            if builtin_wrapped:  # 2BaN: literal wrapper around a directory builtin
                if len(transition_tokens) > 1 and transition_tokens[1].startswith("-") and transition_tokens[1] != "-v":
                    return fail(f"builtin wrapper flag is not statically attributable at {scope_label}: {segment!r}")
                if len(transition_tokens) > 1:
                    transition_tokens = transition_tokens[1:]
                    command = shlex.join(transition_tokens) if transition_tokens else ""
            if transition_tokens[0] in defined_functions and not builtin_wrapped:
                # PRRT_kwDOSYvkl8617Zd0 (round 16) — a DEFINED function shadows
                # the directory builtin: bash would invoke the function, whose
                # scope effects are not statically resolvable. Explicit
                # command/builtin wrappers bypass the function lookup and keep
                # the real transition. The check precedes every transition
                # application, so the shadowed builtin can never move the
                # ambient scope.
                return fail(
                    f"shell function {transition_tokens[0]!r} overrides the directory builtin; "
                    f"its scope effects are not statically resolvable at {scope_label}"
                )
            if any(token in {";", "}"} for token in transition_tokens) or _has_structural_brace_group(inner):
                # 2BaK: protected brace group — ordered token groups. The
                # quote-aware structural scanner keeps quoted argument data
                # whole (9nj_: a quoted ';' is an echo argument, never a
                # separator) and splits structural braces/semicolons.
                tokens = _split_structural_tokens(inner)
                group_segments: list[tuple[str | None, str]] = []
                group_tokens: list[str] = []
                group_operator = operator
                for token in tokens:
                    if token and all(ch in ";{}" for ch in token):
                        # PRRT_kwDOSYvkl86189AG (round 17) — a punctuation RUN
                        # token (`};`) explodes in order: each brace adjusts
                        # nothing here (the flattened ordered model) and each
                        # separator flushes the current word group, so the
                        # glued close+separator is honored with the order
                        # preserved.
                        for ch in token:
                            if ch in {"{", "}"}:
                                continue
                            if group_tokens:
                                group_segments.append((group_operator, shlex.join(group_tokens)))
                                group_tokens = []
                            group_operator = ";"
                        continue
                    if token in {"{", "}"}:
                        continue  # structural brace of the protected group, not command data
                    if token in {"&&", "||"}:
                        # PRRT_kwDOSYvkl8617JVB (round 16) — boolean operators
                        # stay OPERATORS: the ordered engine applies its
                        # transition/conditional fail-closed rules per segment
                        # (a directory transition after && or || inside a
                        # brace group is typed-refused, never silently
                        # dropped or misattributed).
                        if group_tokens:
                            group_segments.append((group_operator, shlex.join(group_tokens)))
                            group_tokens = []
                        group_operator = token
                        continue
                    if token == ";":
                        if group_tokens:
                            group_segments.append((group_operator, shlex.join(group_tokens)))
                            group_tokens = []
                        group_operator = ";"
                        continue
                    if "&&" in token or "||" in token:
                        return fail(
                            f"boolean operator is not token-separated inside a brace group "
                            f"at {scope_label}: {segment!r}"
                        )
                    group_tokens.append(token)
                if group_tokens:
                    group_segments.append((group_operator, shlex.join(group_tokens)))
                if (
                    len(group_segments) == 1 and group_segments[0][1] == inner.strip()
                ):  # 5omx: no measurable parsing progress — unsupported quoted structure
                    return fail(f"brace group is not statically attributable at {scope_label}: {segment!r}")
                if group_segments and not run_engine(group_segments, substitutions):
                    return False
                pop_frames(min(closes, len(scopes) - 1))
                continue
            if transition_tokens[0] in {"case", "esac"}:  # 66eP: case arms are outside the bounded grammar
                return fail(f"case construct is not statically attributable at {scope_label}: {segment!r}")
            if transition_tokens[0] in _LOOP_HEADS:  # loop headers fail closed wherever they occur (v9hO)
                return fail(
                    f"unsupported loop control flow is not statically attributable at {scope_label}: {segment!r}"
                )
            if operator == "||" and last_was_transition:
                return fail(
                    f"conditional reachability after a directory transition is unresolved at {scope_label}: {segment!r}"
                )
            if transition_tokens[0] in _TRANSITION_COMMANDS and (operator not in (None, ";") or conditional_context):
                return fail(
                    f"conditional control flow over a directory transition is unsupported at {scope_label}: {segment!r}"
                )
            if transition_tokens[0] in _TRANSITION_COMMANDS:
                if transition_tokens[0] == "popd":
                    target = pushd_stacks[-1].pop() if pushd_stacks[-1] and len(transition_tokens) == 1 else None
                else:
                    target = _static_cd_target(transition_tokens[1:], effective)
                if target is None:
                    return fail(f"workflow directory transition is unsupported at {scope_label}: {segment!r}")
                if transition_tokens[0] == "pushd":
                    pushd_stacks[-1].append(effective)
                scopes[-1] = target
                pop_frames(min(closes, len(scopes) - 1))
                last_was_transition = True
                continue
            if transition_tokens[0] in defined_functions:
                return fail(
                    f"shell function {tokens[0]!r} is invoked and its scope effects "
                    f"are not statically resolvable at {scope_label}"
                )
            if not _analyze_segment_markers(segment, effective):
                return False
            normalized = _normalize_invocation(command)
            if normalized is not None:
                scoped.append((normalized, effective))
            last_was_transition = False
            pop_frames(min(closes, len(scopes) - 1))
        return True

    def run_segments(segments: list[tuple[str | None, str]], substitutions: list[str]) -> bool:
        return run_engine(segments, substitutions)

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
        nonlocal heredoc_end, heredoc_dashed
        for position, (_operator, segment) in enumerate(segments):
            opener = _HEREDOC.search(segment)
            if opener is None:
                continue
            heredoc_end = opener.group(3)
            heredoc_dashed = opener.group(1) == "-"
            stripped = [
                (operator, _HEREDOC.sub("", segment, count=1) if index == position else segment)
                for index, (operator, segment) in enumerate(segments)
            ]
            return stripped, position
        return None

    pending_substitution: list[str] | None = None
    for raw_line in _logical_shell_lines(run):
        if heredoc_end is not None:  # heredoc bodies are data: consumed before comment stripping
            if _heredoc_terminates(raw_line, heredoc_end, heredoc_dashed):
                heredoc_end = None
                heredoc_dashed = False
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
        # the same lookbehind/lookahead guards as _HEREDOC: a here-string
        # (<<<) is never mistaken for an unrecognized heredoc opener (round 17)
        if heredoc_end is None and re.search(r"(?<!<)<<(?!<)", line) and _HEREDOC.search(line) is None:
            # PRRT_kwDOSYvkl86189AB — an unrecognized heredoc opener form
            # (e.g. an expansion-bearing delimiter) is outside the bounded
            # grammar: typed fail-closed instead of executing its body.
            fail(f"heredoc delimiter is not statically recognizable at {scope_label}: {line!r}")
            return scoped, issues
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
                heredoc_end = opener.group(3)
                heredoc_dashed = opener.group(1) == "-"  # definition's opener command is never attributed (qpx3)
                continue
            function_depth += _structural_brace_delta(line)  # quoted braces are data (5839793113)
            if function_depth <= 0:
                function_depth = None
                # 5om4: the closed body's substitution markers are dropped with the
                # inert body (never attributed); the suffix consumes its own markers
                # by ABSOLUTE index, so no positional accounting is needed.
                if not definition_suffix(line, substitutions):
                    return scoped, issues
            continue
        definition = _FUNCTION_DEF.match(line)
        if definition is not None:
            defined_functions.add(definition.group(1) or definition.group(2))
            delta = _structural_brace_delta(line)
            opener = _HEREDOC.search(line)
            if opener is not None:  # 66eF: declaration-line heredoc — contents are data
                heredoc_end = opener.group(3)
                heredoc_dashed = opener.group(1) == "-"
                function_depth = max(1, delta)
                continue
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
        if conditional_frames:  # conditional context active: body routing (v9hd)
            if line == "fi" or line.startswith("fi;") or line.startswith("fi "):
                conditional_frames.pop()
                suffix = line[2:].strip()
                if suffix.startswith(";"):
                    suffix = suffix[1:].strip()
                # qpx-: the suffix runs with the INHERITED frame context — the engine itself
                # keeps a still-open outer conditional fail-closed and applies top-level ones.
                if suffix and not run_line(suffix, substitutions):
                    return scoped, issues
                continue
            opener = _HEREDOC.search(line)
            if opener is not None:  # a body heredoc isolates its data from scope parsing
                heredoc_end = opener.group(3)
                heredoc_dashed = opener.group(1) == "-"
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
    if conditional_frames:
        issues.append(f"conditional block is unterminated at {scope_label}")
    if function_depth is not None:
        issues.append(f"function definition is unterminated at {scope_label}")
    if len(scopes) > 1:
        issues.append(f"subshell is unterminated at {scope_label}")
    return scoped, issues
