"""Contract for canonical machine-readable evidence reports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from contracts.write_evidence_report import main

SHA = "a" * 40


def test_writer_emits_canonical_report(tmp_path: Path) -> None:
    claims = tmp_path / "claims.json"
    claims.write_text(
        json.dumps(
            [
                {
                    "kind": "rule",
                    "subject": "mcp.authorization",
                    "result": "passed",
                    "command_digest": "sha256:" + "b" * 64,
                }
            ]
        ),
        encoding="utf-8",
    )
    output = tmp_path / "evidence/report.json"
    assert (
        main(
            [
                "--repository",
                "owner/repository",
                "--revision",
                SHA,
                "--run-id",
                "10",
                "--check-run-id",
                "20",
                "--workflow-path",
                ".github/workflows/ci.yml",
                "--workflow-name",
                "CI",
                "--event",
                "pull_request",
                "--job-name",
                "python",
                "--lane",
                "python-compatibility",
                "--claims-file",
                str(claims),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    raw = output.read_bytes()
    assert raw.endswith(b"\n")
    assert b" " not in raw
    document = json.loads(raw)
    assert document["revision"] == SHA
    assert document["claims"][0]["subject"] == "mcp.authorization"
    assert hashlib.sha256(raw).hexdigest()


def test_writer_rejects_non_passed_claim(tmp_path: Path) -> None:
    claims = tmp_path / "claims.json"
    claims.write_text('[{"kind":"rule","subject":"x","result":"failed"}]', encoding="utf-8")
    with pytest.raises(ValueError, match="must be passed"):
        main(
            [
                "--repository",
                "owner/repository",
                "--revision",
                SHA,
                "--run-id",
                "10",
                "--check-run-id",
                "20",
                "--workflow-path",
                ".github/workflows/ci.yml",
                "--workflow-name",
                "CI",
                "--event",
                "pull_request",
                "--job-name",
                "python",
                "--lane",
                "python-compatibility",
                "--claims-file",
                str(claims),
                "--output",
                str(tmp_path / "report.json"),
            ]
        )
