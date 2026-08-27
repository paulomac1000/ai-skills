"""Regressions for migration semantics learned from practical ai-skills adoption."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
MCP_TOOLS = ROOT / "skills/mcp-server-architect/tools"


def _load(name: str, path: Path, *, extra_path: Path | None = None) -> ModuleType:
    if extra_path is not None and str(extra_path) not in sys.path:
        sys.path.insert(0, str(extra_path))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _live_policy(*, unique_namespace: bool = True) -> dict[str, object]:
    if unique_namespace:
        strategies = ["captured-id", "unique-namespace"]
    else:
        strategies = ["captured-id", "verified-baseline-difference"]
    return {
        "schema_version": 1,
        "default_execution": "excluded",
        "mutations": {
            "enabled_by_default": False,
            "independent_opt_ins": 2,
            "credential_access": "after-opt-in",
            "unique_namespace": unique_namespace,
            "target_identity": {
                "verified_before_mutation": True,
                "exclusive_disposable_environment": True,
                "proof": "sandbox-account-id plus known fixture",
            },
            "cleanup": {
                "capture_created_ids": True,
                "reconcile_by_marker": True,
                "report_unreconciled": True,
                "preclean_after_target_verification": True,
                "strategies": strategies,
            },
        },
    }


def test_live_policy_requires_verified_disposable_target_before_mutation(tmp_path: Path) -> None:
    validator = _load("live_policy_semantics", CONTRACTS / "validate_live_backend_test_policy.py")
    policy = _live_policy()
    path = tmp_path / "live-backend-test-policy.yaml"
    path.write_text(yaml.safe_dump(policy), encoding="utf-8")
    assert validator.validate_policy(path) == []

    mutations = policy["mutations"]
    assert isinstance(mutations, dict)
    mutations.pop("target_identity")
    path.write_text(yaml.safe_dump(policy), encoding="utf-8")
    findings = validator.validate_policy(path)
    assert any("target_identity" in finding and "required property" in finding for finding in findings)
    structural_findings = validator.validate_policy(path, require_safe_mutations=False)
    assert any("target_identity" in finding and "required property" in finding for finding in structural_findings)


def test_live_policy_schema_requires_cleanup_ordering_contract(tmp_path: Path) -> None:
    validator = _load("live_policy_cleanup_schema", CONTRACTS / "validate_live_backend_test_policy.py")
    policy = _live_policy()
    mutations = policy["mutations"]
    assert isinstance(mutations, dict)
    cleanup = mutations["cleanup"]
    assert isinstance(cleanup, dict)
    cleanup.pop("preclean_after_target_verification")
    cleanup.pop("strategies")
    path = tmp_path / "live-backend-test-policy.yaml"
    path.write_text(yaml.safe_dump(policy), encoding="utf-8")

    findings = validator.validate_policy(path, require_safe_mutations=False)
    assert any("preclean_after_target_verification" in finding and "required property" in finding for finding in findings)
    assert any("strategies" in finding and "required property" in finding for finding in findings)


def test_live_policy_requires_baseline_cleanup_without_namespace(tmp_path: Path) -> None:
    validator = _load("live_policy_baseline", CONTRACTS / "validate_live_backend_test_policy.py")
    policy = _live_policy(unique_namespace=False)
    path = tmp_path / "live-backend-test-policy.yaml"
    path.write_text(yaml.safe_dump(policy), encoding="utf-8")
    assert validator.validate_policy(path) == []

    mutations = policy["mutations"]
    assert isinstance(mutations, dict)
    cleanup = mutations["cleanup"]
    assert isinstance(cleanup, dict)
    cleanup["strategies"] = ["captured-id"]
    path.write_text(yaml.safe_dump(policy), encoding="utf-8")
    findings = validator.validate_policy(path)
    assert any("verified-baseline-difference" in finding for finding in findings)


def test_mutation_outcome_separates_completion_from_identity(tmp_path: Path) -> None:
    validator = _load("upstream_outcome_semantics", CONTRACTS / "validate_upstream_contract.py")
    contract = {
        "schema_version": 1,
        "upstream": {"name": "legacy-financial-api", "classification": "legacy"},
        "observations": [
            {
                "operation": "create-budget",
                "method": "POST",
                "endpoint": "/budgets",
                "request_encoding": "form",
                "success_statuses": [201],
                "response_body": "empty",
                "credential_placement": "query",
                "confidence": "observed",
                "mutation_outcome": {
                    "completion": "confirmed-success",
                    "identity": "unavailable",
                    "representation": "unavailable",
                    "reconciliation_required": True,
                },
                "evidence": ["controlled disposable-backend probe"],
            }
        ],
    }
    path = tmp_path / "upstream-contract.yaml"
    path.write_text(yaml.safe_dump(contract), encoding="utf-8")
    assert validator.validate_contract(path, require_observed=True) == []

    observation = contract["observations"][0]
    assert isinstance(observation, dict)
    observation.pop("mutation_outcome")
    path.write_text(yaml.safe_dump(contract), encoding="utf-8")
    findings = validator.validate_contract(path, require_observed=True)
    assert any("separate completion, identity, and representation" in finding for finding in findings)


def test_external_trust_lock_uses_one_candidate_snapshot(tmp_path: Path, monkeypatch) -> None:
    validator = _load(
        "external_lock_snapshot",
        CONTRACTS / "validate_external_trust_lock.py",
        extra_path=CONTRACTS,
    )
    authority_revision = "a" * 40
    candidate_revision = "c" * 40
    lock = tmp_path / "trusted-executable-sources.lock.yaml"
    original = {
        "schema_version": 1,
        "sources": [
            {
                "id": "ai-skills",
                "role": "auditor",
                "repository": "trusted/ai-skills",
                "revision": authority_revision,
                "credential_access": "read-only-provider",
                "files": [
                    {
                        "authority_path": "contracts/validate_external_adoption.py",
                        "sha256": "sha256:" + "0" * 64,
                    }
                ],
            }
        ],
    }
    immutable_text = yaml.safe_dump(original)
    lock.write_text(immutable_text, encoding="utf-8")
    authority = tmp_path / "authority"
    authority.mkdir()

    def read_immutable_candidate(*_args, **_kwargs):
        changed = dict(original)
        changed["sources"] = [dict(original["sources"][0], repository="attacker/replaced")]
        lock.write_text(yaml.safe_dump(changed), encoding="utf-8")
        return immutable_text

    captured: dict[str, object] = {}

    def validate_snapshot(document, **_kwargs):
        captured["repository"] = document["sources"][0]["repository"]
        return []

    monkeypatch.setattr(validator.trusted_sources, "_verify_candidate_identity", lambda *_args: None)
    monkeypatch.setattr(validator.trusted_sources, "_authority_text", read_immutable_candidate)
    monkeypatch.setattr(validator.trusted_lock_snapshot, "validate_document", validate_snapshot)
    findings = validator.validate_external_lock(
        lock.name,
        candidate_root=tmp_path,
        candidate_repository="consumer/project",
        candidate_revision=candidate_revision,
        authority_root=authority,
        source_id="ai-skills",
        expected_repository="trusted/ai-skills",
        expected_revision=authority_revision,
        required_authority_paths=("contracts/validate_external_adoption.py",),
    )
    assert findings == []
    assert captured["repository"] == "trusted/ai-skills"


def test_consumer_canary_git_resolution_ignores_path(tmp_path: Path, monkeypatch) -> None:
    checker = _load("consumer_canary_git", MCP_TOOLS / "check_consumer_canaries.py", extra_path=MCP_TOOLS)
    trusted = tmp_path / "trusted-git"
    trusted.write_text("trusted", encoding="utf-8")
    trusted.chmod(0o755)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake = fake_bin / ("git.exe" if os.name == "nt" else "git")
    fake.write_text("candidate controlled", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin))
    monkeypatch.setattr(checker, "_TRUSTED_GIT_CANDIDATES", (trusted,))

    assert checker._trusted_git_executable() == str(trusted)
    assert checker._git_argv("status")[0] == str(trusted)
    assert checker._git_argv("status")[0] != str(fake)


def test_normative_migration_semantics_are_explicit() -> None:
    upstream = (ROOT / "skills/mcp-server-architect/references/upstream-contract-discovery.md").read_text(
        encoding="utf-8"
    )
    migration = (ROOT / "skills/mcp-server-architect/references/migration-assessment.md").read_text(
        encoding="utf-8"
    )
    readme = (ROOT / "skills/afds-doc-writer/references/ecosystem-readme-governance.md").read_text(
        encoding="utf-8"
    )
    trust = (ROOT / "skills/ci-cd-architect/references/trusted-executable-sources.md").read_text(
        encoding="utf-8"
    )
    provenance = (
        ROOT / "skills/mcp-server-architect/references/container-provenance-dataflow.md"
    ).read_text(encoding="utf-8")

    assert "Opt-in proves operator intent" in upstream
    assert "Identity uncertainty and completion uncertainty are independent" in upstream
    assert "Implementation and assurance are independent" in migration
    assert "Zero unresolved bot threads is thread hygiene" in migration
    assert "product and user entrypoint" in readme
    assert "Durable and volatile information" in readme
    assert "SOURCE_DATE_EPOCH` is a reproducibility control" in trust
    assert "review against SHA A is not a review of SHA B" in trust
    assert "conservative stage-local dataflow property" in provenance
    assert "self-comparison, not provenance verification" in provenance
