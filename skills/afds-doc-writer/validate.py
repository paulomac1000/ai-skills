#!/usr/bin/env python3
"""Validate Markdown documents under explicit AFDS governance profiles."""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import stat
import sys
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote

import yaml

FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
FENCE_OPENER = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})(?P<info>[^\r\n]*)$")
REFERENCE_DEFINITION = re.compile(
    r"^(?P<indent>[ ]{0,3})\[(?P<label>[^\]\n]+)\]:[ \t]*(?P<raw>[^\r\n]+)$",
    re.M,
)
REFERENCE_LINK = re.compile(r"(?<!\!)\[(?P<label>(?:\\.|[^\]\n])+)\]\[(?P<reference>[^\]\n]*)\]")
BRACKETED_LABEL = re.compile(r"\[(?P<label>(?:\\.|[^\]\n])+)\]")
DOC_ID = re.compile(r"^(workflow|reference|system|guide|decision|contract)\.[a-z0-9][a-z0-9.-]*$")
COMMON_REQUIRED = {"description", "doc_id", "type", "status", "rigor", "owners"}
VALID_TYPES = {"workflow", "reference", "system", "guide", "decision", "contract"}
VALID_STATUS = {"draft", "active", "evolving", "deprecated", "archived"}
VALID_RIGOR = {"informative", "operational", "normative"}
AUTOMATION_FIELDS = {
    "last_verified",
    "fitness_score",
    "semantic_hash",
    "dependency_versions",
    "backlinks",
}
MAX_DOCUMENT_BYTES = 1024 * 1024
DEFAULT_PROFILES: dict[str, dict[str, bool]] = {
    "governed": {
        "require_frontmatter": True,
        "check_structure": True,
        "check_links": True,
        "check_anchors": True,
        "require_verification_by_rigor": True,
    },
    "human-facing": {
        "require_frontmatter": False,
        "check_structure": True,
        "check_links": True,
        "check_anchors": True,
        "require_verification_by_rigor": False,
    },
}


@dataclass(frozen=True)
class Finding:
    """One validation error associated with a path."""

    path: Path
    message: str


@dataclass(frozen=True)
class Governance:
    """Validated document-profile assignments loaded from one repository file."""

    profiles: Mapping[str, Mapping[str, bool]]
    assignments: tuple[tuple[str, str], ...]
    default_profile: str


def collect_files(inputs: Iterable[Path]) -> tuple[list[Path], list[Finding]]:
    """Resolve explicit Markdown inputs and reject missing or unsupported paths."""
    files: set[Path] = set()
    findings: list[Finding] = []
    for item in inputs:
        if not os.path.lexists(item):
            findings.append(Finding(item, "input does not exist"))
        elif item.is_file() or item.is_symlink():
            if item.suffix.lower() != ".md":
                findings.append(Finding(item, "explicit input is not a Markdown file"))
            else:
                files.add(item)
        elif item.is_dir():
            files.update(
                path
                for path in item.rglob("*.md")
                if not {".git", ".venv", "__pycache__"}.intersection(path.parts)
            )
        else:
            findings.append(Finding(item, "unsupported input type"))
    if not files and not findings:
        findings.append(Finding(Path("."), "no Markdown documents selected"))
    return sorted(files), findings


