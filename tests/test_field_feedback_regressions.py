"""Regressions promoted from observed instruction and local-gate failures."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from contracts.validate_consumer_feedback import validate_registry
from contracts.validate_operational_claims import validate_claims
from scripts.ci_environment import build_clean_environment, configured_passthrough

ROOT = Path(__file__).resolve().parents[1]


def test_clean_environment_strips_session_state_and_requires_explicit_passthrough() -> None:
    source = {
        "PATH": "/tools",
        "HOME": "/home/tester",
        "HTTP_PROXY": "http://proxy.example",
        "LC_ALL": "C.UTF-8",
        "OPENCODE_STACK_LAUNCHED": "1",
        "PROJECT_TEST_MODE": "inherited-session",
        "AI_SKILLS_CI_PASSTHROUGH": "PROJECT_TEST_MODE",
    }
    assert configured_passthrough(source) == ("PROJECT_TEST_MODE",)
    clean = build_clean_environment(source)
    assert clean["PATH"] == "/tools"
    assert clean["HTTP_PROXY"] == "http://proxy.example"
    assert clean["LC_ALL"] == "C.UTF-8"
    assert "OPENCODE_STACK_LAUNCHED" not in clean
    assert "PROJECT_TEST_MODE" not in clean
    explicit = build_clean_environment(source, extra_allowed=configured_passthrough(source))
    assert explicit["PROJECT_TEST_MODE"] == "inherited-session"
    assert "AI_SKILLS_CI_PASSTHROUGH" not in explicit


def test_configuration_state_claim_fails_when_canonical_config_drifts(tmp_path: Path) -> None:
    (tmp_path / "runtime.json").write_text(json.dumps({"services": {"home": {"enabled": False}}}), encoding="utf-8")
    claims = {
        "schema_version": 1,
        "claims": [
            {
                "id": "home-service-enabled",
                "kind": "configuration-state",
                "canonical_source": {"path": "runtime.json", "format": "json", "selector": "services.home.enabled"},
                "expected": False,
            }
        ],
    }
    path = tmp_path / "operational-claims.yaml"
    path.write_text(yaml.safe_dump(claims), encoding="utf-8")
    assert validate_claims(path, repository_root=tmp_path) == []
    (tmp_path / "runtime.json").write_text(json.dumps({"services": {"home": {"enabled": True}}}), encoding="utf-8")
    assert any("canonical configuration drifted" in item for item in validate_claims(path, repository_root=tmp_path))


def test_runtime_capability_claim_is_bound_to_exact_version_argv_and_fresh_context(tmp_path: Path) -> None:
    observation = {
        "format": "ai-skills-runtime-probe-observation",
        "subject": {"name": "agent-runtime", "version": "1.18.6"},
        "argv": ["agent-runtime", "probe", "self-enable"],
        "fresh_context": True,
        "observed": {"self_enable": True},
    }
    (tmp_path / "probe.json").write_text(json.dumps(observation), encoding="utf-8")
    claims = {
        "schema_version": 1,
        "claims": [
            {
                "id": "runtime-self-enable",
                "kind": "runtime-capability",
                "subject": {"name": "agent-runtime", "version": "1.18.6"},
                "probe_evidence": {
                    "path": "probe.json",
                    "argv": ["agent-runtime", "probe", "self-enable"],
                    "fresh_context": True,
                },
                "expected": {"self_enable": True},
            }
        ],
    }
    path = tmp_path / "operational-claims.yaml"
    path.write_text(yaml.safe_dump(claims), encoding="utf-8")
    assert validate_claims(path, repository_root=tmp_path) == []
    observation["fresh_context"] = False
    (tmp_path / "probe.json").write_text(json.dumps(observation), encoding="utf-8")
    assert any("fresh context/session" in item for item in validate_claims(path, repository_root=tmp_path))


def test_operational_claims_reject_stale_runtime_identity_and_probe_shape(tmp_path: Path) -> None:
    observation = {
        "format": "ai-skills-runtime-probe-observation",
        "subject": {"name": "agent-runtime", "version": "1.18.7"},
        "argv": ["agent-runtime", "probe", "different"],
        "fresh_context": True,
        "observed": {"self_enable": False},
    }
    (tmp_path / "probe.json").write_text(json.dumps(observation), encoding="utf-8")
    claims = {
        "schema_version": 1,
        "claims": [
            {
                "id": "runtime-self-enable",
                "kind": "runtime-capability",
                "subject": {"name": "agent-runtime", "version": "latest"},
                "probe_evidence": {
                    "path": "probe.json",
                    "argv": ["agent-runtime", "probe", "self-enable"],
                    "fresh_context": True,
                },
                "expected": {"self_enable": True},
            }
        ],
    }
    path = tmp_path / "operational-claims.yaml"
    path.write_text(yaml.safe_dump(claims), encoding="utf-8")
    findings = validate_claims(path, repository_root=tmp_path)
    assert any("exact observed product/build version" in item for item in findings)
    assert any("subject/version" in item for item in findings)
    assert any("argv" in item for item in findings)
    assert any("runtime capability drifted" in item for item in findings)


def test_real_consumer_canaries_state_their_proof_boundary() -> None:
    catalog = yaml.safe_load((ROOT / "contracts/consumer-canaries.yaml").read_text(encoding="utf-8"))
    assert catalog["canaries"]
    assert {canary["proof_level"] for canary in catalog["canaries"]} == {"source-inspection"}
    checker = (ROOT / "skills/mcp-server-architect/tools/check_consumer_canaries.py").read_text(encoding="utf-8")
    assert "proof_level" in checker
    assert "source-inspection" in checker


def test_consumer_feedback_registry_fails_closed_on_stale_owner_and_selector(tmp_path: Path) -> None:
    (tmp_path / "contracts").mkdir()
    (tmp_path / "skills/example").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "contracts/consumer-canaries.yaml").write_text(
        "schema_version: 1\ncanaries:\n- id: known-canary\n", encoding="utf-8"
    )
    (tmp_path / "skills/example/guide.md").write_text("# Guide\n\n## Current owner\n", encoding="utf-8")
    (tmp_path / "tests/test_example.py").write_text("def test_existing():\n    assert True\n", encoding="utf-8")
    registry = {
        "schema_version": 1,
        "incidents": [
            {
                "id": "field.stale-link",
                "source_kind": "external-consumer",
                "source_canaries": ["missing-canary"],
                "failure_mode": "A real consumer exposed a concrete stale contract link during use.",
                "generalized_invariant": "Every promoted lesson remains bound to an existing owner and executable regression.",
                "canonical_owner": "skills/example/guide.md#missing-owner",
                "regression_selectors": ["tests/test_example.py::test_missing"],
                "status": "implemented",
            }
        ],
    }
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump(registry), encoding="utf-8")
    findings = validate_registry(path, repository_root=tmp_path)
    assert any("unknown source canary" in item for item in findings)
    assert any("canonical owner anchor" in item for item in findings)
    assert any("does not name an existing test" in item for item in findings)


def test_consumer_feedback_registry_points_to_real_tests_and_owned_rules() -> None:
    assert validate_registry(ROOT / "contracts/consumer-feedback.yaml", repository_root=ROOT) == []
