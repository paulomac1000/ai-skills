"""Regression tests for framework-aware scanner and reviewer finding triage."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "skills/ci-cd-architect/references/finding-triage.md"


def test_finding_triage_is_packaged_by_ci_skill() -> None:
    manifest = yaml.safe_load((ROOT / "skills/ci-cd-architect/manifest.yaml").read_text(encoding="utf-8"))
    assert "references/finding-triage.md" in manifest["required"]
    assert REFERENCE.is_file()


def test_triage_requires_framework_call_path_reproduction_and_regression() -> None:
    content = REFERENCE.read_text(encoding="utf-8")
    for required in (
        "exact framework, version, call path",
        "production entrypoint and whether the path is reachable",
        "standard-violation",
        "implementation-defect",
        "compatibility-issue",
        "tool-false-positive",
        "fails_before_fix",
        "passes_after_fix",
        "Do not call a finding false positive merely because the proposed patch is wrong",
        "Never disable a rule repository-wide",
    ):
        assert required in content


def test_triage_rejects_mechanical_cross_framework_remediation() -> None:
    content = REFERENCE.read_text(encoding="utf-8")
    assert "Do not infer a framework from method names" in content
    assert "Do not translate one ecosystem's remediation idiom into another" in content
    assert "proposed patch is not sufficient evidence" in content
