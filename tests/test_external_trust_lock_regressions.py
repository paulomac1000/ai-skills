"""Regression coverage for fail-closed external trust-lock input parsing."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"


def _load_external_trust_lock() -> ModuleType:
    if str(CONTRACTS) not in sys.path:
        sys.path.insert(0, str(CONTRACTS))
    path = CONTRACTS / "validate_external_trust_lock.py"
    spec = importlib.util.spec_from_file_location("external_trust_lock_regression", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_external_trust_lock_rejects_scalar_document_without_traceback(tmp_path: Path) -> None:
    validator = _load_external_trust_lock()
    lock = tmp_path / "trusted-executable-sources.lock.yaml"
    lock.write_text("not-a-mapping\n", encoding="utf-8")

    findings = validator.validate_external_lock(
        lock.name,
        candidate_root=tmp_path,
        authority_root=tmp_path,
        source_id="ai-skills",
        expected_repository="trusted/ai-skills",
        expected_revision="a" * 40,
    )

    assert findings == ["candidate trust lock must contain a mapping"]
