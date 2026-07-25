"""Contract for canonical machine-bound evidence reports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from contracts.write_evidence_report import main

SHA = "a" * 40


def _junit(path: Path, *, failed: bool = False) -> None:
    outcome = '<failure message="boom" />' if failed else ""
    path.write_text(
        f'<testsuite tests="1" failures="{int(failed)}" errors="0" skipped="0">'
        f'<testcase classname="tests.test_contract" name="test_rule">{outcome}</testcase>'
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


def _plan(path: Path) -> None:
    path.write_text(
        """
schema_version: 1
profiles:
  rules:
    - kind: rule
      subject: mcp.authorization
      command: python -m pytest tests/test_contract.py
      selectors: ["*test_rule"]
""".lstrip(),
        encoding="utf-8",
    )


def _arguments(tmp_path: Path) -> list[str]:
    junit = tmp_path / "results.xml"
    provider = tmp_path / "provider.json"
    plan = tmp_path / "plan.yaml"
    _junit(junit)
    _provider(provider)
    _plan(plan)
    return [
        "--repository",
        "owner/repository",
        "--source-head-sha",
        SHA,
        "--tested-checkout-sha",
        SHA,
        "--merge-sha",
        "b" * 40,
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
        "--result-file",
        str(junit),
        "--provider-metadata-file",
        str(provider),
        "--output",
        str(tmp_path / "evidence/report.json"),
    ]


def test_writer_emits_canonical_machine_bound_report(tmp_path: Path) -> None:
    arguments = _arguments(tmp_path)
    assert main(arguments) == 0
    output = tmp_path / "evidence/report.json"
    raw = output.read_bytes()
    document = json.loads(raw)
    canonical = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()
    assert raw == canonical
    assert document["schema_version"] == 2
    assert document["source_head_sha"] == SHA
    assert document["tested_checkout_sha"] == SHA
    assert document["producer"] == {"provider": "github", "login": "author", "id": 40}
    claim = document["claims"][0]
    assert claim["result"] == "passed"
    assert claim["exit_status"] == 0
    assert claim["test_cases"] == ["tests.test_contract::test_rule"]
    assert claim["result_digests"] == [document["results"][0]["digest"]]

    second = tmp_path / "second.json"
    repeat = list(arguments)
    repeat[-1] = str(second)
    assert main(repeat) == 0
    assert hashlib.sha256(raw).digest() == hashlib.sha256(second.read_bytes()).digest()


def test_writer_rejects_merge_checkout_and_failed_or_unmapped_results(tmp_path: Path) -> None:
    arguments = _arguments(tmp_path)
    tested_index = arguments.index("--tested-checkout-sha") + 1
    arguments[tested_index] = "b" * 40
    with pytest.raises(ValueError, match="must equal source_head_sha"):
        main(arguments)

    arguments = _arguments(tmp_path)
    junit = Path(arguments[arguments.index("--result-file") + 1])
    _junit(junit, failed=True)
    with pytest.raises(ValueError, match="failed or errored"):
        main(arguments)

    arguments = _arguments(tmp_path)
    plan = Path(arguments[arguments.index("--claims-plan") + 1])
    plan.write_text(
        """
schema_version: 1
profiles:
  rules:
    - kind: rule
      subject: x
      command: python -m pytest
      selectors: ["*does-not-exist"]
""".lstrip(),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="matched no passed"):
        main(arguments)
