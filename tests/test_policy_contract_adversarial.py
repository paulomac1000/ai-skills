"""Adversarial coverage for policy-critical governance contracts retained in ai-skills."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

from contracts import validate_verification_receipt as receipt

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


STATE_ISOLATION = _load_module(
    "policy_contract_state_isolation",
    ROOT / "skills/ci-cd-architect/tools/verify_state_isolation.py",
)


@pytest.mark.parametrize("value", [-1, True, 1.5, "1", None])
def test_receipt_non_negative_integer_validation(value: object) -> None:
    with pytest.raises(receipt.VerificationReceiptError, match="non-negative integer"):
        receipt._non_negative_int(value, "field")


def _corpus(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "discovered_files": 2,
        "executed_files": 1,
        "excluded_files": [{"path": "tests/excluded.py", "reason": "hosted only"}],
        "accounted_files": 2,
        "execution_evidence": "observed",
        "completeness": "complete",
        "discovery_drift": 0,
    }
    value.update(overrides)
    return value


def test_receipt_semantics_cover_arithmetic_exclusions_and_pass_invariants() -> None:
    assert receipt.validate_receipt_semantics({}) == ["test_corpus must be an object"]
    assert "excluded_files must be an array" in receipt.validate_receipt_semantics(
        {"test_corpus": _corpus(excluded_files="bad")}
    )[0]

    findings = receipt.validate_receipt_semantics(
        {
            "verdict": "pass",
            "test_corpus": _corpus(
                discovered_files=1,
                executed_files=1,
                accounted_files=3,
                excluded_files=[
                    {"path": "tests/x.py"},
                    {"path": "tests/x.py"},
                    {},
                    "bad",
                ],
                execution_evidence="declared",
                completeness="partial",
                discovery_drift=1,
            ),
        }
    )
    assert any("duplicate test-corpus exclusion" in item for item in findings)
    assert any("entries must be objects" in item for item in findings)
    assert any("path must be non-empty" in item for item in findings)
    assert any("accounted_files must equal" in item for item in findings)
    assert any("more files" in item for item in findings)
    assert any("observed execution" in item for item in findings)
    assert any("complete test-corpus" in item for item in findings)
    assert any("zero test discovery" in item for item in findings)


def test_receipt_loader_and_validator_fail_closed_on_malformed_inputs(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    path.write_bytes(b"\xff")
    with pytest.raises(receipt.VerificationReceiptError, match="invalid UTF-8 JSON"):
        receipt._load_mapping(path)
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(receipt.VerificationReceiptError, match="root must be an object"):
        receipt._load_mapping(path)
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(receipt.VerificationReceiptError, match="exceeds"):
        receipt._read_file_bounded(path, max_bytes=1)


def test_receipt_validator_combines_schema_and_semantic_findings() -> None:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["test_corpus"],
    }
    assert receipt.validate_receipt({"test_corpus": _corpus()}, schema=schema) == []
    findings = receipt.validate_receipt(
        {"verdict": "pass", "test_corpus": _corpus(accounted_files=1)},
        schema=schema,
    )
    assert any("accounted_files must equal" in item for item in findings)
    assert any("every discovered file" in item for item in findings)


def test_receipt_main_reports_input_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not-json", encoding="utf-8")
    assert receipt.main([str(path)]) == 2
    assert "ERROR:" in capsys.readouterr().out


def test_state_isolation_snapshots_files_and_detects_overlap(tmp_path: Path) -> None:
    protected = tmp_path / "protected"
    protected.mkdir()
    (protected / "state.db").write_bytes(b"state")
    nested = protected / "nested"
    nested.mkdir()
    (nested / "value.txt").write_text("value", encoding="utf-8")
    snap = STATE_ISOLATION.snapshot([protected])
    assert len(snap) == 2
    STATE_ISOLATION.prove_disjoint([tmp_path / "scratch"], [protected])
    with pytest.raises(ValueError, match="overlap"):
        STATE_ISOLATION.prove_disjoint([protected / "scratch"], [protected])


def test_state_isolation_file_and_count_bounds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    protected = tmp_path / "protected"
    protected.mkdir()
    file = protected / "state.db"
    file.write_bytes(b"12")
    with monkeypatch.context() as patch:
        patch.setattr(STATE_ISOLATION, "MAX_FILE_BYTES", 1)
        with pytest.raises(ValueError, match="size bound"):
            STATE_ISOLATION.snapshot([file])
    with monkeypatch.context() as patch:
        patch.setattr(STATE_ISOLATION, "MAX_FILES", 0)
        with pytest.raises(ValueError, match="maximum file count"):
            STATE_ISOLATION.snapshot([protected])


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink support required")
def test_state_isolation_rejects_symlinked_protected_state(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("state", encoding="utf-8")
    link = tmp_path / "link"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    with pytest.raises(ValueError, match="must not be a symlink"):
        STATE_ISOLATION.snapshot([link])


def test_state_isolation_cli_snapshot_and_change_detection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    protected = tmp_path / "protected"
    protected.mkdir()
    state = protected / "state.txt"
    state.write_text("before", encoding="utf-8")
    snapshot_path = tmp_path / "snapshot.json"

    monkeypatch.setattr(
        sys,
        "argv",
        ["verify_state_isolation.py", "snapshot", "--protected", str(protected), "--output", str(snapshot_path)],
    )
    assert STATE_ISOLATION.main() == 0
    assert '"verdict": "pass"' in capsys.readouterr().out

    monkeypatch.setattr(
        sys,
        "argv",
        ["verify_state_isolation.py", "assert-unchanged", "--protected", str(protected), "--snapshot", str(snapshot_path)],
    )
    assert STATE_ISOLATION.main() == 0
    capsys.readouterr()

    state.write_text("after", encoding="utf-8")
    assert STATE_ISOLATION.main() == 1
    assert '"verdict": "fail"' in capsys.readouterr().out
