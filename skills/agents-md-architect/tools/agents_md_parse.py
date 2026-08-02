"""Safe Markdown, path, language, and instruction extraction for AGENTS.md validation."""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Iterator, Sequence
from pathlib import Path
from urllib.parse import unquote

from agents_md_types import (
    COMMAND_LINE,
    CONCEPT_PATTERNS_BY_LANGUAGE,
    CONTRACT_MARKER,
    FENCE_OPENER,
    HEADING,
    INLINE_LINK,
    LANGUAGE_NEGATIVE_DIRECTIVE,
    LANGUAGE_POSITIVE_DIRECTIVE,
    MAX_INSTRUCTION_FILE_BYTES,
    PATH_CUE,
    PATH_NAMES,
    PATH_SUFFIXES,
    REFERENCE_DEFINITION,
    REFERENCE_USAGE,
    CommandRule,
    Directive,
    LanguageName,
    OwnershipRule,
    ParsedDocument,
    ReadResult,
    _is_external,
    _normalize_heading,
    _normalize_rule,
    _strip_destination,
)


def _blockquote_depth_and_content(line: str) -> tuple[int, str]:
    """Return CommonMark blockquote depth and content after container prefixes."""
    depth = 0
    value = line
    while True:
        match = re.match(r"^[ \t]{0,3}>[ \t]?", value)
        if match is None:
            return depth, value
        depth += 1
        value = value[match.end() :]


def strip_blockquote_prefix(line: str) -> str:
    """Remove CommonMark blockquote prefixes for active-line parsing."""
    return _blockquote_depth_and_content(line)[1]


LIST_ITEM = re.compile(
    r"^(?P<indent> {0,3})(?P<marker>(?:[*+-]|\d{1,9}[.)]))"
    r"(?P<padding>(?: {1,4}|\t))(?P<content>.*)$"
)


def _list_container_content(
    line: str,
    active_indents: tuple[int, ...],
    *,
    allow_new_item: bool,
) -> tuple[str, tuple[int, ...]]:
    """Strip active list-item indentation before parsing Markdown fences."""
    stack = list(active_indents)
    if line.strip():
        while stack and not line.startswith(" " * stack[-1]):
            stack.pop()

    active_indent = stack[-1] if stack else 0
    content = line[active_indent:] if active_indent else line
    if not allow_new_item:
        return content, tuple(stack)

    match = LIST_ITEM.fullmatch(content)
    if match is None:
        return content, tuple(stack)

    padding = match.group("padding")
    padding_width = 4 if padding == "\t" else len(padding)
    content_indent = active_indent + len(match.group("indent")) + len(match.group("marker")) + padding_width
    while stack and stack[-1] >= content_indent:
        stack.pop()
    stack.append(content_indent)
    return match.group("content"), tuple(stack)


def _is_fence_closer(line: str, character: str, minimum_length: int) -> bool:
    match = re.fullmatch(r"(?P<indent>[ \t]{0,3})(?P<marker>`{3,}|~{3,})[ \t]*", line)
    if match is None:
        return False
    marker = match.group("marker")
    return marker[0] == character and len(marker) >= minimum_length


def parse_visible_lines(text: str) -> tuple[list[tuple[int, str]], int | None]:
    """Return active lines outside fenced blocks and a stable unclosed-fence line."""
    visible: list[tuple[int, str]] = []
    fence_character: str | None = None
    minimum_length = 0
    fence_start: int | None = None
    fence_container: tuple[int, tuple[int, ...]] | None = None
    abandoned_fence_start: int | None = None
    list_indents: tuple[int, ...] = ()
    current_quote_depth = 0

    for line_number, source_line in enumerate(text.splitlines(), start=1):
        quote_depth, container_line = _blockquote_depth_and_content(source_line)
        if quote_depth != current_quote_depth:
            list_indents = ()
            current_quote_depth = quote_depth

        line, candidate_indents = _list_container_content(
            container_line,
            list_indents,
            allow_new_item=fence_character is None,
        )
        current_container = (quote_depth, candidate_indents)
        if fence_character is not None and current_container != fence_container:
            abandoned_fence_start = abandoned_fence_start or fence_start
            fence_character = None
            minimum_length = 0
            fence_start = None
            fence_container = None
            line, candidate_indents = _list_container_content(
                container_line,
                candidate_indents,
                allow_new_item=True,
            )
            current_container = (quote_depth, candidate_indents)
        list_indents = candidate_indents

        if fence_character is None:
            opener = FENCE_OPENER.fullmatch(line)
            if opener is not None:
                marker = opener.group("marker")
                info = opener.group("info")
                if marker[0] != "`" or "`" not in info:
                    fence_character = marker[0]
                    minimum_length = len(marker)
                    fence_start = line_number
                    fence_container = current_container
                    continue
            visible.append((line_number, source_line))
            continue

        if _is_fence_closer(line, fence_character, minimum_length):
            fence_character = None
            minimum_length = 0
            fence_start = None
            fence_container = None

    return visible, fence_start or abandoned_fence_start


