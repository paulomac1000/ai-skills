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


def _passing_xml(identity: str = "tests.test_execution::test_exact") -> str:
    classname, name = identity.split("::", 1)
    return (
        '<testsuite tests="1" failures="0" errors="0" skipped="0">'
        f'<testcase classname="{classname}" name="{name}" />'
        "</testsuite>"
    )


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"directory symlinks are unavailable: {exc}")


def test_runner_records_exact_argv_working_directory_and_result_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "write_result.py"
    xml = _passing_xml()
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
    expected_digest = "sha256:" + hashlib.sha256((tmp_path / "result.xml").read_bytes()).hexdigest()
    assert result["digest"] == expected_digest
    assert result["test_cases"] == [{"identity": "tests.test_execution::test_exact", "status": "passed"}]


def test_runner_accepts_explicit_regular_working_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    working_directory = tmp_path / "work"
    working_directory.mkdir()
    script = tmp_path / "write_result.py"
    _writer_script(script, _passing_xml())
    output = tmp_path / "record.json"
    assert (
        main(
            [
                "--execution-id",
                "regular-directory",
                "--working-directory",
                str(working_directory),
                "--result-file",
                "result.xml",
                "--output",
                str(output),
                "--",
                sys.executable,
                str(script),
            ]
        )
        == 0
    )
    assert json.loads(output.read_text(encoding="utf-8"))["working_directory"] == "work"


def test_runner_rejects_working_directory_symlink_to_repository_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "linked"
    _symlink_or_skip(link, real)
    with pytest.raises(ValueError, match="symlink components"):
        main(
            [
                "--execution-id",
                "linked-inside",
                "--working-directory",
                str(link),
                "--result-file",
                "result.xml",
                "--output",
                "record.json",
                "--",
                sys.executable,
                "-c",
                "pass",
            ]
        )


def test_runner_rejects_working_directory_symlink_outside_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    link = tmp_path / "linked-outside"
    _symlink_or_skip(link, tmp_path.parent)
    with pytest.raises(ValueError, match="symlink components"):
        main(
            [
                "--execution-id",
                "linked-outside",
                "--working-directory",
                str(link),
                "--result-file",
                "result.xml",
                "--output",
                "record.json",
                "--",
                sys.executable,
                "-c",
                "pass",
            ]
        )


def test_runner_rejects_result_file_outside_working_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    working_directory = tmp_path / "work"
    working_directory.mkdir()
    (tmp_path / "outside.xml").write_text(_passing_xml(), encoding="utf-8")
    with pytest.raises(ValueError, match="repository boundary"):
        main(
            [
                "--execution-id",
                "outside-result",
                "--working-directory",
                str(working_directory),
                "--result-file",
                "../outside.xml",
                "--output",
                "record.json",
                "--",
                sys.executable,
                "-c",
                "pass",
            ]
        )


def test_runner_rejects_failed_junit_after_successful_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "write_result.py"
    xml = (
        '<testsuite tests="1" failures="1" errors="0" skipped="0">'
        '<testcase classname="tests.test_execution" name="test_exact"><failure /></testcase>'
        "</testsuite>"
    )
    _writer_script(script, xml)
    with pytest.raises(ValueError, match="failed or errored"):
        main(
            [
                "--execution-id",
                "failed-junit",
                "--result-file",
                "result.xml",
                "--output",
                "record.json",
                "--",
                sys.executable,
                str(script),
            ]
        )


def test_runner_rejects_errored_junit_after_successful_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    script = tmp_path / "write_result.py"
    xml = (
        '<testsuite tests="1" failures="0" errors="1" skipped="0">'
        '<testcase classname="tests.test_execution" name="test_exact"><error /></testcase>'
        "</testsuite>"
    )
    _writer_script(script, xml)
    with pytest.raises(ValueError, match="failed or errored"):
        main(
            [
                "--execution-id",
                "errored-junit",
                "--result-file",
                "result.xml",
                "--output",
                "record.json",
                "--",
                sys.executable,
                str(script),
            ]
        )


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
