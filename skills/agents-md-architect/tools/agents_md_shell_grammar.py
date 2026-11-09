"""Bounded shell-grammar primitives for the static scope attribution model."""

from __future__ import annotations

import posixpath

_SUPPORTED_CD_FLAGS = {"-P", "-L"}


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