def read_utf8_bounded(path: Path, max_bytes: int = MAX_INSTRUCTION_FILE_BYTES) -> ReadResult:
    """Read at most max_bytes plus one from a regular file without following symlinks."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if nofollow:
        flags |= nofollow
    else:
        try:
            if path.is_symlink():
                return ReadResult(None, 0, "input.read-error", "Refusing to read a symlink.")
        except OSError as error:
            return ReadResult(None, 0, "input.read-error", f"Could not inspect input file: {error}")

    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        return ReadResult(None, 0, "input.read-error", f"Could not open input file: {error}")

    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            return ReadResult(None, 0, "input.read-error", "Input is not a regular file.")
        if metadata.st_size > max_bytes:
            return ReadResult(
                None,
                metadata.st_size,
                "input.too-large",
                (f"Input file is {metadata.st_size} bytes; maximum supported size is {max_bytes} bytes."),
            )
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            payload = stream.read(max_bytes + 1)
    except OSError as error:
        return ReadResult(None, 0, "input.read-error", f"Could not read input file: {error}")
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    if len(payload) > max_bytes:
        return ReadResult(
            None,
            len(payload),
            "input.too-large",
            f"Input file exceeds the maximum supported size of {max_bytes} bytes.",
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        return ReadResult(
            None,
            len(payload),
            "input.invalid-utf8",
            f"Input file is not valid UTF-8 at byte {error.start}.",
        )
    return ReadResult(text, len(payload), None, None)


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


def iter_references(visible_lines: Sequence[tuple[int, str]]) -> Iterator[tuple[int, str]]:
    """Yield active Markdown and code-span repository references."""
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


def document_has_concept(document: ParsedDocument, concept: str, language: LanguageName) -> bool | None:
    """Return True/False for supported languages and None when semantics are unknown."""
    if concept in document.contracts:
        return True
    patterns = CONCEPT_PATTERNS_BY_LANGUAGE[language]
    if patterns is None:
        return None
    visible_text = "\n".join(line for _, line in document.visible_lines)
    return any(pattern.search(visible_text) for pattern in patterns[concept])


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


def trusted_root(repository_root: Path | None) -> tuple[Path | None, str | None, str | None]:
    try:
        lexical = (repository_root or Path.cwd()).absolute()
        if _absolute_path_has_symlink(lexical):
            return None, "input.repository-root-symlink", "Repository root must not contain symlinks."
        resolved = lexical.resolve(strict=True)
        if not resolved.is_dir():
            return None, "input.repository-root-not-directory", "Repository root is not a directory."
    except FileNotFoundError:
        return None, "input.repository-root-missing", "Repository root does not exist."
    except (OSError, RuntimeError) as error:
        return None, "input.repository-root-unreadable", f"Could not inspect repository root: {error}"
    return resolved, None, None


def trusted_input(path: Path, root: Path) -> tuple[Path | None, str | None, str | None]:
    try:
        lexical = path if path.is_absolute() else root / path
        lexical = lexical.absolute()
        if not lexical.exists() and not lexical.is_symlink():
            return None, "input.missing", "Input file does not exist."
        try:
            lexical.relative_to(root)
        except ValueError:
            return None, "input.outside-repository", "Input file is outside the repository root."
        if _path_has_symlink(root, lexical):
            return None, "input.symlink", "Input path must not contain symlinks."
        resolved = lexical.resolve(strict=True)
        try:
            resolved.relative_to(root)
        except ValueError:
            return None, "input.outside-repository", "Input file resolves outside the repository root."
        if not resolved.is_file():
            return None, "input.not-file", "Input is not a regular file."
    except FileNotFoundError:
        return None, "input.missing", "Input file does not exist."
    except (OSError, RuntimeError) as error:
        return None, "input.unreadable", f"Could not inspect input file: {error}"
    return resolved, None, None


def resolve_reference(path: Path, root: Path, target: str) -> tuple[Path | None, str | None]:
    clean = unquote(target.split("#", 1)[0]).strip()
    if not clean or clean.startswith("#") or _is_external(clean):
        return None, None
    candidate_path = Path(clean)
    lexical = candidate_path if candidate_path.is_absolute() else path.parent / candidate_path
    lexical = lexical.absolute()
    try:
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
    except (OSError, RuntimeError):
        return lexical, "unreadable"
    return resolved, None


def is_negated_keyword_rule(line: str) -> bool:
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
            "nie używaj słów kluczowych",
            "dopasowanie słów kluczowych nie jest",
            "nie jest dowodem zatwierdzenia",
        )
    )


def is_negated_ci_rule(line: str) -> bool:
    lowered = line.casefold()
    return any(
        phrase in lowered
        for phrase in (
            "not guaranteed",
            "does not guarantee",
            "cannot guarantee",
            "must not be described as a guarantee",
            "is not proof",
            "nie gwarantuje",
            "nie jest gwarancją",
            "nie stanowi dowodu",
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
    return {key: "\n".join(" ".join(part.split()) for part in value).strip() for key, value in sections.items()}


def _extract_contracts(visible_lines: Sequence[tuple[int, str]]) -> frozenset[str]:
    return frozenset(
        match.group("name").casefold()
        for _, line in visible_lines
        if (match := CONTRACT_MARKER.fullmatch(line.strip())) is not None
    )


def _directive_category(line: str, language: LanguageName) -> str | None:
    lowered = line.casefold()
    if language == "pl":
        if re.search(r"\bwygenerowan\w*\b", lowered) and re.search(r"\b(?:edyt\w*|modyfik\w*|zmien\w*)\b", lowered):
            return "generated-edit"
        if re.search(r"\btest(?:y|ów|om|ami|ach|ować|owania|owanie|owy|owe|owych)?\b", lowered) and re.search(
            r"\b(?:pomij\w*|wyłącz\w*|osłab\w*|usuń\w*|uruch\w*|wymag\w*|przej\w*)\b", lowered
        ):
            return "test-integrity"
        if re.search(
            r"\b(?:sekret(?:y|ów|om|ami|ach)?|tajemnic(?:a|e|y|ę|ą|om|ami|ach)|dane (?:prywatne|wrażliwe|osobowe))\b",
            lowered,
        ) and re.search(r"\b(?:commit\w*|śled\w*|przechow\w*|ujawn\w*|zapis\w*)\b", lowered):
            return "protected-data"
        if re.search(r"\bbezpośrednio\b", lowered) and re.search(r"\b(?:edyt\w*|modyfik\w*|zmien\w*)\b", lowered):
            return "direct-edit"
        return None
    if language == "other":
        return None
    if re.search(r"\bgenerated\b", lowered) and re.search(
        r"\b(?:edit(?:ed|ing|s)?|modif(?:y|ied|ies|ying)|chang(?:e|ed|es|ing))\b", lowered
    ):
        return "generated-edit"
    if re.search(r"\btests?\b", lowered) and re.search(
        r"\b(?:skip|disable|weaken|remove|required|pass)\b|\bmust\s+run\b", lowered
    ):
        return "test-integrity"
    if re.search(r"\b(?:secrets?|private data|sensitive data)\b", lowered) and re.search(
        r"\b(?:commit|track|store|expose|write)\b", lowered
    ):
        return "protected-data"
    if re.search(r"\bdirectly\b", lowered) and re.search(
        r"\b(?:edit(?:ed|ing|s)?|modif(?:y|ied|ies|ying)|chang(?:e|ed|es|ing))\b", lowered
    ):
        return "direct-edit"
    return None


def _extract_directives(visible_lines: Sequence[tuple[int, str]], language: LanguageName) -> tuple[Directive, ...]:
    directives: list[Directive] = []
    negative_pattern = LANGUAGE_NEGATIVE_DIRECTIVE[language]
    positive_pattern = LANGUAGE_POSITIVE_DIRECTIVE[language]
    if negative_pattern is None or positive_pattern is None:
        return ()
    for line_number, line in visible_lines:
        category = _directive_category(line, language)
        if category is None:
            continue
        negative = negative_pattern.search(line) is not None
        positive = not negative and positive_pattern.search(line) is not None
        if not negative and not positive:
            continue
        directives.append(
            Directive(
                category=category,
                polarity="deny" if negative else "allow",
                line=line_number,
                text=line.strip(),
                explicit_override=bool(
                    re.search(
                        (
                            r"\b(?:override|replaces? inherited|for this subtree|wyjątek|nadpisuje|"
                            r"zastępuje odziedziczone|dla tego poddrzewa)\b"
                        ),
                        line,
                        re.I,
                    )
                ),
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
        label = re.sub(
            r"\b(?:local|subtree|lokaln\w*|poddrzew\w*)\b",
            " ",
            match.group("label"),
            flags=re.I,
        )
        commands.append(
            CommandRule(
                key=_normalize_rule(label),
                command=match.group("command").strip(),
                line=line_number,
                explicit_local=bool(
                    re.search(
                        r"\b(?:local|subtree|override|lokaln\w*|poddrzew\w*|wyjątek)\b",
                        current_heading + " " + _instruction_context(line),
                        re.I,
                    )
                ),
            )
        )
    return tuple(commands)


def _normalized_ownership_target(path: Path, root: Path, target: str) -> str:
    resolved, issue = resolve_reference(path, root, target)
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
            (
                r"\b(?:sources? of truth|canonical owner|normative owner|źródła? prawdy|"
                r"kanoniczny właściciel|właściciel normatywny)\b"
            ),
            current_heading + " " + line,
            re.I,
        )
        if owns_contract is None:
            continue

        linked = [
            (match.group("label"), _strip_destination(match.group("target"))) for match in INLINE_LINK.finditer(line)
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
                        r"\b(?:local|subtree|override|lokaln\w*|poddrzew\w*|wyjątek)\b",
                        current_heading + " " + _instruction_context(line),
                        re.I,
                    )
                ),
            )
        )
    return tuple(ownership)


def _meaningful_lines(visible_lines: Sequence[tuple[int, str]]) -> frozenset[str]:
    ignored = re.compile(
        r"(?i)^(?:these instructions apply|repository-root instructions remain|more specific AGENTS\.md|"
        r"te instrukcje dotyczą|instrukcje główne pozostają|#|<!--\s*agents-md:)"
    )
    values = {
        normalized
        for _, line in visible_lines
        if (normalized := _normalize_rule(line)) and not ignored.search(line.strip())
    }
    return frozenset(values)


def parse_document(
    path: Path,
    root: Path,
    text: str,
    language: LanguageName = "en",
) -> tuple[ParsedDocument, int | None]:
    """Parse one already-confined instruction file using the shared Markdown contract."""
    visible_lines, unclosed_fence = parse_visible_lines(text)
    return (
        ParsedDocument(
            path=path,
            relative_path=path.relative_to(root).as_posix(),
            text=text,
            visible_lines=tuple(visible_lines),
            sections=_build_sections(visible_lines),
            contracts=_extract_contracts(visible_lines),
            directives=_extract_directives(visible_lines, language),
            commands=_extract_commands(visible_lines),
            ownership=_extract_ownership(visible_lines, path, root),
            meaningful_lines=_meaningful_lines(visible_lines),
        ),
        unclosed_fence,
    )
