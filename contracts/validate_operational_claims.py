#!/usr/bin/env python3
"""Validate volatile configuration and runtime capability claims against exact evidence."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from contracts.confined_io import confined_regular_file

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts/operational-claims.schema.json"
_NON_EXACT_VERSION = re.compile(
    r"(?:^|[._+\-])(?:latest|current|main|master|nightly|stable|release|edge|canary|rolling|snapshot|dev|development|head|tip|trunk|x)(?:$|[._+\-])",
    re.IGNORECASE,
)
_RANGE_SYNTAX = re.compile(r"(?:^|[\s,])(?:==|!=|~=|>=|<=|>|<)|[?*|]|\s+-\s+")


def _lookup(document: Any, selector: str) -> Any:
    value = document
    for part in selector.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(selector)
        value = value[part]
    return value


def _load_structured(path: Path, format_name: str) -> Any:
    text = path.read_text(encoding="utf-8")
    if format_name == "json":
        return json.loads(text)
    return yaml.safe_load(text)


def _is_non_exact_version(version: str) -> bool:
    """Reject moving channels, ranges, and wildcards while allowing exact opaque build ids."""
    stripped = version.strip()
    return not stripped or _RANGE_SYNTAX.search(stripped) is not None or _NON_EXACT_VERSION.search(stripped) is not None


def validate_claims(path: Path, *, repository_root: Path = ROOT) -> list[str]:
    root = repository_root.resolve(strict=True)
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        return [f"operational claims could not be loaded: {exc}"]
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    schema_findings = [
        f"schema: {'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(
            Draft202012Validator(schema).iter_errors(document), key=lambda item: list(item.absolute_path)
        )
    ]
    if schema_findings:
        return schema_findings
    assert isinstance(document, dict)
    claims = document["claims"]
    assert isinstance(claims, list)
    findings: list[str] = []
    seen: set[str] = set()
    for claim in claims:
        assert isinstance(claim, dict)
        claim_id = str(claim["id"])
        if claim_id in seen:
            findings.append(f"{claim_id}: duplicate claim id")
        seen.add(claim_id)
        if claim["kind"] == "configuration-state":
            source = claim["canonical_source"]
            assert isinstance(source, dict)
            try:
                source_path = confined_regular_file(root, str(source["path"]))
                value = _lookup(_load_structured(source_path, str(source["format"])), str(source["selector"]))
            except (OSError, UnicodeDecodeError, ValueError, KeyError, json.JSONDecodeError, yaml.YAMLError) as exc:
                findings.append(f"{claim_id}: canonical configuration could not be resolved: {exc}")
                continue
            if value != claim["expected"]:
                findings.append(
                    f"{claim_id}: canonical configuration drifted; expected {claim['expected']!r}, observed {value!r}"
                )
            continue

        subject = claim["subject"]
        evidence = claim["probe_evidence"]
        assert isinstance(subject, dict) and isinstance(evidence, dict)
        version = str(subject["version"])
        if _is_non_exact_version(version):
            findings.append(f"{claim_id}: runtime capability claims require one exact observed product/build version")
        try:
            evidence_path = confined_regular_file(root, str(evidence["path"]))
            observation = json.loads(evidence_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            findings.append(f"{claim_id}: runtime probe evidence could not be loaded: {exc}")
            continue
        if not isinstance(observation, dict) or observation.get("format") != "ai-skills-runtime-probe-observation":
            findings.append(f"{claim_id}: runtime probe evidence has an unsupported format")
            continue
        if observation.get("subject") != subject:
            findings.append(f"{claim_id}: runtime probe subject/version does not match the durable claim")
        if observation.get("argv") != evidence["argv"]:
            findings.append(f"{claim_id}: runtime probe argv does not match the durable claim")
        if observation.get("fresh_context") is not True or evidence["fresh_context"] is not True:
            findings.append(f"{claim_id}: runtime capability evidence must come from a fresh context/session")
        if observation.get("observed") != claim["expected"]:
            findings.append(
                f"{claim_id}: runtime capability drifted; expected {claim['expected']!r}, "
                f"observed {observation.get('observed')!r}"
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("claims", type=Path, nargs="?", default=Path("operational-claims.yaml"))
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    findings = validate_claims(args.claims, repository_root=args.repository_root)
    for finding in findings:
        print(f"ERROR: {finding}")
    print(f"operational claim findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
