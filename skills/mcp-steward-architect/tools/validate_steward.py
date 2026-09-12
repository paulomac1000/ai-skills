#!/usr/bin/env python3
"""Validate MCP Steward profiles and durable control-plane records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "contracts"
_SCHEMA_FILES = {
    "profile": "steward-profile.schema.json",
    "job": "steward-job.schema.json",
    "receipt": "external-operation-receipt.schema.json",
    "handoff": "steward-handoff.schema.json",
    "lineage": "steward-lineage.schema.json",
    "completion": "steward-completion.schema.json",
    "upstream": "upstream-capability.schema.json",
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
    errors = sorted(
        Draft202012Validator(
            _schema(kind),
            format_checker=FormatChecker(),
        ).iter_errors(value),
        key=lambda item: tuple(item.absolute_path),
    )
    findings = [f"schema:{'.'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}" for error in errors]
    if errors or not isinstance(value, dict):
        return findings

    if kind == "profile":
        findings.extend(_profile_findings(value))
    elif kind == "job":
        findings.extend(_job_findings(value))
    elif kind == "receipt":
        findings.extend(_receipt_findings(value))
    elif kind == "handoff":
        findings.extend(_handoff_findings(value))
    elif kind == "upstream":
        findings.extend(_upstream_findings(value))
    elif kind == "lineage":
        findings.extend(_lineage_findings(value))
    elif kind == "completion":
        findings.extend(_completion_findings(value))
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
    required_dimensions = set(value["subject_identity"]["required_dimensions"])
    freshness_dimensions = set(value["subject_identity"]["freshness_dimensions"])
    unknown_freshness = sorted(freshness_dimensions - required_dimensions)
    if unknown_freshness:
        findings.append(
            "subject_identity: freshness dimensions must also be required dimensions: " + ", ".join(unknown_freshness)
        )
    obligation_ids = [item["id"] for item in value["completion"]["obligations"]]
    duplicate_obligations = sorted(item for item in set(obligation_ids) if obligation_ids.count(item) > 1)
    if duplicate_obligations:
        findings.append("completion: duplicate obligation ids: " + ", ".join(duplicate_obligations))
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
    if value["state"] == "reserved" and delivery != "not-delivered":
        findings.append("receipt: reserved operation cannot claim delivery")
    if value["state"] == "reserved" and retry != "forbidden":
        findings.append("receipt: reserved operation cannot be retry-eligible")
    if delivery == "delivery-unknown" and value.get("nextRetryAt") is not None:
        findings.append("receipt: delivery-unknown cannot schedule retry before reconciliation")
    return findings


def _handoff_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    status = value["status"]
    if status in {"failed", "cancelled", "blocked", "superseded"} and value["actionable"]:
        findings.append(f"handoff: {status} handoff cannot be actionable")
    if status == "completed" and value["gaps"]:
        findings.append("handoff: completed handoff cannot retain unresolved gaps")
    if status == "completed-with-gaps" and not value["gaps"]:
        findings.append("handoff: completed-with-gaps requires at least one gap")
    if status in {"completed", "completed-with-gaps"} and value.get("outcome") is None:
        findings.append("handoff: completed handoff requires a domain outcome")
    return findings


def _upstream_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    if value["interaction"] == "stateful":
        recoverable = value["recovery"] in {
            "replay-safe",
            "status-by-handle",
            "resume-by-handle",
        }
        reconcilable = value["reconciliation"]["ambiguous_delivery"] != "unsupported"
        if not recoverable or not reconcilable:
            findings.append("upstream: stateful capability requires recovery and ambiguous-delivery reconciliation")
    if value["delivery"] == "durable-async":
        if value["recovery"] not in {"status-by-handle", "resume-by-handle"}:
            findings.append("upstream: durable-async capability requires status/resume by handle")
        if value["progress"] == "none":
            findings.append("upstream: durable-async capability requires progress semantics")
    return findings


def _lineage_findings(value: dict[str, Any]) -> list[str]:
    if value["currentJobId"] in value["supersededJobIds"]:
        return ["lineage: current job cannot also be superseded"]
    return []


def _completion_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    obligations = value["obligations"]
    obligation_ids = [item["id"] for item in obligations]
    duplicates = sorted(item for item in set(obligation_ids) if obligation_ids.count(item) > 1)
    if duplicates:
        findings.append("completion: duplicate obligation ids: " + ", ".join(duplicates))
    for obligation in obligations:
        location = f"completion: obligation {obligation['id']}"
        state = obligation["state"]
        if state == "satisfied" and not obligation["evidenceRefs"]:
            findings.append(f"{location} satisfied without evidence")
        if state == "not-applicable" and not obligation.get("rationale"):
            findings.append(f"{location} not-applicable without rationale")
        if state == "waived" and not obligation.get("authorityRef"):
            findings.append(f"{location} waived without authority")
    unresolved = any(item["state"] == "unsatisfied" for item in obligations)
    if value["disposition"] == "eligible" and unresolved:
        findings.append("completion: eligible disposition has unsatisfied obligations")
    if value["disposition"] == "eligible" and value["ambiguousOperationRefs"]:
        findings.append("completion: eligible disposition has ambiguous operations")
    return findings


def validate_handoff_current(
    value: dict[str, Any],
    *,
    current_job_id: str,
    current_generation: int,
    current_subject: dict[str, Any],
) -> list[str]:
    findings = validate_document("handoff", value)
    if findings:
        return findings
    if value["actionable"] and (value["jobId"] != current_job_id or value["generation"] != current_generation):
        findings.append("handoff: stale job/generation cannot be actionable")
    if value["actionable"] and value["subject"] != current_subject:
        findings.append("handoff: stale subject identity cannot be actionable")
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
