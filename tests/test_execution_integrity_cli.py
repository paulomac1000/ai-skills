"""CLI regressions for execution-integrity verification."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills/ci-cd-architect/tools/check_execution_integrity.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("execution_integrity_cli", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_module()


def test_execution_integrity_classifies_each_runtime_failure_axis() -> None:
    result = MODULE.evaluate(
        "\n".join(
            [
                "not ok 3 - worker # cancelled",
                "Promise resolution is still pending",
                "coroutine background was never awaited",
                "PytestUnraisableExceptionWarning: destructor failed",
                "unhandledRejection: promise failed",
                "SomeWarning: unreviewed warning",
            ]
        )
    )

    assert result["verdict"] == "fail"
    assert result["cancelled"] == 1
    assert result["pending"] == 1
    assert result["unraisable"] == 1
    assert result["unhandled_exceptions"] == 1
    assert result["blocking_warnings"] == 2
    assert result["leaked_async_work"] == 2


def test_execution_integrity_cli_writes_pass_result_and_honors_reviewed_warning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    log = tmp_path / "test.log"
    output = tmp_path / "result.json"
    log.write_text("DeprecationWarning: reviewed legacy warning\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check_execution_integrity.py",
            str(log),
            "--allow",
            "DeprecationWarning",
            "--output",
            str(output),
        ],
    )

    assert MODULE.main() == 0
    printed = json.loads(capsys.readouterr().out)
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert printed == persisted
    assert persisted["verdict"] == "pass"
    assert persisted["allowed_warnings"] == 1


def test_execution_integrity_cli_returns_one_for_blocking_runtime_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    log = tmp_path / "test.log"
    log.write_text("Exception in thread worker: RuntimeError\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["check_execution_integrity.py", str(log)])

    assert MODULE.main() == 1
    result = json.loads(capsys.readouterr().out)
    assert result["verdict"] == "fail"
    assert result["unhandled_exceptions"] == 1


def test_execution_integrity_cli_fails_closed_for_invalid_allow_regex(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    log = tmp_path / "test.log"
    log.write_text("clean\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["check_execution_integrity.py", str(log), "--allow", "["],
    )

    assert MODULE.main() == 2
    result = json.loads(capsys.readouterr().out)
    assert result["verdict"] == "fail"
    assert "unterminated character set" in result["error"]
