from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
CI_TOOLS = ROOT / "skills" / "ci-cd-architect" / "tools"
AGENT_TOOLS = ROOT / "skills" / "agents-md-architect" / "tools"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PARITY = _load("wave1_local_ci_parity", CI_TOOLS / "check_local_ci_parity.py")
CORPUS = _load("wave1_test_corpus", CI_TOOLS / "check_test_corpus.py")
RECEIPT = _load("wave1_receipt", ROOT / "contracts" / "validate_verification_receipt.py")


def _write_parity_fixture(root: Path, *, local_entrypoint: str | None) -> dict[str, object]:
    workflow = root / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "on:\n  pull_request:\n\njobs:\n  required_gate:\n    runs-on: ubuntu-latest\n    steps: []\n",
        encoding="utf-8",
    )
    (root / "policy.md").write_text("policy\n", encoding="utf-8")
    (root / "requirements.lock").write_text("locked\n", encoding="utf-8")
    gate: dict[str, object] = {
        "id": "required_gate",
        "merge_blocking": True,
        "policy_ref": "policy.md",
    }
    if local_entrypoint is not None:
        gate["local_entrypoint"] = local_entrypoint
        gate["dependency_ref"] = "requirements.lock"
    return {"schema_version": 1, "policy_revision": "policy-1", "gates": [gate]}


def test_parity_fails_closed_for_discovered_blocking_job_without_policy_entry(tmp_path: Path) -> None:
    policy = _write_parity_fixture(tmp_path, local_entrypoint=None)
    policy["gates"] = [
        {
            "id": "different_gate",
            "merge_blocking": True,
            "hosted_only": True,
            "hosted_only_reason": "provider-only evidence",
            "policy_ref": "policy.md",
        }
    ]
    result = PARITY.evaluate(policy, root=tmp_path)
    assert result["verdict"] == "fail"
    assert result["unmapped_merge_blocking_jobs"] == ["required_gate"]


def test_parity_rejects_nonexistent_local_entrypoint(tmp_path: Path) -> None:
    policy = _write_parity_fixture(tmp_path, local_entrypoint="python scripts/missing.py")
    result = PARITY.evaluate(policy, root=tmp_path)
    assert result["verdict"] == "fail"
    assert result["invalid_gates"] == ["required_gate"]


def _corpus_policy(expires_at: str | None) -> dict[str, object]:
    exclusion: dict[str, object] = {"path": "tests/test_one.py", "reason": "temporary quarantine"}
    if expires_at is not None:
        exclusion["expires_at"] = expires_at
    return {
        "schema_version": 1,
        "policy_revision": "corpus-1",
        "mode": "automatic",
        "include": ["tests/test_*.py"],
        "exclusions": [exclusion],
    }


def test_test_corpus_expired_exclusion_is_discovery_drift(tmp_path: Path) -> None:
    test_file = tmp_path / "tests" / "test_one.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_one():\n    pass\n", encoding="utf-8")
    now = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)

    result = CORPUS.evaluate(
        tmp_path,
        _corpus_policy("2026-09-10T12:00:00Z"),
        observed_executed=[],
        now=now,
    )
    assert result["verdict"] == "fail"
    assert result["completeness"] == "drift"
    assert result["expired_exclusions"] == ["tests/test_one.py"]
    assert result["accounted_files"] == 0


@pytest.mark.parametrize("expires_at", ["2026-09-12T12:00:00Z", None])
def test_test_corpus_active_or_unbounded_exclusion_remains_accounted(
    tmp_path: Path,
    expires_at: str | None,
) -> None:
    test_file = tmp_path / "tests" / "test_one.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_one():\n    pass\n", encoding="utf-8")
    result = CORPUS.evaluate(
        tmp_path,
        _corpus_policy(expires_at),
        observed_executed=[],
        now=datetime(2026, 9, 11, 12, 0, tzinfo=UTC),
    )
    assert result["verdict"] == "pass"
    assert result["accounted_files"] == 1
    assert result["expired_exclusions"] == []


def _receipt(expires_at: str | None) -> dict[str, object]:
    exclusion: dict[str, object] = {"path": "tests/test_one.py", "reason": "temporary quarantine"}
    if expires_at is not None:
        exclusion["expires_at"] = expires_at
    return {
        "schema_version": 1,
        "candidate": {"source_revision": "a" * 40},
        "bootstrap": {"policy_revision": "bootstrap-1", "declared_dependencies_only": True},
        "test_corpus": {
            "policy_revision": "corpus-1",
            "discovered_files": 1,
            "executed_files": 0,
            "excluded_files": [exclusion],
            "accounted_files": 1,
            "discovery_drift": 0,
            "execution_evidence": "observed",
            "completeness": "complete",
        },
        "execution_integrity": {
            "cancelled": 0,
            "pending": 0,
            "unhandled_exceptions": 0,
            "unraisable": 0,
            "blocking_warnings": 0,
            "leaked_async_work": 0,
        },
        "isolation": {"production_effective_state_touched": False},
        "evidence_refs": ["evidence:run"],
        "verdict": "pass",
    }


def test_receipt_expired_exclusion_cannot_support_pass() -> None:
    findings = RECEIPT.validate_receipt_semantics(
        _receipt("2026-09-10T12:00:00Z"),
        now=datetime(2026, 9, 11, 12, 0, tzinfo=UTC),
    )
    assert any("expired test-corpus exclusion" in finding for finding in findings)
    assert any("accounted_files" in finding for finding in findings)


@pytest.mark.parametrize("expires_at", ["2026-09-12T12:00:00Z", None])
def test_receipt_active_or_unbounded_exclusion_can_support_pass(expires_at: str | None) -> None:
    assert (
        RECEIPT.validate_receipt_semantics(
            _receipt(expires_at),
            now=datetime(2026, 9, 11, 12, 0, tzinfo=UTC),
        )
        == []
    )


def test_removed_runtime_layer_has_no_python_references() -> None:
    forbidden = (
        "agent-task-orchestrator",
        "diagnostic_reasoning",
        "diagnostic-state.schema.json",
        "secret_taint",
        "secret-taint",
        "skill_consumer",
        "skill_distribution",
        "build_skill_bundle",
        "skill-catalog.yaml",
        "intent-ledger.schema.json",
        "delegation-contract.schema.json",
    )
    offenders: list[str] = []
    for base in (ROOT / "contracts", ROOT / "scripts", ROOT / "skills", ROOT / "tests"):
        for path in base.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if path.name == Path(__file__).name:
                continue
            if any(token in text for token in forbidden):
                offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []
