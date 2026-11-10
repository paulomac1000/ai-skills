"""Bounded shell-grammar primitives for the static scope attribution model."""

from __future__ import annotations

import posixpath

_SUPPORTED_CD_FLAGS = {"-P", "-L"}


def _split_ordered(command: str) -> list[tuple[str | None, str]]:
    """Split at unquoted ``;``/``&&``/``||`` preserving order and the preceding operator.

    Brace-aware (review 2BaK): separators inside structural ``{ ... }`` — e.g. the
    body of a function definition — never split, so definitions stay whole for the
    ordered engine. ``${{ ... }}`` runner expressions are TRANSPARENT: the runner
    expands them before bash runs, their braces are not function bodies, and their
    internal separators have always split the stream (the workflow reference
    extractor depends on that segment shape). Quote/escape state is tracked
    throughout.
    """
    ordered: list[tuple[str | None, str]] = []
    operator: str | None = None
    current: list[str] = []
    quote: str | None = None
    escaped = False
    brace_depth = 0
    expression = False
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
        if not expression and command.startswith("${{", index):
            # Round 14: the expression delimiters are recognized so their
            # braces never count as function-body braces, but the span stays
            # TRANSPARENT to separator splitting (the historical segment
            # shape the workflow reference extractor depends on).
            expression = True
            current.append("${{")
            index += 3
            continue
        if expression and command.startswith("}}", index):
            expression = False
            current.append("}}")
            index += 2
            continue
        if character == "{":
            brace_depth += 1
            current.append(character)
            index += 1
            continue
        if character == "}":
            brace_depth -= 1
            current.append(character)
            index += 1
            continue
        separator = ""
        if brace_depth == 0:
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


def _structural_brace_delta(line: str) -> int:
    """Count structural braces outside quotes, escapes and line continuations.

    Quoted or escaped braces are shell data (review C / 5839793113) and never
    contribute to function-body depth. The caller strips comments beforehand.
    """
    quote: str | None = None
    escaped = False
    delta = 0
    for character in line:
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote != "'":
            escaped = True
            continue
        if quote is not None:
            if character == quote:
                quote = None
            continue
        if character in "'\"":
            quote = character
            continue
        if character == "{":
            delta += 1
        elif character == "}":
            delta -= 1
    return delta


def _structural_close_index(line: str) -> int | None:
    """Index just past the brace that closes the line's structural brace depth.

    Lexically quote/escape-aware (review F2 / 5840414479): a closing brace
    inside quotes — e.g. the '{}' in `python check.py --format '{}'` — is data
    and never terminates a function definition's suffix scan.
    """
    quote: str | None = None
    escaped = False
    depth = 0
    for index, character in enumerate(line):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote != "'":
            escaped = True
            continue
        if quote is not None:
            if character == quote:
                quote = None
            continue
        if character in "'\"":
            quote = character
            continue
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth <= 0:
                return index + 1
    return None
