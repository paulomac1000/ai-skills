"""Safe Markdown, path, and instruction extraction for AGENTS.md validation."""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from pathlib import Path
from urllib.parse import unquote

from agents_md_types import (
    COMMAND_LINE,
    CONCEPT_PATTERNS,
    FENCE_OPENER,
    HEADING,
    INLINE_LINK,
    NEGATIVE_DIRECTIVE,
    PATH_CUE,
    PATH_NAMES,
    PATH_SUFFIXES,
    POSITIVE_DIRECTIVE,
    REFERENCE_DEFINITION,
    REFERENCE_USAGE,
    CommandRule,
    Directive,
    Finding,
    OwnershipRule,
    ParsedDocument,
    _is_external,
    _normalize_heading,
    _normalize_rule,
    _strip_destination,
)


def _strip_blockquote_prefix(line: str) -> str:
    value = line
    while True:
        match = re.match(r"^[ \t]{0,3}>[ \t]?", value)
        if match is None:
            return value
        value = value[match.end() :]


def _parse_visible_lines(text: str) -> tuple[list[tuple[int, str]], int | None]:
    visible: list[tuple[int, str]] = []
    fence_character: str | None = None
    minimum_length = 0
    fence_start: int | None = None
    for line_number, source_line in enumerate(text.splitlines(), start=1):
        line = _strip_blockquote_prefix(source_line)
        if fence_character is None:
            opener = FENCE_OPENER.fullmatch(line)
            if opener is not None:
                marker = opener.group("marker")
                info = opener.group("info")
                if marker[0] != "`" or "`" not in info:
                    fence_character = marker[0]
                    minimum_length = len(marker)
                    fence_start = line_number
                    continue
            visible.append((line_number, source_line))
            continue

        stripped = line.lstrip(" \t")
        closing = re.fullmatch(rf"{re.escape(fence_character)}{{{minimum_length},}}[ \t]*", stripped)
        if closing is not None:
            fence_character = None
            minimum_length = 0
            fence_start = None
    return visible, fence_start


def _iter_code_spans(line: str) -> Iterator[str]:
    index = 0
    while index < len(line):
        if line[index] != "`":
            index += 1
            continue
        end = index
        while end < len(line) and line[end] == "`":
            end += 1
        width = end - index
        closing = line.find("`" * width, end)
        if closing < 0:
            return
        yield line[end:closing].strip()
        index = closing + width


def _is_path_candidate(value: str, source_line: str) -> bool:
    if not value or any(character.isspace() for character in value):
        return False
    if value.startswith(("$", "-", "http://", "https://")):
        return False
    if any(character in value for character in "{}|*<>="):
        return False
    candidate = unquote(value.split("#", 1)[0]).removeprefix("./")
    path = Path(candidate)
    return (
        path.name in PATH_NAMES
        or path.suffix.casefold() in PATH_SUFFIXES
        or ("/" in candidate and PATH_CUE.search(source_line) is not None)
    )


def _iter_references(visible_lines: Sequence[tuple[int, str]]) -> Iterator[tuple[int, str]]:
    definitions: dict[str, str] = {}
    for _, line in visible_lines:
        match = REFERENCE_DEFINITION.fullmatch(line)
        if match is not None:
            definitions[match.group("label").casefold()] = _strip_destination(match.group("target"))

    for line_number, line in visible_lines:
        for match in INLINE_LINK.finditer(line):
            yield line_number, _strip_destination(match.group("target"))
        for match in REFERENCE_USAGE.finditer(line):
            key = (match.group("ref") or match.group("label")).casefold()
            target = definitions.get(key)
            if target:
                yield line_number, target
        for span in _iter_code_spans(line):
            if _is_path_candidate(span, line):
                yield line_number, span


def _has_concept(text: str, concept: str) -> bool:
    return any(pattern.search(text) for pattern in CONCEPT_PATTERNS[concept])


