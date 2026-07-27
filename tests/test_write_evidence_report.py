"""Canonical reports bind claims to exact execution and JUnit records."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from contracts.write_evidence_report import main

SHA = "a" * 40


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _command_digest(argv: list[str], cwd: str = ".") -> str:
    payload = json.dumps(
        {"argv": argv, "working_directory": cwd},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _junit(path: Path, identity: str = "tests.test_contract::test_rule", *, failed: bool = False) -> None:
    classname, name = identity.split("::", 1)
    outcome = '<failure message="boom" />' if failed else ""
    path.write_text(
        f'<testsuite tests="1" failures="{int(failed)}" errors="0" skipped="0">'
        f'<testcase classname="{classname}" name="{name}">{outcome}</testcase>'
        "</testsuite>",
        encoding="utf-8",
    )


def _provider(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "run": {
                    "id": 10,
                    "head_sha": SHA,
                    "workflow_id": 30,
                    "path": ".github/workflows/ci.yml",
                    "name": "CI",
                    "event": "pull_request",
                    "actor": {"login": "author", "id": 40},
                },
                "job": {
                    "id": 20,
                    "run_id": 10,
                    "name": "python",
                    "check_run_url": "https://api.github.com/repos/owner/repository/check-runs/25",
                },
            }
        ),
        encoding="utf-8",
    )


def _record(
    path: Path,
    results: list[tuple[Path, str]],
    execution_id: str = "rules",
    working_directory: str = ".",
) -> None:
    argv = ["python", "-m", "pytest", "tests/test_contract.py"]
    path.write_text(
        json.dumps(
            {
                "format": "ai-skills-execution-record",
                "execution_id": execution_id,
                "argv": argv,
                "working_directory": working_directory,
                "command_digest": _command_digest(argv, working_directory),
                "exit_status": 0,
                "results": [
                    {
                        "path": result.name,
                        "format": "junit",
                        "digest": _digest(result),
                        "test_cases": [{"identity": identity, "status": "passed"}],
                    }
                    for result, identity in results
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )


def _plan(
    path: Path,
    *,
    selector: str = "*test_rule",
    result_file: str = "results.xml",
    content_path: str | None = None,
) -> None:
    content_line = "" if content_path is None else f"      content_path: {json.dumps(content_path)}\n"
    path.write_text(
        "format: ai-skills-claim-plan\n"
        "profiles:\n"
        "  rules:\n"
        "    - kind: rule\n"
        "      subject: mcp.authorization\n"
        "      execution_id: rules\n"
        f'      selectors: ["{selector}"]\n'
        f'      result_files: ["{result_file}"]\n'
        f"{content_line}",
        encoding="utf-8",
    )


def _arguments(tmp_path: Path) -> list[str]:
    junit = tmp_path / "results.xml"
    provider = tmp_path / "provider.json"
    record = tmp_path / "record.json"
    plan = tmp_path / "plan.yaml"
    _junit(junit)
    _provider(provider)
    _record(record, [(junit, "tests.test_contract::test_rule")])
    _plan(plan)
    return [
        "--repository",
        "owner/repository",
        "--source-head-sha",
        SHA,
        "--tested-checkout-sha",
        SHA,
        "--run-id",
        "10",
        "--workflow-path",
        ".github/workflows/ci.yml",
        "--workflow-name",
        "CI",
        "--event",
        "pull_request",
        "--job-name",
        "python",
        "--lane",
        "repository-rules",
        "--claims-plan",
        str(plan),
        "--claims-profile",
        "rules",
        "--execution-record",
        str(record),
        "--provider-metadata-file",
        str(provider),
        "--output",
        str(tmp_path / "evidence/report.json"),
    ]


def test_writer_emits_execution_bound_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    arguments = _arguments(tmp_path)
    assert main(arguments) == 0
    document = json.loads((tmp_path / "evidence/report.json").read_text(encoding="utf-8"))
    assert document["format"] == "ai-skills-evidence-report"
    assert document["evidence_role"] == "diagnostic"
    execution = document["executions"][0]
    claim = document["claims"][0]
    assert claim["execution_id"] == execution["execution_id"] == "rules"
    assert claim["command_digest"] == execution["command_digest"]
    assert claim["result_bindings"] == [
        {
            "result_path": "results.xml",
            "result_digest": document["results"][0]["digest"],
            "test_cases": [{"identity": "tests.test_contract::test_rule", "status": "passed"}],
        }
    ]


def test_writer_scopes_claim_to_selected_result_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    arguments = _arguments(tmp_path)
    first = tmp_path / "results.xml"
    unrelated = tmp_path / "unrelated.xml"
    _junit(unrelated, "tests.test_other::test_other")
    record = Path(arguments[arguments.index("--execution-record") + 1])
    _record(
        record,
        [
            (first, "tests.test_contract::test_rule"),
            (unrelated, "tests.test_other::test_other"),
        ],
    )
    assert main(arguments) == 0
    claim = json.loads((tmp_path / "evidence/report.json").read_text(encoding="utf-8"))["claims"][0]
    assert [binding["result_path"] for binding in claim["result_bindings"]] == ["results.xml"]


def test_writer_rejects_tampered_recorded_testcase(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    arguments = _arguments(tmp_path)
    record = Path(arguments[arguments.index("--execution-record") + 1])
    document = json.loads(record.read_text(encoding="utf-8"))
    document["results"][0]["test_cases"][0]["identity"] = "tests.test_contract::not_executed"
    record.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="do not match JUnit bytes"):
        main(arguments)


def test_writer_rejects_failed_junit_with_matching_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    arguments = _arguments(tmp_path)
    junit = tmp_path / "results.xml"
    _junit(junit, failed=True)
    record = Path(arguments[arguments.index("--execution-record") + 1])
    _record(record, [(junit, "tests.test_contract::test_rule")])
    with pytest.raises(ValueError, match="failed or errored"):
        main(arguments)


def test_writer_rejects_absolute_content_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    arguments = _arguments(tmp_path)
    content = tmp_path / "content.txt"
    content.write_text("content", encoding="utf-8")
    plan = Path(arguments[arguments.index("--claims-plan") + 1])
    _plan(plan, content_path=str(content.resolve()))
    with pytest.raises(ValueError, match="relative POSIX"):
        main(arguments)


def test_writer_rejects_parent_traversal_content_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    arguments = _arguments(tmp_path)
    plan = Path(arguments[arguments.index("--claims-plan") + 1])
    _plan(plan, content_path="../outside.txt")
    with pytest.raises(ValueError, match="safe relative POSIX"):
        main(arguments)


def test_writer_rejects_symlink_content_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    arguments = _arguments(tmp_path)
    target = tmp_path / "content.txt"
    target.write_text("content", encoding="utf-8")
    link = tmp_path / "content-link.txt"
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"file symlinks are unavailable: {exc}")
    plan = Path(arguments[arguments.index("--claims-plan") + 1])
    _plan(plan, content_path=link.name)
    with pytest.raises(ValueError, match="symlink components"):
        main(arguments)


def test_writer_rejects_result_path_collision_with_different_digests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    arguments = _arguments(tmp_path)
    first_directory = tmp_path / "first"
    second_directory = tmp_path / "second"
    first_directory.mkdir()
    second_directory.mkdir()
    first = first_directory / "results.xml"
    second = second_directory / "results.xml"
    _junit(first, "tests.test_contract::test_rule")
    _junit(second, "tests.test_other::test_other")

    first_record = Path(arguments[arguments.index("--execution-record") + 1])
    second_record = tmp_path / "record-other.json"
    _record(
        first_record,
        [(first, "tests.test_contract::test_rule")],
        execution_id="rules",
        working_directory="first",
    )
    _record(
        second_record,
        [(second, "tests.test_other::test_other")],
        execution_id="other",
        working_directory="second",
    )
    arguments.extend(["--execution-record", str(second_record)])
    with pytest.raises(ValueError, match=r"result path collision.*rules.*other"):
        main(arguments)
