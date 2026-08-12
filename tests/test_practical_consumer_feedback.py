"""Executable regressions derived from real downstream migration failures."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def inspector():
    return load_module(
        "consumer_inspector",
        ROOT / "skills/mcp-server-architect/tools/inspect_existing_project.py",
    )


def test_inspector_routes_fastmcp_and_requires_upstream_discovery(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """[project]\nname = "sample"\nversion = "3.2.1"\ndependencies = ["fastmcp==3.4.6", "httpx==0.28.1"]\n[tool.pytest.ini_options]\naddopts = '-m "not external"'\n""",
        encoding="utf-8",
    )
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/ci.yml").write_text("name: CI\n", encoding="utf-8")
    (tmp_path / "tests/external").mkdir(parents=True)
    (tmp_path / "tests/external/test_live.py").write_text(
        "import pytest\npytestmark = pytest.mark.external\n", encoding="utf-8"
    )
    (tmp_path / "server.py").write_text("# stdio streamable_http create_record delete_record\n", encoding="utf-8")

    result = inspector().inspect_repository(tmp_path)
    assert result["facts"]["sdk_profile"] == "python-fastmcp-package"
    assert result["facts"]["external_tests_default_excluded"] is True
    assert result["facts"]["transports"] == {
        "stdio": True,
        "streamable_http": True,
        "legacy_http_sse_signal": False,
    }
    assert result["plan"]["upstream_contract"] == "required"
    assert result["plan"]["live_backend_safety"] == "needs-policy"
    assert "references/python-fastmcp-package.md" in result["required_read_set"]


def test_inspector_recognizes_machine_readable_discovery_artifacts(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="sample"\nversion="2.0.0"\ndependencies=["mcp==2.0.0", "requests==2.34.2"]\n',
        encoding="utf-8",
    )
    (tmp_path / "upstream-contract.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    result = inspector().inspect_repository(tmp_path)
    assert result["facts"]["sdk_profile"] == "python-official-mcp"
    assert result["plan"]["upstream_contract"] == "verified"


def test_upstream_contract_rejects_inference_and_embedded_secret_keys(tmp_path: Path) -> None:
    validator = load_module("upstream_contract_validator", ROOT / "contracts/validate_upstream_contract.py")
    contract = {
        "schema_version": 1,
        "upstream": {"name": "legacy-api", "classification": "legacy"},
        "observations": [
            {
                "operation": "create-item",
                "method": "POST",
                "endpoint": "/items",
                "request_encoding": "form",
                "success_statuses": [201],
                "response_body": "empty",
                "credential_placement": "query",
                "confidence": "inferred",
                "evidence": ["controlled-probe-1"],
            }
        ],
    }
    path = tmp_path / "upstream-contract.yaml"
    path.write_text(yaml.safe_dump(contract), encoding="utf-8")
    assert any("inferred" in finding for finding in validator.validate_contract(path, require_observed=True))
    contract["observations"][0]["confidence"] = "observed"
    contract["observations"][0]["api_key"] = "should-never-be-recorded"
    path.write_text(yaml.safe_dump(contract), encoding="utf-8")
    assert validator.validate_contract(path)


def test_live_backend_policy_requires_two_opt_ins_and_reconciliation(tmp_path: Path) -> None:
    validator = load_module(
        "live_policy_validator",
        ROOT / "contracts/validate_live_backend_test_policy.py",
    )
    valid = {
        "schema_version": 1,
        "default_execution": "excluded",
        "mutations": {
            "enabled_by_default": False,
            "independent_opt_ins": 2,
            "credential_access": "after-opt-in",
            "unique_namespace": True,
            "cleanup": {
                "capture_created_ids": True,
                "reconcile_by_marker": True,
                "report_unreconciled": True,
            },
        },
    }
    path = tmp_path / "live-backend-test-policy.yaml"
    path.write_text(yaml.safe_dump(valid), encoding="utf-8")
    assert validator.validate_policy(path) == []
    valid["mutations"]["independent_opt_ins"] = 1
    path.write_text(yaml.safe_dump(valid), encoding="utf-8")
    assert validator.validate_policy(path)


def test_real_consumer_canaries_are_immutable_and_source_only() -> None:
    catalog = yaml.safe_load((ROOT / "contracts/consumer-canaries.yaml").read_text(encoding="utf-8"))
    assert catalog["schema_version"] == 1
    assert len(catalog["canaries"]) >= 2
    for canary in catalog["canaries"]:
        assert len(canary["revision"]) == 40
        int(canary["revision"], 16)
        assert canary["expected"]["facts.external_upstream"] is True
    checker = (ROOT / "skills/mcp-server-architect/tools/check_consumer_canaries.py").read_text(encoding="utf-8")
    assert "inspect_repository" in checker
    assert "pytest" not in checker
    assert "subprocess.run" in checker


def test_atomic_controls_capture_practical_migration_failures() -> None:
    catalog = yaml.safe_load((ROOT / "contracts/atomic-claim-catalog.yaml").read_text(encoding="utf-8"))
    controls = {item["id"]: item for item in catalog["controls"]}
    assert controls["mcp.testing.live-backend-safety"]["applies_when"]["profiles_any"] == ["live-backend"]
    parity = controls["mcp.authorization.transport-parity"]
    assert parity["applies_when"]["profiles_all"] == ["local-stdio", "remote-http"]
    assert set(parity["applies_when"]["capabilities_any"]) == {"write", "destructive"}
    upstream = controls["mcp.upstream.contract-observed"]
    assert upstream["parent_rule_id"] == "mcp.verification.layered"


def test_consumer_discovery_document_is_valid_json(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="x"\nversion="1.0.0"\ndependencies=[]\n', encoding="utf-8"
    )
    document = inspector().inspect_repository(tmp_path)
    assert json.loads(json.dumps(document))["format"] == "ai-skills-adoption-discovery"
