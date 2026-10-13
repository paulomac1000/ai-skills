"""Read-only semantic-preservation audit of a pinned skill refactor ledger.

This verifies declared invariants and route reachability, NOT stochastic model
behavior.  A candidate-authored ledger cannot certify semantic equivalence.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


MATERIAL = {"trigger", "authority", "safety_stop", "exception", "recovery", "completion", "evidence", "precedence"}
DISPOSITIONS = {"PRESERVE", "MOVE", "DEDUPLICATE", "REPLACE_BY_CANONICAL_OWNER", "REMOVE_WITH_REASON"}


def assess(baseline: dict[str, Any], ledger: dict[str, Any], candidate: Path) -> dict[str, Any]:
    """Fail a missing required behavior even when the package's structural audit passes."""
    findings: list[str] = []
    baseline_rules = baseline.get("required_behaviors")
    decisions = ledger.get("decisions")
    if not isinstance(baseline_rules, list) or not isinstance(decisions, list):
        return {"structural": "FAILED", "behavior": "BEHAVIOR_NOT_VERIFIED", "findings": ["invalid_ledger"]}
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
    result = assess(json.loads(args.baseline.read_text()), json.loads(args.ledger.read_text()), args.candidate)
    print(json.dumps(result, indent=2))
    return 1 if result["structural"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())