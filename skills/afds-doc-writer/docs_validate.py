#!/usr/bin/env python3
"""Validate AFDS v3 Markdown documents without judging prose style."""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.M)
LINK = re.compile(r"\[[^\]]+\]\((?!https?://|mailto:|#)([^)]+)\)")
DOC_ID = re.compile(r"^(workflow|reference|system|guide|decision|contract)\.[a-z0-9][a-z0-9.-]*$")
VALID_TYPES = {"workflow", "reference", "system", "guide", "decision", "contract"}
VALID_STATUS = {"draft", "active", "evolving", "deprecated", "archived"}
VALID_RIGOR = {"informative", "operational", "normative"}


@dataclass(frozen=True)
class Finding:
    path: Path
    severity: str
    code: str
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.severity}:{self.code}: {self.message}"


def load_config(path: Path | None) -> dict[str, Any]:
    if path is None:
        path = Path(__file__).with_name("afds_config.yaml")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def markdown_files(inputs: Iterable[Path], excluded: set[str]) -> list[Path]:
    result: set[Path] = set()
    for item in inputs:
        if item.is_file() and item.suffix.lower() == ".md":
            result.add(item)
        elif item.is_dir():
            for path in item.rglob("*.md"):
                parts = set(path.parts)
                if parts.intersection(excluded):
                    continue
                result.add(path)
    return sorted(result)


def parse_document(path: Path) -> tuple[dict[str, Any] | None, str, list[Finding]]:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER.search(text)
    if not match:
        return None, text, [Finding(path, "ERROR", "AFDS001", "missing YAML frontmatter")]
    try:
        metadata = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        return None, text, [Finding(path, "ERROR", "AFDS002", f"invalid YAML: {exc}")]
    if not isinstance(metadata, dict):
        return None, text, [Finding(path, "ERROR", "AFDS003", "frontmatter must be a mapping")]
    return metadata, text[match.end():], []


def validate_document(path: Path, config: dict[str, Any]) -> list[Finding]:
    metadata, body, findings = parse_document(path)
    if metadata is None:
        return findings

    required = config.get("required_frontmatter", [])
    for field in required:
        if field not in metadata or metadata[field] in (None, "", []):
            findings.append(Finding(path, "ERROR", "AFDS010", f"missing required field '{field}'"))

    doc_type = metadata.get("type")
    doc_id = metadata.get("doc_id")
    if doc_type not in VALID_TYPES:
        findings.append(Finding(path, "ERROR", "AFDS011", f"invalid type '{doc_type}'"))
    if not isinstance(doc_id, str) or not DOC_ID.fullmatch(doc_id):
        findings.append(Finding(path, "ERROR", "AFDS012", f"invalid doc_id '{doc_id}'"))
    elif doc_type and not doc_id.startswith(f"{doc_type}."):
        findings.append(Finding(path, "ERROR", "AFDS013", "doc_id prefix does not match type"))
    if metadata.get("status") not in VALID_STATUS:
        findings.append(Finding(path, "ERROR", "AFDS014", f"invalid status '{metadata.get('status')}'"))
    if metadata.get("rigor") not in VALID_RIGOR:
        findings.append(Finding(path, "ERROR", "AFDS015", f"invalid rigor '{metadata.get('rigor')}'"))
    if metadata.get("schema_version") != 3:
        findings.append(Finding(path, "ERROR", "AFDS016", "schema_version must be 3"))

    headings = HEADING.findall(body)
    h1s = [title for level, title in headings if level == "#"]
    if len(h1s) != 1:
        findings.append(Finding(path, "ERROR", "AFDS020", f"expected one H1, found {len(h1s)}"))
    normalized = [re.sub(r"[^a-z0-9]+", " ", title.lower()).strip() for _, title in headings]
    duplicates = sorted({title for title in normalized if normalized.count(title) > 1})
    if duplicates:
        findings.append(Finding(path, "ERROR", "AFDS021", f"duplicate headings: {', '.join(duplicates)}"))

    lowered = body.lower()
    concepts = config.get("types", {}).get(doc_type, {}).get("required_concepts", [])
    missing = [concept for concept in concepts if concept not in lowered]
    if missing:
        findings.append(Finding(path, "WARNING", "AFDS030", f"type profile may be incomplete: {', '.join(missing)}"))

    if metadata.get("rigor") in {"operational", "normative"} and "validation" not in lowered and doc_type not in {"reference", "contract"}:
        findings.append(Finding(path, "WARNING", "AFDS031", "operational or normative document has no validation section or statement"))

    for target in LINK.findall(body):
        target = target.split("#", 1)[0]
        if not target:
            continue
        resolved = (path.parent / target).resolve()
        if not resolved.exists():
            findings.append(Finding(path, "ERROR", "AFDS040", f"broken relative link '{target}'"))

    volatile = {"last_verified", "fitness_score", "semantic_hash", "dependency_versions", "backlinks"}
    authored_volatile = sorted(volatile.intersection(metadata))
    if authored_volatile:
        findings.append(Finding(path, "ERROR", "AFDS050", f"automation-owned fields in source: {', '.join(authored_volatile)}"))

    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--warnings-as-errors", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    files = markdown_files(args.inputs, set(config.get("exclude", [])))
    if not files:
        print("No Markdown files found", file=sys.stderr)
        return 1

    findings = [finding for path in files for finding in validate_document(path, config)]
    for finding in findings:
        print(finding.render())

    errors = sum(f.severity == "ERROR" for f in findings)
    warnings = sum(f.severity == "WARNING" for f in findings)
    print(f"Validated {len(files)} files: {errors} errors, {warnings} warnings")
    return 1 if errors or (args.warnings_as_errors and warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
