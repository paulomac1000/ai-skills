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


def test_manifest_drift_reproduces_34_discovered_23_executed(tmp_path: Path) -> None:
    for index in range(34):
        path = tmp_path / "tests" / f"case_{index}.test.mjs"
        path.parent.mkdir(exist_ok=True)
        path.write_text("", encoding="utf-8")
    manifest = tmp_path / "tests.manifest"
    manifest.write_text("\n".join(f"tests/case_{index}.test.mjs" for index in range(23)), encoding="utf-8")
    result = test_corpus.evaluate(tmp_path, {"schema_version": 1, "policy_revision": "fixture", "mode": "manifest", "include": ["tests/*.test.mjs"], "execution_manifest": "tests.manifest"})
    assert result["discovered_files"] == 34
    assert result["executed_files"] == 23
    assert result["discovery_drift"] == 11
    assert result["verdict"] == "fail"


def test_reviewed_exclusion_is_visible_not_orphaned(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    for name in ("a.test.ts", "b.test.ts"):
        (tmp_path / "tests" / name).write_text("", encoding="utf-8")
    result = test_corpus.evaluate(tmp_path, {"schema_version": 1, "mode": "automatic", "include": ["tests/*.test.ts"], "exclusions": [{"path": "tests/b.test.ts", "reason": "provider-only fixture", "owner": "team"}]})
    assert result["verdict"] == "pass"
    assert result["excluded_files"][0]["path"] == "tests/b.test.ts"


def test_pytest_unhandled_thread_warning_is_blocking() -> None:
    result = execution.evaluate("190 passed, 1 warning\nPytestUnhandledThreadExceptionWarning: TypeError: boom")
    assert result["unhandled_exceptions"] == 1
    assert result["verdict"] == "fail"


def test_node_green_subtests_but_cancelled_file_is_blocking() -> None:
    result = execution.evaluate("11 tests passed\ncancelled: Promise resolution is still pending")
    assert result["cancelled"] == 1
    assert result["verdict"] == "fail"


def test_reviewed_deprecation_can_be_non_blocking() -> None:
    result = execution.evaluate("DeprecationWarning: dependency API is deprecated", (re.compile(r"^DeprecationWarning:"),))
    assert result["allowed_warnings"] == 1
    assert result["verdict"] == "pass"


def test_merge_blocking_gate_requires_local_or_hosted_only_reason() -> None:
    bad = parity.evaluate({"schema_version": 1, "gates": [{"id": "security", "merge_blocking": True}]})
    assert bad["verdict"] == "fail"
    good = parity.evaluate({"schema_version": 1, "gates": [{"id": "security", "merge_blocking": True, "hosted_only": True, "hosted_only_reason": "requires provider identity"}]})
    assert good["verdict"] == "pass"


def test_state_isolation_rejects_nested_writable_path(tmp_path: Path) -> None:
    protected = tmp_path / "prod"
    writable = protected / "test-output"
    writable.mkdir(parents=True)
    with pytest.raises(ValueError):
        isolation.prove_disjoint([writable], [protected])


def test_state_snapshot_detects_mutation(tmp_path: Path) -> None:
    protected = tmp_path / "effective.env"
    protected.write_text("MODE=prod\n", encoding="utf-8")
    before = isolation.snapshot([protected])
    protected.write_text("MODE=test\n", encoding="utf-8")
    after = isolation.snapshot([protected])
    assert before != after
