"""Wave 2 regressions for canonical layered outcomes in generated MCP servers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
ARCHITECT = ROOT / "skills/mcp-server-architect"
TOOL = ARCHITECT / "tools/action_outcome.py"
GENERATOR = ARCHITECT / "tools/generate_python_server_impl.py"
MANIFEST = ARCHITECT / "manifest.yaml"
ACTION_SCHEMA = ROOT / "contracts/action-outcome.schema.json"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _completed_outcome() -> dict[str, object]:
    return {
        "schema_version": 1,
        "transport": "succeeded",
        "execution": "succeeded",
        "side_effect": "confirmed",
        "artifact": "none",
        "verification": "not_run",
        "disposition": "completed",
        "safe_to_retry": "no",
    }


def test_action_outcome_tool_reuses_canonical_schema_and_semantics() -> None:
    action_outcome = _load("wave2_action_outcome", TOOL)
    outcome = _completed_outcome()

    assert action_outcome.ACTION_OUTCOME_SCHEMA.resolve() == ACTION_SCHEMA.resolve()
    assert action_outcome.validate_layered_outcome(outcome) is outcome

    invalid = dict(outcome, side_effect="unknown")
    with pytest.raises(ValueError, match="canonical layered outcome"):
        action_outcome.validate_layered_outcome(invalid)


def test_python_generator_emits_canonical_layered_write_and_simple_read() -> None:
    generator = _load("wave2_python_generator", GENERATOR)
    generated = generator.project_files("wave2_server", "Wave 2 Server")
    generator.validate_generated_project(generated, "wave2_server")

    action_schema_path = "src/wave2_server/contracts/action-outcome.schema.json"
    capability_schema_path = "src/wave2_server/contracts/capability-manifest.schema.json"
    put_path = "src/wave2_server/capabilities/put_item.json"
    list_path = "src/wave2_server/capabilities/list_items.json"

    assert json.loads(generated[action_schema_path]) == json.loads(ACTION_SCHEMA.read_text(encoding="utf-8"))
    assert capability_schema_path in generated
    assert json.loads(generated[put_path])["outcome_contract"] == "layered"
    assert json.loads(generated[list_path])["outcome_contract"] == "simple"

    kernel = generated["src/wave2_server/kernel.py"]
    assert '"outcome": {' in kernel
    assert '"side_effect": "confirmed"' in kernel
    assert '"disposition": "completed"' in kernel
    assert '"safe_to_retry": "no"' in kernel

    Draft202012Validator(json.loads(generated[action_schema_path])).validate(_completed_outcome())


def test_architect_manifest_requires_canonical_action_outcome_tool() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert "tools/action_outcome.py" in manifest["required"]