def _absolute_path_has_symlink(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _path_has_symlink(base: Path, candidate: Path) -> bool:
    try:
        relative = candidate.relative_to(base)
    except ValueError:
        return False
    current = base
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _trusted_root(repository_root: Path | None) -> tuple[Path | None, Finding | None]:
    lexical = (repository_root or Path.cwd()).absolute()
    if _absolute_path_has_symlink(lexical):
        return None, Finding(
            str(lexical),
            "error",
            "input.repository-root-symlink",
            1,
            "Repository root must not be a symlink.",
        )
    try:
        resolved = lexical.resolve(strict=True)
    except FileNotFoundError:
        return None, Finding(
            str(lexical),
            "error",
            "input.repository-root-missing",
            1,
            "Repository root does not exist.",
        )
    if not resolved.is_dir():
        return None, Finding(
            str(lexical),
            "error",
            "input.repository-root-not-directory",
            1,
            "Repository root is not a directory.",
        )
    return resolved, None


def _trusted_input(path: Path, root: Path) -> tuple[Path | None, Finding | None]:
    lexical = path if path.is_absolute() else root / path
    lexical = lexical.absolute()
    if not lexical.exists() and not lexical.is_symlink():
        return None, Finding(str(path), "error", "input.missing", 1, "Input file does not exist.")
    try:
        lexical.relative_to(root)
    except ValueError:
        return None, Finding(
            str(path),
            "error",
            "input.outside-repository",
            1,
            "Input file is outside the repository root.",
        )
    if _path_has_symlink(root, lexical):
        return None, Finding(str(path), "error", "input.symlink", 1, "Input path must not contain symlinks.")
    try:
        resolved = lexical.resolve(strict=True)
    except FileNotFoundError:
        return None, Finding(str(path), "error", "input.missing", 1, "Input file does not exist.")
    try:
        resolved.relative_to(root)
    except ValueError:
        return None, Finding(
            str(path),
            "error",
            "input.outside-repository",
            1,
            "Input file resolves outside the repository root.",
        )
    if not resolved.is_file():
        return None, Finding(str(path), "error", "input.not-file", 1, "Input is not a regular file.")
    return resolved, None


def _resolve_reference(path: Path, root: Path, target: str) -> tuple[Path | None, str | None]:
    clean = unquote(target.split("#", 1)[0]).strip()
    if not clean or clean.startswith("#") or _is_external(clean):
        return None, None
    candidate_path = Path(clean)
    lexical = candidate_path if candidate_path.is_absolute() else path.parent / candidate_path
    lexical = lexical.absolute()
    try:
        lexical.relative_to(root)
    except ValueError:
        return lexical, "outside"
    if _path_has_symlink(root, lexical):
        return lexical, "symlink"
    resolved = lexical.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError:
        return resolved, "outside"
    return resolved, None


def _is_negated_keyword_rule(line: str) -> bool:
    lowered = line.casefold()
    return any(
        phrase in lowered
        for phrase in (
            "do not use keyword",
            "must not use keyword",
            "never use keyword",
            "keyword matching is not",
            "keyword-based approval is not",
            "reject keyword",
            "forbid keyword",
            "not proof of human approval",
        )
    )


def _is_negated_ci_rule(line: str) -> bool:
    lowered = line.casefold()
    return any(
        phrase in lowered
        for phrase in (
            "not guaranteed",
            "does not guarantee",
            "cannot guarantee",
            "must not be described as a guarantee",
            "is not proof",
        )
    )


def _build_sections(visible_lines: Sequence[tuple[int, str]]) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for _, line in visible_lines:
        heading = HEADING.fullmatch(line)
        if heading is not None and len(heading.group("level")) == 2:
            current = _normalize_heading(heading.group("title"))
            sections.setdefault(current, [])
            continue
        if current is not None and HEADING.fullmatch(line) is None:
            sections[current].append(line)
    return {
        key: "\n".join(" ".join(part.split()) for part in value).strip()
        for key, value in sections.items()
    }


def _directive_category(line: str) -> str | None:
    lowered = line.casefold()
    if "generated" in lowered and any(token in lowered for token in ("edit", "modify", "change")):
        return "generated-edit"
    if "test" in lowered and any(
        token in lowered
        for token in ("skip", "disable", "weaken", "remove", "must run", "required", "pass")
    ):
        return "test-integrity"
    if any(token in lowered for token in ("secret", "private data", "sensitive data")) and any(
        token in lowered for token in ("commit", "track", "store", "expose", "write")
    ):
        return "protected-data"
    if "directly" in lowered and any(token in lowered for token in ("edit", "modify", "change")):
        return "direct-edit"
    return None


def _extract_directives(visible_lines: Sequence[tuple[int, str]]) -> tuple[Directive, ...]:
    directives: list[Directive] = []
    for line_number, line in visible_lines:
        category = _directive_category(line)
        if category is None:
            continue
        negative = NEGATIVE_DIRECTIVE.search(line) is not None
        positive = not negative and POSITIVE_DIRECTIVE.search(line) is not None
        if not negative and not positive:
            continue
        directives.append(
            Directive(
                category=category,
                polarity="deny" if negative else "allow",
                line=line_number,
                text=line.strip(),
                explicit_override=bool(re.search(r"\b(?:override|replaces? inherited|for this subtree)\b", line, re.I)),
            )
        )
    return tuple(directives)


def _instruction_context(line: str) -> str:
    without_code = re.sub(r"`[^`]*`", " ", line)
    return INLINE_LINK.sub(lambda match: match.group("label"), without_code)


def _extract_commands(visible_lines: Sequence[tuple[int, str]]) -> tuple[CommandRule, ...]:
    commands: list[CommandRule] = []
    current_heading = ""
    for line_number, line in visible_lines:
        heading = HEADING.fullmatch(line)
        if heading is not None:
            current_heading = heading.group("title")
            continue
        match = COMMAND_LINE.fullmatch(line)
        if match is None:
            continue
        label = re.sub(r"\b(?:local|subtree)\b", " ", match.group("label"), flags=re.I)
        commands.append(
            CommandRule(
                key=_normalize_rule(label),
                command=match.group("command").strip(),
                line=line_number,
                explicit_local=bool(
                    re.search(
                        r"\b(?:local|subtree|override)\b",
                        current_heading + " " + _instruction_context(line),
                        re.I,
                    )
                ),
            )
        )
    return tuple(commands)


def _normalized_ownership_target(path: Path, root: Path, target: str) -> str:
    resolved, issue = _resolve_reference(path, root, target)
    if resolved is None or issue is not None:
        return target
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return target


def _extract_ownership(
    visible_lines: Sequence[tuple[int, str]],
    path: Path,
    root: Path,
) -> tuple[OwnershipRule, ...]:
    ownership: list[OwnershipRule] = []
    current_heading = ""
    for line_number, line in visible_lines:
        heading = HEADING.fullmatch(line)
        if heading is not None:
            current_heading = heading.group("title")
            continue
        owns_contract = re.search(
            r"\b(?:sources? of truth|canonical owner|normative owner)\b",
            current_heading + " " + line,
            re.I,
        )
        if owns_contract is None:
            continue

        linked = [
            (match.group("label"), _strip_destination(match.group("target")))
            for match in INLINE_LINK.finditer(line)
        ]
        code_targets = [span for span in _iter_code_spans(line) if _is_path_candidate(span, line)]
        candidates = linked + [(line.split("`", 1)[0], target) for target in code_targets]
        if not candidates:
            continue
        label, target = candidates[0]
        ownership.append(
            OwnershipRule(
                key=_normalize_rule(label),
                target=_normalized_ownership_target(path, root, target),
                line=line_number,
                explicit_local=bool(
                    re.search(
                        r"\b(?:local|subtree|override)\b",
                        current_heading + " " + _instruction_context(line),
                        re.I,
                    )
                ),
            )
        )
    return tuple(ownership)


def _meaningful_lines(visible_lines: Sequence[tuple[int, str]]) -> frozenset[str]:
    ignored = re.compile(
        r"(?i)^(?:these instructions apply|repository-root instructions remain|more specific AGENTS\.md|#)"
    )
    values = {
        normalized
        for _, line in visible_lines
        if (normalized := _normalize_rule(line)) and not ignored.search(line.strip())
    }
    return frozenset(values)


def _parse_document(path: Path, root: Path, text: str) -> tuple[ParsedDocument, int | None]:
    visible_lines, unclosed_fence = _parse_visible_lines(text)
    return (
        ParsedDocument(
            path=path,
            relative_path=path.relative_to(root).as_posix(),
            text=text,
            visible_lines=tuple(visible_lines),
            sections=_build_sections(visible_lines),
            directives=_extract_directives(visible_lines),
            commands=_extract_commands(visible_lines),
            ownership=_extract_ownership(visible_lines, path, root),
            meaningful_lines=_meaningful_lines(visible_lines),
        ),
        unclosed_fence,
    )
