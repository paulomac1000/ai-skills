"""Executable contract for lightweight local conformance reports."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
if str(CONTRACTS) not in sys.path:
    sys.path.insert(0, str(CONTRACTS))

from rule_applicability import RuleContext, expected_rules  # noqa: E402
from validate_conformance import validate  # noqa: E402


def _repository(tmp_path: Path) -> tuple[Path, dict[str, Any], list[dict[str, Any]]]:
    root = tmp_path / "repository"
    skill = root / "skills" / "mcp-server-architect"
    skill.mkdir(parents=True)
    (skill / "manifest.yaml").write_text("version: 1.2.0\n", encoding="utf-8")
    (root / "implementation.py").write_text("class ContractMarker: pass\n", encoding="utf-8")
    (root / "evidence.xml").write_text("<testsuite/>\n", encoding="utf-8")
    catalog = yaml.safe_load((CONTRACTS / "rule-catalog.yaml").read_text(encoding="utf-8"))
    rules = expected_rules(catalog, "mcp-server-architect", RuleContext("L1"))
    return root, catalog, rules


def _report(rules: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "report_id": "local-conformance-001",
        "generated_at": "2026-08-06T08:00:00Z",
        "repository": {"name": "owner/repository", "revision": "a" * 40},
        "skill": {"name": "mcp-server-architect", "version": "1.2.0"},
        "context": {"target_level": "L1", "profiles": [], "capabilities": []},
        "checks": [
            {
                "rule_id": rule["id"],
                "status": "passed",
                "implementation": [
                    {"path": "implementation.py", "symbol": "ContractMarker"}
                ],
                "command": "python -m pytest",
                "result": "passed",
                "evidence_types": rule["required_evidence"],
                "evidence_paths": ["evidence.xml"],
            }
            for rule in rules
        ],
        "residual_risks": [],
    }


def _validate(tmp_path: Path, report: dict[str, Any]) -> list[str]:
    root, _catalog, _rules = _repository(tmp_path)
    report_path = root / "conformance.yaml"
    report_path.write_text(yaml.safe_dump(report, sort_keys=False), encoding="utf-8")
    return validate(report_path, root, CONTRACTS / "rule-catalog.yaml")


def test_valid_local_conformance_needs_no_provider_identifiers(tmp_path: Path) -> None:
    root, _catalog, rules = _repository(tmp_path)
    report = _report(rules)
    report_path = root / "conformance.yaml"
    report_path.write_text(yaml.safe_dump(report, sort_keys=False), encoding="utf-8")
    assert validate(report_path, root, CONTRACTS / "rule-catalog.yaml") == []
    serialized = report_path.read_text(encoding="utf-8")
    for forbidden in ("run_id", "job_id", "artifact_id", "acceptance_authority"):
        assert forbidden not in serialized


def test_missing_applicable_rule_fails_closed(tmp_path: Path) -> None:
    root, _catalog, rules = _repository(tmp_path)
    report = _report(rules)
    report["checks"].pop()
    report_path = root / "conformance.yaml"
    report_path.write_text(yaml.safe_dump(report, sort_keys=False), encoding="utf-8")
    errors = validate(report_path, root, CONTRACTS / "rule-catalog.yaml")
    assert any("missing applicable rules" in error for error in errors)


def test_required_evidence_type_is_enforced(tmp_path: Path) -> None:
    root, _catalog, rules = _repository(tmp_path)
    report = _report(rules)
    report["checks"][0]["evidence_types"] = []
    report_path = root / "conformance.yaml"
    report_path.write_text(yaml.safe_dump(report, sort_keys=False), encoding="utf-8")
    errors = validate(report_path, root, CONTRACTS / "rule-catalog.yaml")
    assert any("missing" in error and "evidence_types" in error for error in errors)


def test_symlink_evidence_is_rejected(tmp_path: Path) -> None:
    root, _catalog, rules = _repository(tmp_path)
    target = root / "outside.xml"
    target.write_text("<testsuite/>\n", encoding="utf-8")
    link = root / "linked.xml"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    report = _report(rules)
    report["checks"][0]["evidence_paths"] = ["linked.xml"]
    report_path = root / "conformance.yaml"
    report_path.write_text(yaml.safe_dump(report, sort_keys=False), encoding="utf-8")
    errors = validate(report_path, root, CONTRACTS / "rule-catalog.yaml")
    assert any("must not contain symlinks" in error for error in errors)


def test_skill_name_cannot_escape_repository(tmp_path: Path) -> None:
    root, _catalog, rules = _repository(tmp_path)
    report = _report(rules)
    report["skill"]["name"] = "../../outside"
    report_path = root / "conformance.yaml"
    report_path.write_text(yaml.safe_dump(report, sort_keys=False), encoding="utf-8")
    errors = validate(report_path, root, CONTRACTS / "rule-catalog.yaml")
    assert "skill.name: must be a safe skill identifier" in errors


def test_unknown_top_level_fields_fail_closed(tmp_path: Path) -> None:
    root, _catalog, rules = _repository(tmp_path)
    report = _report(rules)
    report["provider_run_id"] = 123
    report_path = root / "conformance.yaml"
    report_path.write_text(yaml.safe_dump(report, sort_keys=False), encoding="utf-8")
    errors = validate(report_path, root, CONTRACTS / "rule-catalog.yaml")
    assert any("unsupported fields" in error for error in errors)
