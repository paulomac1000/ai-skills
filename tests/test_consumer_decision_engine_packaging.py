"""The advertised MCP consumer decision engine must be a standalone required artifact."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "skills/mcp-server-consumer/tools/decision_engine.py"
MANIFEST = ROOT / "skills/mcp-server-consumer/manifest.yaml"


def test_decision_engine_imports_when_distributed_without_sibling_modules(tmp_path: Path) -> None:
    isolated = tmp_path / "decision_engine.py"
    shutil.copyfile(SOURCE, isolated)

    spec = importlib.util.spec_from_file_location("isolated_consumer_decision_engine", isolated)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    assert module.evaluate_decision("READ", False, "general") is module.Decision.INVOKE
    assert module.should_retry(
        error_code="TIMEOUT",
        attempt=0,
        operation_idempotent=True,
        response_retryable=True,
    )


def test_consumer_manifest_requires_the_canonical_engine_and_no_duplicate_remains() -> None:
    document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    required = document.get("required")

    assert isinstance(required, list)
    assert "tools/decision_engine.py" in required
    assert not (SOURCE.parent / "decision_engine_legacy.py").exists()
