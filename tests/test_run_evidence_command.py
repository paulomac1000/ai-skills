"""Exact command execution records bind argv to unique JUnit bytes."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from contracts.run_evidence_command import main


def _writer_script(path: Path, xml: str, exit_status: int = 0) -> None:
    path.write_text(
        "from pathlib import Path\n"
        f"Path('result.xml').write_text({xml!r}, encoding='utf-8')\n"
        f"raise SystemExit({exit_status})\n",
        encoding="utf-8",
    )


def test_runner_records_exact_argv_working_directory_and_result_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "write_result.py"
    xml = (
        '<testsuite tests="1" failures="0" errors="0" skipped="0">'
        '<testcase classname="tests.test_execution" name="test_exact" />'
        "</testsuite>"
    )
    _writer_script(script, xml)
    output = tmp_path / "evidence/executions/exact.json"
    argv = [
        "--execution-id",
        "exact",
        "--result-file",
        "result.xml",
        "--output",
        str(output),
        "--",
        sys.executable,
        str(script),
    ]
    assert main(argv) == 0
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["format"] == "ai-skills-execution-record"
    assert record["argv"] == [sys.executable, str(script)]
    assert record["working_directory"] == "."
    assert record["exit_status"] == 0
    result = record["results"][0]
    assert result["digest"] == "sha256:" + hashlib.sha256((tmp_path / "result.xml").read_bytes()).hexdigest()
    assert result["test_cases"] == [{"identity": "tests.test_execution::test_exact", "status": "passed"}]


def test_runner_rejects_duplicate_testcase_identities(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "write_result.py"
    xml = (
        '<testsuite tests="2" failures="0" errors="0" skipped="0">'
        '<testcase classname="tests.test_execution" name="test_exact" />'
        '<testcase classname="tests.test_execution" name="test_exact" />'
        "</testsuite>"
    )
    _writer_script(script, xml)
    with pytest.raises(ValueError, match="duplicate testcase identity"):
        main(
            [
                "--execution-id",
                "duplicate",
                "--result-file",
                "result.xml",
                "--output",
                "record.json",
                "--",
                sys.executable,
                str(script),
            ]
        )


def test_runner_preserves_nonzero_exit_status_in_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "write_result.py"
    _writer_script(script, '<testsuite tests="0" failures="0" errors="0" skipped="0" />', exit_status=7)
    output = tmp_path / "record.json"
    assert (
        main(
            [
                "--execution-id",
                "failed-command",
                "--result-file",
                "result.xml",
                "--output",
                str(output),
                "--",
                sys.executable,
                str(script),
            ]
        )
        == 7
    )
    assert json.loads(output.read_text(encoding="utf-8"))["exit_status"] == 7