def _blank_line(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n") or line.endswith("\r"):
        return line[-1]
    return ""


def _indentation_columns(prefix: str) -> int:
    columns = 0
    for character in prefix:
        columns += 4 - (columns % 4) if character == "\t" else 1
    return columns


def strip_fenced_blocks(text: str) -> str:
    """Blank CommonMark fenced blocks while preserving source line boundaries."""
    output: list[str] = []
    fence_character: str | None = None
    minimum_length = 0
    for line in text.splitlines(keepends=True):
        candidate = line.rstrip("\r\n")
        if fence_character is None:
            opener = FENCE_OPENER.match(candidate)
            if opener and _indentation_columns(opener.group("indent")) <= 3:
                marker = opener.group("fence")
                info = opener.group("info")
                if marker[0] != "`" or "`" not in info:
                    fence_character = marker[0]
                    minimum_length = len(marker)
                    output.append(_blank_line(line))
                    continue
            output.append(line)
            continue

        stripped = candidate.lstrip(" \t")
        indentation_prefix = candidate[: len(candidate) - len(stripped)]
        closing = re.fullmatch(rf"{re.escape(fence_character)}{{{minimum_length},}}[ \t]*", stripped)
        output.append(_blank_line(line))
        if closing and _indentation_columns(indentation_prefix) <= 3:
            fence_character = None
            minimum_length = 0
    return "".join(output)


def _extract_destination(raw: str) -> str | None:
    value = raw.strip()
    if not value:
        return None
    if value.startswith("<"):
        end = value.find(">")
        return value[1:end] if end > 0 else None
    escaped = False
    depth = 0
    for index, character in enumerate(value):
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == "(":
            depth += 1
        elif character == ")" and depth:
            depth -= 1
        elif character.isspace() and depth == 0:
            return value[:index]
    return value


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def strip_inline_code_spans(text: str) -> str:
    """Blank CommonMark code spans while preserving line endings and offsets."""
    output = list(text)
    index = 0
    while index < len(text):
        if text[index] != "`" or _is_escaped(text, index):
            index += 1
            continue
        run_end = index
        while run_end < len(text) and text[run_end] == "`":
            run_end += 1
        run_length = run_end - index
        cursor = run_end
        closing_start: int | None = None
        while cursor < len(text):
            if text[cursor] != "`":
                cursor += 1
                continue
            closing_end = cursor
            while closing_end < len(text) and text[closing_end] == "`":
                closing_end += 1
            if closing_end - cursor == run_length:
                closing_start = cursor
                break
            cursor = closing_end
        if closing_start is None:
            index = run_end
            continue
        span_end = closing_start + run_length
        for position in range(index, span_end):
            if output[position] not in {"\n", "\r"}:
                output[position] = " "
        index = span_end
    return "".join(output)


def _matching_open_bracket(text: str, close_index: int) -> int | None:
    depth = 1
    for index in range(close_index - 1, -1, -1):
        if _is_escaped(text, index):
            continue
        if text[index] == "]":
            depth += 1
        elif text[index] == "[":
            depth -= 1
            if depth == 0:
                return index
    return None


def iter_inline_link_destinations(text: str) -> Iterator[str]:
    """Yield destinations from inline Markdown links using balanced parentheses."""
    cursor = 0
    while True:
        close_bracket = text.find("](", cursor)
        if close_bracket < 0:
            return
        open_bracket = _matching_open_bracket(text, close_bracket)
        if open_bracket is None or _is_escaped(text, open_bracket):
            cursor = close_bracket + 2
            continue
        if open_bracket > 0 and text[open_bracket - 1] == "!" and not _is_escaped(text, open_bracket - 1):
            cursor = close_bracket + 2
            continue
        start = close_bracket + 2
        depth = 1
        escaped = False
        quote: str | None = None
        index = start
        while index < len(text):
            character = text[index]
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif quote:
                if character == quote:
                    quote = None
            elif character in {'"', "'"}:
                quote = character
            elif character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0:
                    destination = _extract_destination(text[start:index])
                    if destination:
                        yield destination
                    cursor = index + 1
                    break
            index += 1
        else:
            cursor = start


def _normalize_reference_label(label: str) -> str:
    return " ".join(label.replace("\\", "").split()).casefold()


def _is_image_label(text: str, index: int) -> bool:
    return index > 0 and text[index - 1] == "!" and not _is_escaped(text, index - 1)


def iter_reference_link_destinations(text: str) -> Iterator[str]:
    """Yield destinations used by full, collapsed, and shortcut reference links."""
    definitions: dict[str, str] = {}
    definition_spans: list[tuple[int, int]] = []
    for match in REFERENCE_DEFINITION.finditer(text):
        destination = _extract_destination(match.group("raw"))
        if destination:
            definitions[_normalize_reference_label(match.group("label"))] = destination
            definition_spans.append(match.span())

    for match in REFERENCE_LINK.finditer(text):
        if _is_escaped(text, match.start()) or _is_image_label(text, match.start()):
            continue
        reference = match.group("reference") or match.group("label")
        destination = definitions.get(_normalize_reference_label(reference))
        if destination:
            yield destination

    for match in BRACKETED_LABEL.finditer(text):
        start, end = match.span()
        if _is_escaped(text, start) or _is_image_label(text, start):
            continue
        if start > 0 and text[start - 1] == "]" and not _is_escaped(text, start - 1):
            continue
        if any(span_start <= start < span_end for span_start, span_end in definition_spans):
            continue
        if text[end : end + 1] in {"(", "[", ":"}:
            continue
        destination = definitions.get(_normalize_reference_label(match.group("label")))
        if destination:
            yield destination


def iter_link_destinations(text: str) -> Iterator[str]:
    yield from iter_inline_link_destinations(text)
    yield from iter_reference_link_destinations(text)


def _has_explicit_verification(metadata: Mapping[str, Any], body: str) -> bool:
    verification = metadata.get("verification")
    if isinstance(verification, str) and verification.strip():
        return True
    if isinstance(verification, (list, dict)) and verification:
        return True
    match = re.search(
        r"^##\s+Verification\s*$\n(?P<content>.*?)(?=^##\s+|\Z)",
        body,
        re.M | re.S | re.I,
    )
    return bool(match and match.group("content").strip())


def _load_governance(path: Path) -> Governance:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise ValueError("governance must be a schema_version 1 mapping")
    raw_profiles = raw.get("profiles")
    if not isinstance(raw_profiles, dict) or not raw_profiles:
        raise ValueError("governance profiles must be a non-empty mapping")
    profiles: dict[str, dict[str, bool]] = {}
    for name, value in raw_profiles.items():
        if not isinstance(name, str) or not name or not isinstance(value, dict):
            raise ValueError("governance profile names and values are invalid")
        required_options = set(DEFAULT_PROFILES["governed"])
        if set(value) != required_options:
            missing = sorted(required_options - set(value))
            unknown = sorted(set(value) - required_options)
            raise ValueError(
                f"profile {name!r} must declare exactly the supported options; "
                f"missing={missing}, unknown={unknown}"
            )
        profile_options: dict[str, bool] = {}
        for key in DEFAULT_PROFILES["governed"]:
            candidate = value[key]
            if type(candidate) is not bool:
                raise ValueError(f"profile {name!r} option {key!r} must be boolean")
            profile_options[key] = candidate
        profiles[name] = profile_options
    default_profile = raw.get("default_profile", "governed")
    if default_profile not in profiles:
        raise ValueError("default_profile does not identify a configured profile")
    raw_assignments = raw.get("documents", [])
    if not isinstance(raw_assignments, list):
        raise ValueError("governance documents must be a list")
    assignments: list[tuple[str, str]] = []
    for entry in raw_assignments:
        if not isinstance(entry, dict) or set(entry) != {"match", "profile"}:
            raise ValueError("each governance document entry needs only match and profile")
        pattern = entry["match"]
        profile = entry["profile"]
        if not isinstance(pattern, str) or not pattern or pattern.startswith("/") or "\\" in pattern:
            raise ValueError("governance match must be a safe repository-relative POSIX glob")
        if any(part == ".." for part in PurePosixPath(pattern).parts):
            raise ValueError("governance match must not contain parent traversal")
        if profile not in profiles:
            raise ValueError(f"unknown governance profile: {profile}")
        assignments.append((pattern, profile))
    return Governance(profiles, tuple(assignments), default_profile)


def _profile_for(path: Path, repository_root: Path, governance: Governance | None) -> Mapping[str, bool]:
    if governance is None:
        return DEFAULT_PROFILES["governed"]
    relative = path.resolve(strict=False).relative_to(repository_root.resolve()).as_posix()
    selected = governance.default_profile
    for pattern, profile in governance.assignments:
        if fnmatch.fnmatchcase(relative, pattern):
            selected = profile
    return governance.profiles[selected]


def _read_regular_utf8(path: Path, repository_root: Path) -> tuple[str | None, str | None]:
    try:
        root = repository_root.resolve(strict=True)
        candidate = path if path.is_absolute() else Path.cwd() / path
        lexical = candidate.relative_to(root)
    except (OSError, ValueError):
        return None, "document path must remain inside repository root"
    if any(part in {"", ".", ".."} for part in lexical.parts):
        return None, "document path must remain inside repository root"
    current = root
    for part in lexical.parts:
        current = current / part
        try:
            metadata = current.lstat()
        except OSError as exc:
            return None, f"cannot inspect document safely: {exc}"
        if stat.S_ISLNK(metadata.st_mode):
            return None, "document path must not contain symlinks"
    try:
        metadata = candidate.stat()
    except OSError as exc:
        return None, f"cannot inspect document safely: {exc}"
    if not stat.S_ISREG(metadata.st_mode):
        return None, "document path must be a regular file"
    if metadata.st_size > MAX_DOCUMENT_BYTES:
        return None, f"document exceeds {MAX_DOCUMENT_BYTES} byte limit"
    try:
        return candidate.read_text(encoding="utf-8"), None
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"cannot read document as UTF-8: {exc}"


def _github_anchor(title: str) -> str:
    value = strip_inline_code_spans(title).strip().casefold()
    value = re.sub(r"[^\w\- ]", "", value, flags=re.UNICODE)
    return re.sub(r"\s+", "-", value).strip("-")


def _anchors(text: str) -> set[str]:
    body = strip_inline_code_spans(strip_fenced_blocks(text))
    counts: dict[str, int] = {}
    result: set[str] = set()
    for _level, title in HEADING.findall(body):
        base = _github_anchor(title)
        if not base:
            continue
        number = counts.get(base, 0)
        result.add(base if number == 0 else f"{base}-{number}")
        counts[base] = number + 1
    return result


def _safe_link_target(source: Path, raw_target: str, repository_root: Path) -> tuple[Path | None, str | None]:
    if "\\" in raw_target:
        return None, "link target must use POSIX separators"
    candidate_path = PurePosixPath(raw_target)
    if candidate_path.is_absolute() or any(part in {"", ".", ".."} for part in candidate_path.parts):
        return None, "link target must be a confined repository-relative path"
    root = repository_root.resolve()
    candidate = source.parent.joinpath(*candidate_path.parts)
    try:
        relative = candidate.absolute().relative_to(root)
    except ValueError:
        return None, "link target escapes repository root"
    current = root
    for part in relative.parts:
        current = current / part
        if not os.path.lexists(current):
            return None, None
        try:
            metadata = current.lstat()
        except OSError as exc:
            return None, f"cannot inspect link target safely: {exc}"
        if stat.S_ISLNK(metadata.st_mode):
            return None, "link target must not contain symlinks"
    try:
        metadata = candidate.stat()
    except OSError:
        return None, None
    if not stat.S_ISREG(metadata.st_mode):
        return None, "link target must be a regular file"
    if metadata.st_size > MAX_DOCUMENT_BYTES:
        return None, f"link target exceeds {MAX_DOCUMENT_BYTES} byte limit"
    return candidate, None


def _validate_links(path: Path, body: str, repository_root: Path, *, check_anchors: bool) -> list[Finding]:
    findings: list[Finding] = []
    anchor_cache: dict[Path, set[str]] = {}
    for destination in iter_link_destinations(body):
        decoded = unquote(destination)
        if re.match(r"^[a-z][a-z0-9+.-]*:", decoded, re.I) or decoded.startswith("//"):
            continue
        raw_path, separator, fragment = decoded.partition("#")
        display = decoded
        if not raw_path:
            target_path = path
        else:
            target_path, unsafe = _safe_link_target(path, raw_path, repository_root)
            if unsafe:
                findings.append(Finding(path, f"unsafe relative link: {raw_path}: {unsafe}"))
                continue
            if target_path is None:
                findings.append(Finding(path, f"broken relative link: {raw_path}"))
                continue
        if separator and fragment and check_anchors:
            try:
                anchors = anchor_cache.setdefault(
                    target_path,
                    _anchors(target_path.read_text(encoding="utf-8")),
                )
            except (OSError, UnicodeDecodeError):
                findings.append(Finding(path, f"cannot inspect relative anchor: {display}"))
                continue
            normalized_fragment = _github_anchor(fragment)
            if normalized_fragment not in anchors:
                findings.append(Finding(path, f"broken relative anchor: {display}"))
    return findings


def _discover_repository_root(path: Path) -> Path:
    """Find the nearest repository root that owns the AFDS governance file."""
    candidate = path.absolute()
    start = candidate if candidate.is_dir() else candidate.parent
    for parent in (start, *start.parents):
        if (parent / "skills/afds-doc-writer/governance.yaml").is_file():
            return parent.resolve()
    return start.resolve()


def validate(
    path: Path,
    repository_root: Path | None = None,
    *,
    profile: Mapping[str, bool] | None = None,
    governance: Governance | None = None,
) -> list[Finding]:
    """Validate one Markdown document under its selected governance profile."""
    root = (repository_root or _discover_repository_root(path)).resolve()
    if governance is None:
        governance_path = root / "skills/afds-doc-writer/governance.yaml"
        if governance_path.is_file():
            try:
                governance = _load_governance(governance_path)
            except (OSError, ValueError, yaml.YAMLError) as exc:
                return [Finding(governance_path, f"invalid governance: {exc}")]
    text, read_error = _read_regular_utf8(path, root)
    if read_error:
        return [Finding(path, read_error)]
    assert text is not None
    selected = profile or _profile_for(path, root, governance)

    match = FRONTMATTER.search(text)
    metadata: Mapping[str, Any] = {}
    body = text
    findings: list[Finding] = []
    if selected.get("require_frontmatter", True):
        if not match:
            return [Finding(path, "missing YAML frontmatter")]
        try:
            loaded = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError as exc:
            return [Finding(path, f"invalid YAML: {exc}")]
        if not isinstance(loaded, dict):
            return [Finding(path, "frontmatter must be a mapping")]
        metadata = loaded
        body = text[match.end() :]

        missing = sorted(field for field in COMMON_REQUIRED if not metadata.get(field))
        if missing:
            findings.append(Finding(path, f"missing required fields: {', '.join(missing)}"))
        description = metadata.get("description")
        if not isinstance(description, str) or not description.strip():
            findings.append(Finding(path, "description must be a non-empty string"))
        owners = metadata.get("owners")
        if not (
            isinstance(owners, list)
            and owners
            and all(isinstance(owner, str) and owner.strip() for owner in owners)
        ):
            findings.append(
                Finding(path, "owners must be a non-empty list of role or team names")
            )

        doc_type = metadata.get("type")
        doc_id = metadata.get("doc_id")
        status = metadata.get("status")
        rigor = metadata.get("rigor")
        if not isinstance(doc_type, str) or doc_type not in VALID_TYPES:
            findings.append(Finding(path, f"invalid type: {doc_type}"))
        if not isinstance(doc_id, str) or not DOC_ID.fullmatch(doc_id):
            findings.append(Finding(path, f"invalid doc_id: {doc_id}"))
        elif isinstance(doc_type, str) and doc_type in VALID_TYPES and not doc_id.startswith(f"{doc_type}."):
            findings.append(Finding(path, "doc_id prefix does not match type"))
        if not isinstance(status, str) or status not in VALID_STATUS:
            findings.append(Finding(path, f"invalid status: {status}"))
        if not isinstance(rigor, str) or rigor not in VALID_RIGOR:
            findings.append(Finding(path, f"invalid rigor: {rigor}"))
        authored = sorted(AUTOMATION_FIELDS.intersection(metadata))
        if authored:
            findings.append(Finding(path, f"automation-owned fields: {', '.join(authored)}"))
        if (
            selected.get("require_verification_by_rigor", True)
            and isinstance(rigor, str)
            and rigor in {"operational", "normative"}
            and not _has_explicit_verification(metadata, strip_inline_code_spans(strip_fenced_blocks(body)))
        ):
            findings.append(Finding(path, "missing explicit verification method"))
    elif match:
        body = text[match.end() :]

    structural_body = strip_inline_code_spans(strip_fenced_blocks(body))
    if selected.get("check_structure", True):
        headings = HEADING.findall(structural_body)
        if sum(level == "#" for level, _ in headings) != 1:
            findings.append(Finding(path, "expected exactly one H1"))
        normalized = [re.sub(r"[^a-z0-9]+", " ", title.lower()).strip() for _, title in headings]
        duplicates = sorted({title for title in normalized if normalized.count(title) > 1})
        if duplicates:
            findings.append(Finding(path, f"duplicate headings: {', '.join(duplicates)}"))
    if selected.get("check_links", True):
        findings.extend(
            _validate_links(
                path,
                structural_body,
                root,
                check_anchors=selected.get("check_anchors", True),
            )
        )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--governance", type=Path)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    governance_path = args.governance or root / "skills/afds-doc-writer/governance.yaml"
    governance: Governance | None = None
    findings: list[Finding] = []
    if governance_path.exists():
        try:
            governance = _load_governance(governance_path)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            findings.append(Finding(governance_path, f"invalid governance: {exc}"))
    paths, input_findings = collect_files(args.inputs)
    findings.extend(input_findings)
    findings.extend(finding for path in paths for finding in validate(path, root, governance=governance))
    for finding in findings:
        print(f"{finding.path}: {finding.message}", file=sys.stderr)
    print(f"validated {len(paths)} markdown files; findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
