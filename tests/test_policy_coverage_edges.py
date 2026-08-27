"""Coverage regressions for fail-closed execution evidence boundaries."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from contracts.run_evidence_command import (
    MAX_CAPTURE_BYTES,
    MAX_TIMEOUT_SECONDS,
    _junit_cases,
    _safe_relative,
    _safe_working_directory,
    main as run_evidence_command,
)


def test_evidence_cli_rejects_invalid_identity_and_missing_argv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="execution_id"):
        run_evidence_command(["--execution-id", "INVALID", "--output", "record.json", "--", sys.executable])

    with pytest.raises(ValueError, match="exact non-empty argv"):
        run_evidence_command(["--execution-id", "valid-id", "--output", "record.json", "--"])


def test_evidence_cli_rejects_unsafe_working_directory_and_limits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    command = ["--", sys.executable, "-c", "pass"]

    with pytest.raises(ValueError, match="parent traversal"):
        run_evidence_command(
            [
                "--execution-id",
                "working-directory",
                "--working-directory",
                "../outside",
                "--output",
                "record.json",
                *command,
            ]
        )

    with pytest.raises(ValueError, match="timeout_seconds"):
        run_evidence_command(
            [
                "--execution-id",
                "timeout-bound",
                "--timeout-seconds",
                str(MAX_TIMEOUT_SECONDS + 1),
                "--output",
                "record.json",
                *command,
            ]
        )

    with pytest.raises(ValueError, match="max_output_bytes"):
        run_evidence_command(
            [
                "--execution-id",
                "output-bound",
                "--max-output-bytes",
                str(MAX_CAPTURE_BYTES + 1),
                "--output",
                "record.json",
                *command,
            ]
        )


def test_evidence_safe_paths_reject_missing_and_non_file_targets(tmp_path: Path) -> None:
    directory = tmp_path / "directory"
    directory.mkdir()
    file_path = tmp_path / "file.txt"
    file_path.write_text("ok\n", encoding="utf-8")

    resolved, relative = _safe_relative(file_path, tmp_path, "result_file")
    assert resolved == file_path.resolve()
    assert relative == "file.txt"

    with pytest.raises(ValueError, match="must exist"):
        _safe_relative(tmp_path / "missing.xml", tmp_path, "result_file")
    with pytest.raises(ValueError, match="regular file"):
        _safe_relative(directory, tmp_path, "result_file")
    with pytest.raises(ValueError, match="real directory"):
        _safe_working_directory(file_path, tmp_path)


def test_junit_validation_rejects_malformed_empty_unnamed_duplicate_and_failed_cases(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.xml"
    malformed.write_text("<testsuite>", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JUnit"):
        _junit_cases(malformed)

    empty = tmp_path / "empty.xml"
    empty.write_text("<testsuite />", encoding="utf-8")
    with pytest.raises(ValueError, match="no test cases"):
        _junit_cases(empty)

    unnamed = tmp_path / "unnamed.xml"
    unnamed.write_text("<testsuite><testcase /></testsuite>", encoding="utf-8")
    with pytest.raises(ValueError, match="without a name"):
        _junit_cases(unnamed)

    duplicate = tmp_path / "duplicate.xml"
    duplicate.write_text(
        '<testsuite><testcase classname="tests.x" name="test_y" />'
        '<testcase classname="tests.x" name="test_y" /></testsuite>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate testcase identity"):
        _junit_cases(duplicate)

    failed = tmp_path / "failed.xml"
    failed.write_text(
        '<testsuite><testcase classname="tests.x" name="test_y"><failure /></testcase></testsuite>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="failed or errored"):
        _junit_cases(failed)
