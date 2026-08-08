#!/usr/bin/env python3
"""Validate AFDS-governed Markdown, foreign frontmatter, links, anchors, and repository confinement."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from urllib.parse import unquote, urlsplit

import yaml
from jsonschema import Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_GOVERNANCE = SCRIPT_DIR / "governance.yaml"
FRONTMATTER_SCHEMA = REPOSITORY_ROOT / "contracts/afds-frontmatter.schema.json"
GOVERNANCE_SCHEMA = REPOSITORY_ROOT / "contracts/afds-governance.schema.json"
LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
HTML_ANCHOR_RE = re.compile(r"<a\s+(?:name|id)=[\"']([^\"']+)[\"']", re.IGNORECASE)


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False):  # type: ignore[no-untyped-def]
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.YAMLError(f"duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


@dataclass(frozen=True, slots=True)
class Profile:
    name: str
    kind: str
    conformance_eligible: bool
    frontmatter_mode: str
    check_structure: bool
    check_links: bool
    check_anchors: bool
    require_verification_by_rigor: bool


def _safe_yaml(text: str, source: Path) -> Any:
    try:
        return yaml.load(text, Loader=UniqueKeyLoader)  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as exc:
        raise ValueError(f"{source}: invalid YAML: {exc}") from exc


def _load_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{path}: schema root must be an object")
    Draft202012Validator.check_schema(value)
    return value


def _load_governance(path: Path) -> Mapping[str, Any]:
    value = _safe_yaml(path.read_text(encoding="utf-8"), path)
    if not isinstance(value, Mapping):
        raise ValueError(f"{path}: governance root must be a mapping")
    schema = _load_json(GOVERNANCE_SCHEMA)
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda error: tuple(error.absolute_path))
    if errors:
        location = ".".join(str(item) for item in errors[0].absolute_path) or "$"
        raise ValueError(f"{path}: governance schema {location}: {errors[0].message}")
    if value.get("schema_version") != 2:
        raise ValueError(f"{path}: governance schema_version must equal 2")
    profiles = value.get("profiles", {})
    if not isinstance(profiles, Mapping):
        raise ValueError(f"{path}: profiles must be a mapping")
    for name, raw in profiles.items():
        if not isinstance(raw, Mapping):
            continue
        if raw.get("conformance_eligible") is True:
            disabled = [
                check
                for check in ("check_structure", "check_links", "check_anchors")
                if raw.get(check) is not True
            ]
            if disabled:
                raise ValueError(
                    f"{path}: conformance-eligible profile {name} cannot disable structural/link/anchor checks: {disabled}"
                )
            if raw.get("frontmatter_mode") != "afds-required":
                raise ValueError(
                    f"{path}: conformance-eligible profile {name} must require AFDS frontmatter"
                )
            if raw.get("require_verification_by_rigor") is not True:
                raise ValueError(
                    f"{path}: conformance-eligible profile {name} cannot disable verification-by-rigor"
                )
    return value


def _profile(governance: Mapping[str, Any], document: Path, repository_root: Path) -> Profile:
    relative = document.relative_to(repository_root).as_posix()
    selected = governance.get("default_profile")
    rules = governance.get("documents", [])
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, Mapping):
                continue
            pattern = rule.get("match")
            if isinstance(pattern, str) and fnmatch.fnmatchcase(relative, pattern):
                selected = rule.get("profile")
                break
    profiles = governance.get("profiles", {})
    raw = profiles.get(selected) if isinstance(profiles, Mapping) else None
    if not isinstance(selected, str) or not isinstance(raw, Mapping):
        raise ValueError(f"{document}: no valid AFDS governance profile")
    return Profile(
        name=selected,
        kind=str(raw.get("kind", "afds")),
        conformance_eligible=bool(raw.get("conformance_eligible")),
        frontmatter_mode=str(raw.get("frontmatter_mode")),
        check_structure=bool(raw.get("check_structure")),
        check_links=bool(raw.get("check_links")),
        check_anchors=bool(raw.get("check_anchors")),
        require_verification_by_rigor=bool(raw.get("require_verification_by_rigor")),
    )


def _split_frontmatter(text: str, source: Path) -> tuple[Mapping[str, Any] | None, str, bool]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, text, False
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break
    if end is None:
        raise ValueError(f"{source}: unterminated YAML frontmatter")
    raw = "\n".join(lines[1:end])
    metadata = _safe_yaml(raw, source)
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, Mapping):
        raise ValueError(f"{source}: YAML frontmatter must be a mapping")
    body = "\n".join(lines[end + 1 :])
    if text.endswith("\n"):
        body += "\n"
    return metadata, body, True


def _schema_metadata_findings(metadata: Mapping[str, Any], source: Path, minimum: int | None) -> list[str]:
    schema = _load_json(FRONTMATTER_SCHEMA)
    findings: list[str] = []
    validator = Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(metadata), key=lambda item: tuple(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        findings.append(f"{source}: frontmatter {location}: {error.message}")
    version = metadata.get("afds_schema_version")
    if minimum is not None and (not isinstance(version, int) or version < minimum):
        findings.append(f"{source}: afds_schema_version must be at least {minimum}")
    return findings


def _visible_lines(body: str):  # type: ignore[no-untyped-def]
    fenced = False
    fence = ""
    for line in body.splitlines():
        marker = FENCE_RE.match(line)
        if marker:
            current = marker.group(1)
            if not fenced:
                fenced = True
                fence = current[0]
            elif current.startswith(fence):
                fenced = False
            continue
        if not fenced:
            yield line


def _heading_text(raw: str) -> str:
    text = re.sub(r"\s+#+\s*$", "", raw).strip()
    text = re.sub(r"[`*_~]", "", text)
    return text


def _slug(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[^\w\- ]", "", text, flags=re.UNICODE)
    text = text.replace(" ", "-")
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def _anchors(body: str) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    for line in _visible_lines(body):
        for explicit in HTML_ANCHOR_RE.findall(line):
            anchors.add(explicit)
        match = HEADING_RE.match(line)
        if not match:
            continue
        base = _slug(_heading_text(match.group(2)))
        if not base:
            continue
        count = counts.get(base, 0)
        counts[base] = count + 1
        anchors.add(base if count == 0 else f"{base}-{count}")
    return anchors


def _structure_findings(body: str, source: Path) -> list[str]:
    findings: list[str] = []
    headings: list[tuple[int, str]] = []
    for line in _visible_lines(body):
        match = HEADING_RE.match(line)
        if match:
            headings.append((len(match.group(1)), _heading_text(match.group(2))))
    h1 = [heading for heading in headings if heading[0] == 1]
    if len(h1) != 1:
        findings.append(f"{source}: document must contain exactly one H1 heading")
    previous = 0
    for level, title in headings:
        if previous and level > previous + 1:
            findings.append(f"{source}: heading level skips from H{previous} to H{level} at {title!r}")
        previous = level
    return findings


def _confined(path: Path, repository_root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(repository_root.resolve())
        return True
    except ValueError:
        return False


def _link_target(raw: str) -> tuple[str, str]:
    value = raw.strip()
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1]
    if " " in value and not value.startswith(("http://", "https://")):
        value = value.split(" ", 1)[0]
    split = urlsplit(value)
    return unquote(split.path), unquote(split.fragment)


def _links(body: str) -> list[str]:
    visible = "\n".join(_visible_lines(body))
    return [match.group(1) for match in LINK_RE.finditer(visible)]


def _link_findings(body: str, source: Path, repository_root: Path, *, check_anchors: bool) -> list[str]:
    findings: list[str] = []
    source_anchors = _anchors(body) if check_anchors else set()
    for raw in _links(body):
        split = urlsplit(raw.strip().strip("<>"))
        if split.scheme or split.netloc:
            continue
        path_part, fragment = _link_target(raw)
        if not path_part:
            if check_anchors and fragment and fragment not in source_anchors:
                findings.append(f"{source}: broken anchor link: #{fragment}")
            continue
        pure = PurePosixPath(path_part)
        if pure.is_absolute() or ".." in pure.parts and not _confined(source.parent.joinpath(*pure.parts), repository_root):
            findings.append(f"{source}: relative link escapes repository: {raw}")
            continue
        target = source.parent.joinpath(*pure.parts)
        if not _confined(target, repository_root):
            findings.append(f"{source}: relative link escapes repository: {raw}")
            continue
        try:
            resolved = target.resolve(strict=True)
        except FileNotFoundError:
            findings.append(f"{source}: broken relative link: {path_part}")
            continue
        if not _confined(resolved, repository_root):
            findings.append(f"{source}: linked target escapes repository: {path_part}")
            continue
        if check_anchors and fragment:
            if resolved.suffix.lower() != ".md":
                findings.append(f"{source}: anchor target is not Markdown: {raw}")
                continue
            try:
                target_text = resolved.read_text(encoding="utf-8")
                _, target_body, _ = _split_frontmatter(target_text, resolved)
            except (OSError, UnicodeError, ValueError) as exc:
                findings.append(f"{source}: cannot inspect anchor target {path_part}: {exc}")
                continue
            if fragment not in _anchors(target_body):
                findings.append(f"{source}: broken relative anchor: {raw}")
    return findings


def validate_document(
    document: Path,
    *,
    repository_root: Path | None = None,
    governance_path: Path | None = None,
    minimum_document_schema: int | None = None,
) -> list[str]:
    repository_root = (repository_root or REPOSITORY_ROOT).resolve()
    governance_path = governance_path or DEFAULT_GOVERNANCE
    try:
        document = document.resolve(strict=True)
    except FileNotFoundError:
        return [f"{document}: document does not exist"]
    if not _confined(document, repository_root):
        return [f"{document}: document escapes repository root"]
    if document.is_symlink() or not document.is_file():
        return [f"{document}: document must be a regular non-symlink file"]
    try:
        governance = _load_governance(governance_path)
        profile = _profile(governance, document, repository_root)
        text = document.read_text(encoding="utf-8")
        metadata, body, has_frontmatter = _split_frontmatter(text, document)
    except (OSError, UnicodeError, ValueError) as exc:
        return [str(exc)]

    findings: list[str] = []
    if profile.frontmatter_mode == "afds-required":
        if not has_frontmatter or metadata is None:
            findings.append(f"{document}: AFDS frontmatter is required by profile {profile.name}")
        else:
            findings.extend(_schema_metadata_findings(metadata, document, minimum_document_schema))
    elif profile.frontmatter_mode == "foreign-allowed":
        # Parsing above proves syntax only. Foreign metadata is never interpreted as AFDS.
        pass
    elif profile.frontmatter_mode == "absent":
        if has_frontmatter:
            findings.append(f"{document}: frontmatter is forbidden by profile {profile.name}")
    else:
        findings.append(f"{document}: unsupported frontmatter_mode {profile.frontmatter_mode!r}")

    if profile.check_structure:
        findings.extend(_structure_findings(body, document))
    if profile.check_links:
        findings.extend(_link_findings(body, document, repository_root, check_anchors=profile.check_anchors))
    return findings


def _collect(paths: list[Path], repository_root: Path) -> list[Path]:
    documents: set[Path] = set()
    for raw in paths:
        candidate = raw if raw.is_absolute() else repository_root / raw
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError:
            documents.add(candidate)
            continue
        if resolved.is_dir():
            documents.update(path for path in resolved.rglob("*.md") if path.is_file())
        else:
            documents.add(resolved)
    return sorted(documents, key=lambda path: path.as_posix())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--governance", type=Path, default=DEFAULT_GOVERNANCE)
    parser.add_argument("--minimum-document-schema", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repository_root = args.repository_root.resolve()
    try:
        _load_governance(args.governance)
    except (OSError, UnicodeError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1
    documents = _collect(args.paths, repository_root)
    findings: list[str] = []
    for document in documents:
        findings.extend(
            validate_document(
                document,
                repository_root=repository_root,
                governance_path=args.governance,
                minimum_document_schema=args.minimum_document_schema,
            )
        )
    for finding in findings:
        print(finding, file=sys.stderr)
    print(f"validated {len(documents)} markdown files; findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
