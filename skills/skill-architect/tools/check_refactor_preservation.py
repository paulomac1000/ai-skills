"""Read-only semantic-preservation audit of a pinned skill refactor ledger.

This verifies declared invariants and route reachability, NOT stochastic model
behavior.  A candidate-authored ledger cannot certify semantic equivalence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

MATERIAL = {"trigger", "authority", "safety_stop", "exception", "recovery", "completion", "evidence", "precedence"}
DISPOSITIONS = {"PRESERVE", "MOVE", "DEDUPLICATE", "REPLACE_BY_CANONICAL_OWNER", "REMOVE_WITH_REASON"}
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _content_bindings(baseline: dict[str, Any], ledger: dict[str, Any], candidate: Path) -> list[str]:
    findings: list[str] = []
    revision = baseline.get("revision")
    if not isinstance(revision, str) or not SHA40.fullmatch(revision):
        findings.append("invalid_baseline_revision")
    digest = "sha256:" + hashlib.sha256(_canonical_json(baseline)).hexdigest()
    if ledger.get("baseline_sha256") != digest:
        findings.append("baseline_content_mismatch")
    bindings = ledger.get("candidate_files")
    if not isinstance(bindings, dict) or not bindings:
        return findings + ["candidate_files_missing"]
    root = candidate.resolve()
    for rel, expected in bindings.items():
        if (
            not isinstance(rel, str)
            or not rel
            or Path(rel).is_absolute()
            or ".." in Path(rel).parts
            or not isinstance(expected, str)
            or not SHA40.fullmatch(expected)
        ):
            findings.append("invalid_candidate_binding")
            continue
        path = (candidate / rel).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            findings.append("candidate_file_missing:" + rel)
        elif path.stat().st_size > 1_000_000:
            findings.append("candidate_file_too_large:" + rel)
        elif _git_blob_sha(path.read_bytes()) != expected:
            findings.append("candidate_content_mismatch:" + rel)
    return findings


def assess(baseline: dict[str, Any], ledger: dict[str, Any], candidate: Path) -> dict[str, Any]:
    """Fail a missing required behavior even when the package's structural audit passes."""
    findings: list[str] = _content_bindings(baseline, ledger, candidate)
    baseline_rules = baseline.get("required_behaviors")
    decisions = ledger.get("decisions")
    if not isinstance(baseline_rules, list) or not baseline_rules or not isinstance(decisions, list):
        return {"structural": "FAILED", "behavior": "BEHAVIOR_NOT_VERIFIED", "findings": findings + ["invalid_ledger"]}
    by_id: dict[str, dict[str, Any]] = {}
    for entry in decisions:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            findings.append("invalid_decision")
            continue
        if entry["id"] in by_id:
            findings.append("duplicate_decision:" + entry["id"])
        by_id[entry["id"]] = entry
    for old in baseline_rules:
        if not isinstance(old, dict) or not isinstance(old.get("id"), str):
            findings.append("invalid_baseline_rule")
            continue
        rule_id = old["id"]
        decision = by_id.get(rule_id)
        if decision is None:
            findings.append("missing_required_behavior:" + rule_id)
            continue
        kind = old.get("kind")
        disposition = decision.get("disposition")
        if disposition not in DISPOSITIONS:
            findings.append("invalid_disposition:" + rule_id)
            continue
        if kind in MATERIAL and disposition == "REMOVE_WITH_REASON":
            # Human review and model-backed comparison, not this ledger, may authorize a semantic removal.
            findings.append("required_behavior_removed:" + rule_id)
        if disposition == "REMOVE_WITH_REASON" and not decision.get("reason"):
            findings.append("unexplained_removal:" + rule_id)
        if disposition != "REMOVE_WITH_REASON":
            rel = decision.get("target_path")
            if not isinstance(rel, str) or not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
                findings.append("unsafe_or_missing_owner:" + rule_id)
                continue
            if rel not in ledger.get("candidate_files", {}):
                findings.append("unbound_owner:" + rule_id)
            target = (candidate / rel).resolve()
            root = candidate.resolve()
            if not target.is_relative_to(root) or not target.is_file():
                findings.append("unreachable_owner:" + rule_id)
                continue
            required_anchor = decision.get("target_anchor")
            if not isinstance(required_anchor, str) or not required_anchor:
                findings.append("missing_target_anchor:" + rule_id)
            elif required_anchor not in target.read_text(encoding="utf-8"):
                findings.append("anchor_not_present:" + rule_id)
            if kind in MATERIAL and not decision.get("negative_case"):
                findings.append("negative_case_missing:" + rule_id)
            if not decision.get("verification"):
                findings.append("verification_missing:" + rule_id)
            if kind in {"trigger", "authority", "safety_stop", "precedence"}:
                pre_load = decision.get("pre_load_path")
                marker = decision.get("pre_load_trigger")
                if not isinstance(pre_load, str) or not isinstance(marker, str) or not marker:
                    findings.append("preload_route_missing:" + rule_id)
                elif Path(pre_load).is_absolute() or ".." in Path(pre_load).parts:
                    findings.append("preload_route_unsafe:" + rule_id)
                else:
                    if pre_load not in ledger.get("candidate_files", {}):
                        findings.append("unbound_preload_route:" + rule_id)
                    route_file = (candidate / pre_load).resolve()
                    if (
                        not route_file.is_relative_to(root)
                        or not route_file.is_file()
                        or marker not in route_file.read_text(encoding="utf-8")
                    ):
                        findings.append("preload_trigger_unreachable:" + rule_id)
    unknown = sorted(set(by_id) - {x.get("id") for x in baseline_rules if isinstance(x, dict)})
    findings.extend("unreviewed_new_rule:" + item for item in unknown)
    # Separate metrics from gate results. No cost metric can override a safety finding.
    return {
        "structural": "FAILED" if findings else "PASS",
        "behavior": "BEHAVIOR_NOT_VERIFIED",
        "findings": findings,
        "baseline_revision": baseline.get("revision"),
        "candidate_revision": ledger.get("candidate_revision"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    try:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
        if not isinstance(baseline, dict) or not isinstance(ledger, dict) or not args.candidate.is_dir():
            raise ValueError("invalid_ledger_or_candidate")
        result = assess(baseline, ledger, args.candidate)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
        result = {
            "structural": "INVALID_INPUT",
            "behavior": "BEHAVIOR_NOT_VERIFIED",
            "findings": ["invalid_input:" + type(exc).__name__],
        }
        print(json.dumps(result))
        return 2
    print(json.dumps(result, indent=2))
    return 1 if result["structural"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
