"""External adoption must parse candidate assessments from immutable bounded snapshots."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"


def _validator() -> ModuleType:
    if str(CONTRACTS) not in sys.path:
        sys.path.insert(0, str(CONTRACTS))
    path = CONTRACTS / "validate_external_adoption.py"
    spec = importlib.util.spec_from_file_location("external_adoption_assessment_snapshot", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_candidate_assessment_is_not_reread_by_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = _validator()
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    assessment = candidate / "assessment.yaml"
    assessment.write_bytes(b"schema_version: 1\n")
    original_read_text = Path.read_text

    def forbid_candidate_path_read(path: Path, *args: object, **kwargs: object) -> str:
        if path == assessment:
            raise AssertionError("candidate assessment was reread through Path.read_text")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", forbid_candidate_path_read)

    document = validator._load_mapping(candidate, "assessment.yaml")

    assert dict(document) == {"schema_version": 1}


def test_external_adoption_cli_reads_assessment_from_candidate_git_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validator = _validator()
    candidate = tmp_path / "candidate"
    authority = tmp_path / "authority"
    candidate.mkdir()
    authority.mkdir()
    (candidate / "assessment.yaml").write_text("schema_version: 999\n", encoding="utf-8")
    revision = "a" * 40
    captured: dict[str, object] = {}

    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setattr(validator.trusted_sources, "_verify_candidate_identity", lambda *_args, **_kwargs: None)

    def immutable_candidate_text(root: Path, observed_revision: str, relative: str, *, max_bytes: int) -> str:
        assert root == candidate.resolve()
        assert observed_revision == revision
        assert relative == "assessment.yaml"
        assert max_bytes == validator.MAX_DOCUMENT_BYTES
        return "schema_version: 1\n"

    def capture_validation(assessment, **_kwargs):
        captured["assessment"] = dict(assessment)
        return []

    monkeypatch.setattr(validator.trusted_sources, "_authority_text", immutable_candidate_text)
    monkeypatch.setattr(validator, "validate_external_adoption", capture_validation)

    result = validator.main(
        [
            "assessment.yaml",
            "--candidate-root",
            str(candidate),
            "--candidate-repository",
            "acme/project",
            "--candidate-revision",
            revision,
            "--authority-root",
            str(authority),
            "--authority-repository",
            "trusted/ai-skills",
            "--authority-revision",
            "b" * 40,
            "--authority-workflow-path",
            ".github/workflows/consumer-acceptance.yml",
        ]
    )

    assert result == 0
    assert captured["assessment"] == {"schema_version": 1}
