"""Focused regressions for the final PR #87 hardening review."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

import pytest
from jsonschema import Draft202012Validator

from contracts.deployment_lease import DeploymentLeaseError, admit_lease
from contracts.secret_taint import TaintGuard, TaintViolation
from contracts.skill_consumer import SkillConsumerError, load_catalog, resolve_skill
from contracts.skill_distribution import DistributionError, install

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


TASK_ORCHESTRATOR = _load_module(
    "pr87_task_orchestrator",
    ROOT / "skills/agent-task-orchestrator/tools/task_orchestrator.py",
)
EXECUTION_INTEGRITY = _load_module(
    "pr87_execution_integrity",
    ROOT / "skills/ci-cd-architect/tools/check_execution_integrity.py",
)
BOOTSTRAP = _load_module(
    "pr87_verification_bootstrap",
    ROOT / "skills/ci-cd-architect/tools/check_verification_bootstrap.py",
)
RECEIPT_VALIDATOR = _load_module(
    "pr87_receipt_validator",
    ROOT / "contracts/validate_verification_receipt.py",
)


def _taint_guard() -> TaintGuard:
    guard = TaintGuard()
    guard.observe(
        "s3cr3t-token",
        sensitivity="secret",
        source_boundary="environment",
        opaque_ref="secret:token",
    )
    return guard


def test_protected_callback_rejects_direct_and_nested_binary_secret_results() -> None:
    guard = _taint_guard()
    with pytest.raises(TaintViolation, match="contains tainted material"):
        guard.use_protected(
            "secret:token",
            channel="credential-broker",
            purpose="authenticate",
            operation=lambda raw: raw.encode("utf-8"),
        )
    with pytest.raises(TaintViolation, match="contains tainted material"):
        guard.use_protected(
            "secret:token",
            channel="credential-broker",
            purpose="authenticate",
            operation=lambda raw: {"nested": [bytearray(f"prefix:{raw}:suffix", "utf-8")]},
        )


def test_catalog_loader_and_in_memory_resolver_reject_scalar_capabilities(tmp_path: Path) -> None:
    malformed = {
        "schema_version": 1,
        "catalog_revision": "test",
        "skills": [
            {
                "skill_id": "analysis-skill",
                "version": "2.0.0",
                "manifest_path": "skills/analysis-skill/manifest.yaml",
                "skill_entrypoint": "skills/analysis-skill/SKILL.md",
                "capabilities": "analysis",
                "use_when": ["analysis requested"],
                "do_not_use_when": ["different capability requested"],
                "loading": {"modes": ["runtime_tool"]},
            }
        ],
    }
    path = tmp_path / "catalog.yaml"
    path.write_text(json.dumps(malformed), encoding="utf-8")
    with pytest.raises(SkillConsumerError, match="capabilities"):
        load_catalog(path)
    with pytest.raises(SkillConsumerError, match="capabilities"):
        resolve_skill(catalog=malformed, runtime={"skills": []}, capability="ana")


def test_session_bound_deployment_lease_rejects_other_session() -> None:
    digest = "sha256:" + "a" * 64
    args_digest = "sha256:" + "b" * 64
    lease = {
        "lease_id": "lease-1",
        "principal": "operator",
        "session": "session-a",
        "target": {"project": "app", "environment": "production", "resource": "service:web"},
        "artifact_digest": digest,
        "action": "deploy",
        "normalized_args_digest": args_digest,
        "policy_revision": "policy-1",
        "issued_at": "2026-09-10T10:00:00Z",
        "expires_at": "2026-09-10T12:00:00Z",
        "state": "active",
    }
    with pytest.raises(DeploymentLeaseError, match="session does not match"):
        admit_lease(
            lease,
            principal="operator",
            session="session-b",
            target={"project": "app", "environment": "production", "resource": "service:web"},
            artifact_digest=digest,
            action="deploy",
            normalized_args_digest=args_digest,
            now=datetime(2026, 9, 10, 11, 0, tzinfo=UTC),
        )


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required for EPHEMERAL ignore verification")
def test_ephemeral_install_rejects_wildcard_reinclude(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    (project / ".gitignore").write_text(".ai-skills/ephemeral/\n!*/ephemeral/\n", encoding="utf-8")
    source = tmp_path / "source"
    source.mkdir()
    (source / "SKILL.md").write_text("# Example\n", encoding="utf-8")

    with pytest.raises(DistributionError, match="must be ignored"):
        install(
            source=source,
            target=project / ".ai-skills/ephemeral/example-skill",
            project_root=project,
            mode="EPHEMERAL",
            skill_id="example-skill",
            canonical_source="github:example/skills/example-skill",
            source_revision="a" * 40,
            managed_by="ai-skills",
            update_policy="explicit",
            cleanup_policy="owner-digest-verified",
            installed_at="2026-09-10T00:00:00+00:00",
        )


def _minimal_pass_receipt() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "candidate": {"source_revision": "a" * 40},
        "bootstrap": {"policy_revision": "policy-1", "declared_dependencies_only": True},
        "test_corpus": {
            "policy_revision": "tests-1",
            "discovered_files": 0,
            "executed_files": 0,
            "excluded_files": [],
            "accounted_files": 0,
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
        "verdict": "pass",
    }


def test_pass_receipt_requires_nonempty_evidence_refs() -> None:
    schema = json.loads((ROOT / "contracts/verification-receipt.schema.json").read_text(encoding="utf-8"))
    receipt = _minimal_pass_receipt()
    assert list(Draft202012Validator(schema).iter_errors(receipt))
    receipt["evidence_refs"] = []
    assert list(Draft202012Validator(schema).iter_errors(receipt))
    receipt["evidence_refs"] = ["evidence:run-1"]
    assert list(Draft202012Validator(schema).iter_errors(receipt)) == []


def test_terminal_evidence_without_outputs_must_bind_the_current_task() -> None:
    revision = "a" * 40
    bindings = {
        "evidence:other": {
            "intent_revision": 3,
            "execution_revision": revision,
            "subjects": ["task:other-task"],
        },
        "evidence:task": {
            "intent_revision": 3,
            "execution_revision": revision,
            "subjects": ["task:task-1"],
        },
    }
    rejected = TASK_ORCHESTRATOR.classify_terminal(
        requires_work=True,
        child_disposition="completed",
        expected_outputs=[],
        task_id="task-1",
        intent_revision=3,
        execution_revision=revision,
        evidence_bindings=bindings,
        evidence_refs=["evidence:other"],
    )
    assert rejected.code == "COMPLETED_NO_EVIDENCE"
    accepted = TASK_ORCHESTRATOR.classify_terminal(
        requires_work=True,
        child_disposition="completed",
        expected_outputs=[],
        task_id="task-1",
        intent_revision=3,
        execution_revision=revision,
        evidence_bindings=bindings,
        evidence_refs=["evidence:task"],
    )
    assert accepted.code == "TERMINAL_EVIDENCE_PRESENT"


def _swap_path_after_open(
    monkeypatch: pytest.MonkeyPatch,
    module: ModuleType,
    path: Path,
    reader: Callable[[], bytes | str],
    expected: bytes | str,
) -> None:
    original_open = os.open

    def swapping_open(target: os.PathLike[str] | str, flags: int, *args: Any, **kwargs: Any) -> int:
        descriptor = original_open(target, flags, *args, **kwargs)
        if Path(target) == path:
            replacement = path.with_name(path.name + ".replacement")
            replacement.write_bytes(b"substitute")
            os.replace(replacement, path)
        return descriptor

    with monkeypatch.context() as patch:
        patch.setattr(module.os, "open", swapping_open)
        assert reader() == expected


def test_descriptor_bound_readers_do_not_process_same_path_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases: list[tuple[ModuleType, Path, Callable[[], bytes | str], bytes | str]] = []

    log = tmp_path / "run.log"
    log.write_bytes(b"original!!")
    cases.append((EXECUTION_INTEGRITY, log, lambda: EXECUTION_INTEGRITY._read(log), "original!!"))

    policy = tmp_path / "policy.yaml"
    policy.write_bytes(b"original!!")
    cases.append((BOOTSTRAP, policy, lambda: BOOTSTRAP._read_bounded(policy, 100, label="policy"), b"original!!"))

    receipt = tmp_path / "receipt.json"
    receipt.write_bytes(b"original!!")
    cases.append((RECEIPT_VALIDATOR, receipt, lambda: RECEIPT_VALIDATOR._read_file_bounded(receipt, max_bytes=100), b"original!!"))

    for module, path, reader, expected in cases:
        _swap_path_after_open(monkeypatch, module, path, reader, expected)
