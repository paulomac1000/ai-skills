"""Regressions for feedback-ledger selector collection policy."""

from __future__ import annotations

from pathlib import Path

import yaml

from contracts.validate_consumer_feedback import validate_registry


def test_feedback_selector_respects_repository_pytest_addopts(tmp_path: Path) -> None:
    (tmp_path / "contracts").mkdir()
    (tmp_path / "skills/example").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "contracts/consumer-canaries.yaml").write_text(
        "schema_version: 1\ncanaries: []\n",
        encoding="utf-8",
    )
    (tmp_path / "skills/example/guide.md").write_text("# Guide\n\n## Owner\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        "addopts = \"-m 'not excluded'\"\n"
        "markers = [\"excluded: excluded from the authoritative gate\"]\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/test_filtered.py").write_text(
        "import pytest\n\n"
        "@pytest.mark.excluded\n"
        "def test_filtered():\n"
        "    assert True\n",
        encoding="utf-8",
    )
    registry = {
        "schema_version": 1,
        "incidents": [
            {
                "id": "field.repository-collection-policy",
                "source_kind": "field-report",
                "failure_mode": "A selector resolved only after overriding the repository test-runner policy.",
                "generalized_invariant": "Promoted regressions must be collected by the repository-configured pytest gate.",
                "canonical_owner": "skills/example/guide.md#owner",
                "regression_selectors": ["tests/test_filtered.py::test_filtered"],
                "status": "implemented",
            }
        ],
    }
    path = tmp_path / "registry.yaml"
    path.write_text(yaml.safe_dump(registry), encoding="utf-8")

    findings = validate_registry(path, repository_root=tmp_path)

    expected = (
        "field.repository-collection-policy: regression selector is not collectable by pytest: "
        "tests/test_filtered.py::test_filtered"
    )
    matching = [finding for finding in findings if finding.startswith(expected)]
    assert len(matching) == 1
