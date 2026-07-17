#!/usr/bin/env python3
"""Validate governed Markdown documents used by this skills collection."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator
from urllib.parse import unquote

import yaml

FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
FENCED_BLOCK = re.compile(r"^(?P<fence>`{3,}|~{3,})[^\n]*\n.*?^\s*(?P=fence)\s*$", re.M | re.S)
DOC_ID = re.compile(r"^(workflow|reference|system|guide|decision|contract)\.[a-z0-9][a-z0-9.-]*$")
REQUIRED = {"description", "doc_id", "type", "status", "rigor", "owners"}
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
EXEMPT_NAMES = {"README.md", "SKILL.md", "CHANGELOG.md"}


@dataclass(frozen=True)
class Finding:
    """One validation error associated with a path."""

    path: Path
    message: str


def collect_files(inputs: Iterable[Path]) -> tuple[list[Path], list[Finding]]:
    """Resolve explicit Markdown inputs and reject missing or unsupported paths."""
    files: set[Path] = set()
    findings: list[Finding] = []

    for item in inputs:
        if not item.exists():
            findings.append(Finding(item, "input does not exist"))
        elif item.is_file():
            if item.suffix.lower() != ".md":
                findings.append(Finding(item, "explicit input is not a Markdown file"))
            else:
                files.add(item)
        elif item.is_dir():
            files.update(
                path
                for path in item.rglob("*.md")
                if ".git" not in path.parts and ".venv" not in path.parts
            )
        else:
            findings.append(Finding(item, "unsupported input type"))

    if not files and not findings:
        findings.append(Finding(Path("."), "no Markdown documents selected"))
    return sorted(files), findings


def strip_fenced_blocks(text: str) -> str:
    """Remove fenced code blocks while preserving line boundaries."""

    def replace(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    return FENCED_BLOCK.sub(replace, text)


def _extract_destination(raw: str) -> str | None:
    """Extract a Markdown link destination while ignoring an optional title."""
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
            continue
        if character == "\\":
            escaped = True
            continue
        if character == "(":
            depth += 1
            continue
        if character == ")" and depth:
            depth -= 1
            continue
        if character.isspace() and depth == 0:
            return value[:index]
    return value


def iter_link_destinations(text: str) -> Iterator[str]:
    """Yield destinations from inline Markdown links using balanced parentheses."""
    cursor = 0
    while True:
        opener = text.find("](", cursor)
        if opener < 0:
            return
        if opener > 0 and text[opener - 1] == "!":
            cursor = opener + 2
            continue

        start = opener + 2
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


def _has_explicit_verification(metadata: dict, body: str) -> bool:
    """Return whether a document states a concrete verification method."""
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


def validate(path: Path) -> list[Finding]:
    """Validate one governed Markdown document."""
    text = path.read_text(encoding="utf-8")
    if path.name in EXEMPT_NAMES:
        return []

    match = FRONTMATTER.search(text)
    if not match:
        return [Finding(path, "missing YAML frontmatter")]

    try:
        metadata = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        return [Finding(path, f"invalid YAML: {exc}")]
    if not isinstance(metadata, dict):
        return [Finding(path, "frontmatter must be a mapping")]

    findings: list[Finding] = []
    missing = sorted(field for field in REQUIRED if not metadata.get(field))
    if missing:
        findings.append(Finding(path, f"missing required fields: {', '.join(missing)}"))

    doc_type = metadata.get("type")
    doc_id = metadata.get("doc_id")
    if doc_type not in VALID_TYPES:
        findings.append(Finding(path, f"invalid type: {doc_type}"))
    if not isinstance(doc_id, str) or not DOC_ID.fullmatch(doc_id):
        findings.append(Finding(path, f"invalid doc_id: {doc_id}"))
    elif doc_type and not doc_id.startswith(f"{doc_type}."):
        findings.append(Finding(path, "doc_id prefix does not match type"))
    if metadata.get("status") not in VALID_STATUS:
        findings.append(Finding(path, f"invalid status: {metadata.get('status')}"))
    if metadata.get("rigor") not in VALID_RIGOR:
        findings.append(Finding(path, f"invalid rigor: {metadata.get('rigor')}"))

    authored = sorted(AUTOMATION_FIELDS.intersection(metadata))
    if authored:
        findings.append(Finding(path, f"automation-owned fields: {', '.join(authored)}"))

    body = text[match.end() :]
    structural_body = strip_fenced_blocks(body)
    headings = HEADING.findall(structural_body)
    if sum(level == "#" for level, _ in headings) != 1:
        findings.append(Finding(path, "expected exactly one H1"))

    normalized = [
        re.sub(r"[^a-z0-9]+", " ", title.lower()).strip() for _, title in headings
    ]
    duplicates = sorted({title for title in normalized if normalized.count(title) > 1})
    if duplicates:
        findings.append(Finding(path, f"duplicate headings: {', '.join(duplicates)}"))

    for target in iter_link_destinations(structural_body):
        target = unquote(target.split("#", 1)[0])
        if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):
            continue
        if not (path.parent / target).resolve().exists():
            findings.append(Finding(path, f"broken relative link: {target}"))

    if metadata.get("rigor") in {"operational", "normative"} and not _has_explicit_verification(metadata, structural_body):
        findings.append(Finding(path, "missing explicit verification method"))

    return findings


def main() -> int:
    """Run validation for command-line inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    args = parser.parse_args()

    paths, findings = collect_files(args.inputs)
    findings.extend(finding for path in paths for finding in validate(path))
    for finding in findings:
        print(f"{finding.path}: {finding.message}", file=sys.stderr)
    print(f"validated {len(paths)} markdown files; findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
