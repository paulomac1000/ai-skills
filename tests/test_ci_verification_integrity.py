from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills" / "ci-cd-architect" / "tools"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


test_corpus = _load("check_test_corpus")
execution = _load("check_execution_integrity")
parity = _load("check_local_ci_parity")
isolation = _load("verify_state_isolation")
bootstrap = _load("check_verification_bootstrap")


def test_manifest_drift_reproduces_34_discovered_23_selected(tmp_path: Path) -> None:
    for index in range(34):
        path = tmp_path / "tests" / f"case_{index}.test.mjs"
        path.parent.mkdir(exist_ok=True)
        path.write_text("", encoding="utf-8")
    manifest = tmp_path / "tests.manifest"
    manifest.write_text("\n".join(f"tests/case_{index}.test.mjs" for index in range(23)), encoding="utf-8")
    result = test_corpus.evaluate(
        tmp_path,
        {
            "schema_version": 1,
            "policy_revision": "fixture",
            "mode": "manifest",
            "include": ["tests/*.test.mjs"],
            "execution_manifest": "tests.manifest",
        },
        observed_executed={f"tests/case_{index}.test.mjs" for index in range(23)},
    )
    assert result["discovered_files"] == 34
    assert result["selected_files"] == 23
    assert result["executed_files"] == 23
    assert result["discovery_drift"] == 11
    assert result["verdict"] == "fail"


def test_automatic_selection_without_post_run_execution_evidence_is_incomplete(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "a.test.ts").write_text("", encoding="utf-8")
    result = test_corpus.evaluate(
        tmp_path,
        {
            "schema_version": 1,
            "policy_revision": "fixture",
            "mode": "automatic",
            "include": ["tests/*.test.ts"],
        },
    )
    assert result["selected_files"] == 1
    assert result["executed_files"] == 0
    assert result["execution_evidence"] == "unknown"
    assert result["completeness"] == "unknown"
    assert result["verdict"] == "incomplete"


