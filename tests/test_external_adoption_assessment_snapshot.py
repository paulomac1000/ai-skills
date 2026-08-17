"""External adoption must parse candidate assessments from the bounded stable-read snapshot."""

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
