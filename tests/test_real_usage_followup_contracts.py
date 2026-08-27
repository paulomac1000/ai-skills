"""Fail-closed regressions for field feedback and its review follow-ups."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from contracts.mcp_public_contract import compare_contracts
from contracts.rule_applicability import RuleContext, project_applicability
from contracts.validate_consumer_feedback import validate_registry
from contracts.validate_deployment_observation import validate_observation
from contracts.validate_operational_claims import validate_claims

ROOT = Path(__file__).resolve().parents[1]


def _contract(version: str) -> dict:
    return {
        "format": "ai-skills-mcp-public-contract",
        "schema_version": 1,
        "source_revision": "a" * 40,
        "artifact": {"kind": "wheel", "identity": "sample.whl", "digest": "sha256:" + "b" * 64},
        "server": {"name": "sample", "version": version},
        "sdk": {"profile": "python-official-mcp", "version": "2.0.0"},
        "transports": ["stdio"],
        "authentication": {"required": False, "mechanism": "none", "target_selection": "fixed"},
        "tools": [
            {
                "name": "read",
                "version": "1.0.0",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "nested": {
                            "type": "object",
                            "required": ["b", "a"],
                            "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
                        }
                    },
                    "required": [],
                },
                "output_schema": {"type": "object", "properties": {}, "required": []},
                "error_contract": ["INTERNAL_ERROR"],
                "pagination": "none",
                "retry_semantics": "none",
                "target_selection": "fixed",
            }
        ],
    }


def test_nested_required_order_is_not_a_breaking_change_and_prerelease_cannot_close_release_gate() -> None:
    baseline = _contract("1.0.0")
    candidate = _contract("1.0.1")
    candidate["tools"][0]["input_schema"]["properties"]["nested"]["required"] = ["a", "b"]
    result = compare_contracts(baseline, candidate)
    assert result.required_bump == "none"
    assert result.version_satisfies is True
    candidate["server"]["version"] = "1.0.1-rc.1"
    assert compare_contracts(baseline, candidate).version_satisfies is False


def test_applicability_rejects_non_list_and_non_object_child_catalogs() -> None:
    parents = {"skills": {"demo": {"rules": []}}}
    context = RuleContext("L1")
    with pytest.raises(ValueError, match="must be a list"):
        project_applicability(parents, {"controls": "not-a-list"}, "demo", context)
    with pytest.raises(ValueError, match="must be an object"):
        project_applicability(parents, {"controls": ["not-an-object"]}, "demo", context)


def test_deployment_observation_rejects_naive_and_reversed_times(tmp_path: Path) -> None:
    base = {
        "format": "ai-skills-deployment-observation",
        "schema_version": 1,
        "source_revision": "a" * 40,
        "artifact": {"identity": "sample.whl", "digest": "sha256:" + "b" * 64},
        "deployment_identity": "local-test",
        "environment_class": "live-test",
        "command": {"argv": ["probe"], "working_directory": "."},
        "result": {
            "status": "passed",
            "result_digest": "sha256:" + "c" * 64,
            "started_at": "2026-08-13T01:00:00Z",
            "completed_at": "2026-08-13T01:01:00Z",
        },
        "actor": {"kind": "runner", "identity": "ci"},
    }
    path = tmp_path / "observation.yaml"
    path.write_text(yaml.safe_dump(base), encoding="utf-8")
    assert validate_observation(path) == []
    base["result"]["completed_at"] = "2026-08-13T00:59:00Z"
    path.write_text(yaml.safe_dump(base), encoding="utf-8")
    assert any("must not precede" in finding for finding in validate_observation(path))
    base["result"]["started_at"] = "2026-08-13T01:00:00"
    base["result"]["completed_at"] = "2026-08-13T01:01:00Z"
    path.write_text(yaml.safe_dump(base), encoding="utf-8")
    assert any("timezone offset" in finding for finding in validate_observation(path))


def test_field_feedback_validators_cover_schema_and_load_failures(tmp_path: Path) -> None:
    bad_registry = tmp_path / "registry.yaml"
    bad_registry.write_text("schema_version: 1\nincidents: []\n", encoding="utf-8")
    assert any("schema:" in finding for finding in validate_registry(bad_registry, repository_root=ROOT))
    missing_claims = tmp_path / "missing-claims.yaml"
    missing_claims.write_text("schema_version: 1\nclaims: []\n", encoding="utf-8")
    assert any("schema:" in finding for finding in validate_claims(missing_claims, repository_root=tmp_path))


def test_test_case_schemas_reject_parent_traversal() -> None:
    for name, node_path in (
        ("atomic-claim-report.schema.json", ("properties", "checks", "items", "properties", "test_case")),
        ("adoption-assessment.schema.json", ("$defs", "verification", "properties", "test_case")),
    ):
        schema = json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))
        node = schema
        for key in node_path:
            node = node[key]
        import re

        assert re.fullmatch(node["pattern"], "tests/unit/test_ok.py::test_case")
        assert not re.fullmatch(node["pattern"], "tests/../secrets/x.py::test_case")