def test_automatic_discovery_passes_with_observed_execution_and_reviewed_exclusion(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    for name in ("a.test.ts", "b.test.ts"):
        (tmp_path / "tests" / name).write_text("", encoding="utf-8")
    policy = {
        "schema_version": 1,
        "policy_revision": "fixture",
        "mode": "automatic",
        "include": ["tests/*.test.ts"],
        "exclusions": [{"path": "tests/b.test.ts", "reason": "provider-only fixture", "owner": "team"}],
    }
    result = test_corpus.evaluate(tmp_path, policy, observed_executed={"tests/a.test.ts"})
    assert result["verdict"] == "pass"
    assert result["completeness"] == "complete"
    assert result["excluded_files"][0]["path"] == "tests/b.test.ts"


def test_stale_exclusion_is_policy_drift(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "a.py").write_text("", encoding="utf-8")
    result = test_corpus.evaluate(
        tmp_path,
        {
            "schema_version": 1,
            "policy_revision": "fixture",
            "mode": "automatic",
            "include": ["tests/*.py"],
            "exclusions": [{"path": "tests/old.py", "reason": "old"}],
        },
        observed_executed={"tests/a.py"},
    )
    assert result["verdict"] == "fail"
    assert result["discovery_drift"] == 1


def test_pytest_unhandled_thread_warning_is_blocking_even_if_allowlist_matches() -> None:
    result = execution.evaluate(
        "PytestUnhandledThreadExceptionWarning: TypeError: boom",
        (re.compile(r".*Warning.*"),),
    )
    assert result["unhandled_exceptions"] == 1
    assert result["allowed_warnings"] == 0
    assert result["verdict"] == "fail"


def test_node_green_subtests_but_cancelled_pending_file_is_blocking() -> None:
    result = execution.evaluate("11 tests passed\ncancelled: Promise resolution is still pending")
    assert result["cancelled"] == 1
    assert result["pending"] == 1
    assert result["leaked_async_work"] == 1
    assert result["verdict"] == "fail"


def test_plain_english_cancelled_word_is_not_false_positive() -> None:
    result = execution.evaluate("cleanup cancelled by operator before tests were selected")
    assert result["verdict"] == "pass"


def test_reviewed_deprecation_can_be_non_blocking() -> None:
    result = execution.evaluate(
        "DeprecationWarning: dependency API is deprecated",
        (re.compile(r"^DeprecationWarning:"),),
    )
    assert result["allowed_warnings"] == 1
    assert result["verdict"] == "pass"


def test_unreviewed_warning_is_not_silently_green() -> None:
    result = execution.evaluate("DeprecationWarning: dependency API is deprecated")
    assert result["blocking_warnings"] == 1
    assert result["verdict"] == "fail"


def test_merge_blocking_gate_requires_faithful_local_or_hosted_only_contract() -> None:
    bad = parity.evaluate(
        {"schema_version": 1, "policy_revision": "p1", "gates": [{"id": "security", "merge_blocking": True}]}
    )
    assert bad["verdict"] == "fail"

    hosted_only = parity.evaluate(
        {
            "schema_version": 1,
            "policy_revision": "p1",
            "gates": [
                {
                    "id": "security",
                    "merge_blocking": True,
                    "hosted_only": True,
                    "hosted_only_reason": "requires provider identity",
                    "policy_ref": "policy/security.yml",
                }
            ],
        }
    )
    assert hosted_only["verdict"] == "pass"
    assert hosted_only["hosted_only_gates"] == ["security"]

    local = parity.evaluate(
        {
            "schema_version": 1,
            "policy_revision": "p1",
            "gates": [
                {
                    "id": "tests",
                    "merge_blocking": True,
                    "local_entrypoint": "scripts/verify-ci",
                    "policy_ref": "pyproject.toml",
                    "dependency_ref": "requirements-ci.lock",
                }
            ],
        }
    )
    assert local["verdict"] == "pass"


def test_gate_cannot_be_local_and_hosted_only_simultaneously() -> None:
    result = parity.evaluate(
        {
            "schema_version": 1,
            "policy_revision": "p1",
            "gates": [
                {
                    "id": "x",
                    "merge_blocking": True,
                    "local_entrypoint": "verify",
                    "hosted_only": True,
                    "hosted_only_reason": "provider",
                    "policy_ref": "p",
                    "dependency_ref": "lock",
                }
            ],
        }
    )
    assert result["verdict"] == "fail"


def test_bootstrap_rejects_ambient_dependency_and_accepts_declared_lock(tmp_path: Path) -> None:
    lock = tmp_path / "requirements-ci.lock"
    lock.write_text("pytest==9.0.2\n", encoding="utf-8")
    base = {
        "schema_version": 1,
        "policy_revision": "bootstrap-1",
        "network": "required",
        "cache": "verified",
        "dependencies": [
            {
                "id": "pytest",
                "source_type": "lockfile",
                "source": "requirements-ci.lock",
                "resolved_version": "9.0.2",
                "expected_version": "9.0.2",
                "resolution": "declared",
            }
        ],
    }
    assert bootstrap.evaluate(tmp_path, base)["verdict"] == "pass"
    ambient = {**base, "dependencies": [{**base["dependencies"][0], "resolution": "ambient"}]}
    assert bootstrap.evaluate(tmp_path, ambient)["verdict"] == "fail"


def test_bootstrap_rejects_mutable_image_reference(tmp_path: Path) -> None:
    policy = {
        "schema_version": 1,
        "policy_revision": "p",
        "network": "required",
        "cache": "disabled",
        "dependencies": [
            {
                "id": "toolchain",
                "source_type": "immutable-image",
                "source": "example/tool:latest",
                "resolved_version": "1",
                "resolution": "declared",
            }
        ],
    }
    assert bootstrap.evaluate(tmp_path, policy)["verdict"] == "fail"


def test_state_isolation_rejects_nested_future_writable_path(tmp_path: Path) -> None:
    protected = tmp_path / "prod"
    protected.mkdir()
    writable = protected / "future-output"
    with pytest.raises(ValueError):
        isolation.prove_disjoint([writable], [protected])


def test_state_snapshot_detects_mutation(tmp_path: Path) -> None:
    protected = tmp_path / "effective.env"
    protected.write_text("MODE=prod\n", encoding="utf-8")
    before = isolation.snapshot([protected])
    protected.write_text("MODE=test\n", encoding="utf-8")
    assert before != isolation.snapshot([protected])


def test_state_snapshot_rejects_symlink_in_protected_tree(tmp_path: Path) -> None:
    protected = tmp_path / "prod"
    protected.mkdir()
    target = tmp_path / "outside"
    target.write_text("x", encoding="utf-8")
    (protected / "link").symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        isolation.snapshot([protected])
