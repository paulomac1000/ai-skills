#!/usr/bin/env python3
"""Validate MCP Steward profiles and durable control-plane records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "contracts"
_SCHEMA_FILES = {
    "profile": "steward-profile.schema.json",
    "job": "steward-job.schema.json",
    "receipt": "external-operation-receipt.schema.json",
    "handoff": "steward-handoff.schema.json",
}


def _load(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.casefold() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def _schema(kind: str) -> dict[str, Any]:
    value = json.loads((CONTRACTS / _SCHEMA_FILES[kind]).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(value)
    return value


def validate_document(kind: str, value: Any) -> list[str]:
    if kind not in _SCHEMA_FILES:
        raise ValueError(f"unknown document kind: {kind}")
    errors = sorted(Draft202012Validator(_schema(kind)).iter_errors(value), key=lambda item: tuple(item.absolute_path))
    findings = [f"schema:{'.'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}" for error in errors]
    if errors or not isinstance(value, dict):
        return findings

    if kind == "profile":
        findings.extend(_profile_findings(value))
    elif kind == "job":
        findings.extend(_job_findings(value))
    elif kind == "receipt":
        findings.extend(_receipt_findings(value))
    return findings


def _profile_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    authority = value["authority"]
    owned = set(authority["owns"])
    never = set(authority["never_claims"])
    overlap = sorted(owned & never)
    if overlap:
        findings.append("authority: owns and never_claims overlap: " + ", ".join(overlap))
    durability = value["durability"]
    if durability["profile"] != "constrained-file" and not durability["transactional_store_required"]:
        findings.append("durability: durable profiles require a transactional store")
    fallback = value["credentials"]["fallback"]
    if fallback["enabled"] and (not fallback["preserve_principal_scope"] or not fallback["preserve_target"]):
        findings.append("credentials: fallback must preserve principal/scope and target")
    return findings


def _job_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    terminal = {"completed", "completed-with-gaps", "failed", "cancelled", "superseded"}
    if value["status"] in terminal and value.get("lease") is not None:
        findings.append("job: terminal state must not retain an active lease")
    if value["status"] == "superseded" and value.get("domainOutcome") not in {None, "superseded"}:
        findings.append("job: superseded work cannot carry an actionable domain outcome")
    return findings


def _receipt_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    delivery = value["delivery"]
    retry = value["retryDisposition"]
    if delivery == "delivery-unknown" and retry != "reconcile-first":
        findings.append("receipt: delivery-unknown requires retryDisposition=reconcile-first")
    if delivery == "not-delivered" and value.get("remoteHandle"):
        findings.append("receipt: not-delivered cannot claim a remote handle")
    return findings


def validate_handoff_current(value: dict[str, Any], *, current_job_id: str, current_generation: int) -> list[str]:
    findings = validate_document("handoff", value)
    if findings:
        return findings
    if value["actionable"] and (value["jobId"] != current_job_id or value["generation"] != current_generation):
        findings.append("handoff: stale job/generation cannot be actionable")
    if value["status"] == "superseded" and value["actionable"]:
        findings.append("handoff: superseded handoff cannot be actionable")
    return findings


def validate_path(kind: str, path: Path) -> list[str]:
    return validate_document(kind, _load(path))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=sorted(_SCHEMA_FILES))
    parser.add_argument("path", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    findings = validate_path(args.kind, args.path)
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
