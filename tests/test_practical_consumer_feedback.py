"""Executable regressions derived from real downstream migration failures."""

from __future__ import annotations

import importlib.util
import json
import re
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


def test_inspector_recognizes_but_does_not_trust_invalid_discovery_artifacts(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="sample"\nversion="2.0.0"\ndependencies=["mcp==2.0.0", "requests==2.34.2"]\n',
        encoding="utf-8",
    )
    (tmp_path / "upstream-contract.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    result = inspector().inspect_repository(tmp_path)
    assert result["facts"]["sdk_profile"] == "python-official-mcp"
    assert result["facts"]["upstream_contract_present"] is True
    assert result["facts"]["upstream_contract_valid"] is False
    assert result["plan"]["upstream_contract"] == "invalid"


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
    assert any("api_key" in finding for finding in validator.validate_contract(path))
    contract["observations"][0].pop("api_key")
    contract["observations"][0]["evidence"] = ["probe api_key=plaintext-secret"]
    path.write_text(yaml.safe_dump(contract), encoding="utf-8")
    assert any("secret values" in finding for finding in validator.validate_contract(path))


def test_live_backend_policy_requires_two_opt_ins_and_reconciliation(tmp_path: Path) -> None:
    validator = load_module(
        "live_policy_validator",
        ROOT / "contracts/validate_live_backend_test_policy.py",
    )
    valid = {
        "schema_version": 1,
        "default_execution": "excluded",
        "mutations": {
            "enabled": True,
            "opt_in_controls": ["RUN_EXTERNAL_TESTS", "ALLOW_REAL_MUTATIONS"],
            "exclusive_disposable_target_required": True,
        },
        "cleanup": {
            "ownership_marker_required": True,
            "preclean_required": True,
            "reconciliation_required": True,
            "postclean_verification_required": True,
        },
    }
    path = tmp_path / "live-backend-test-policy.yaml"
    path.write_text(yaml.safe_dump(valid), encoding="utf-8")
    assert validator.validate_policy(path) == []
    valid["mutations"]["opt_in_controls"] = ["RUN_EXTERNAL_TESTS"]
    path.write_text(yaml.safe_dump(valid), encoding="utf-8")
    assert any("at least two" in finding for finding in validator.validate_policy(path))


def test_contract_capture_rejects_untrusted_probe_shape(tmp_path: Path) -> None:
    capture = load_module(
        "capture_contract",
        ROOT / "skills/mcp-server-architect/tools/capture_mcp_contract.py",
    )
    malformed = tmp_path / "contract.json"
    malformed.write_text(json.dumps({"tools": []}), encoding="utf-8")
    assert any("schema_version" in item for item in capture.validate_capture(json.loads(malformed.read_text())))


def test_protocol_revision_reference_avoids_unverified_repository_claims() -> None:
    manifest = yaml.safe_load((ROOT / "skills/mcp-server-architect/manifest.yaml").read_text(encoding="utf-8"))
    profiles = manifest["protocol"]["sdk_profiles"]
    for profile in profiles.values():
        assert profile["repository_tested_revisions"] == []
        assert profile["current_revision_support"] == "not-claimed"


def test_no_generated_or_documented_fake_external_acceptance() -> None:
    text = (ROOT / "skills/mcp-server-architect/STANDARD.md").read_text(encoding="utf-8")
    assert "provider-backed" in text
    assert "candidate-owned" in text
    assert re.search(r"cannot\s+(?:self-)?approve", text, re.IGNORECASE)
