"""Wave 2 regression coverage for canonical MCP consumer runtime identity references."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills/mcp-server-consumer/tools/runtime_identity_ref.py"
STANDARD = ROOT / "skills/mcp-server-consumer/STANDARD.md"
MANIFEST = ROOT / "skills/mcp-server-consumer/manifest.yaml"
CANONICAL_SCHEMA = ROOT / "contracts/runtime-identity.schema.json"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("wave2_runtime_identity_ref", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _identity(**overrides: object) -> dict[str, object]:
    identity: dict[str, object] = {
        "schema_version": 1,
        "runtime_id": "inventory-mcp",
        "instance_generation": "generation-42",
        "source_revision": "a" * 40,
        "artifact_digest": "sha256:" + "b" * 64,
        "config_revision": "config-7",
        "provenance_refs": ["deployment:inventory-mcp:42"],
    }
    identity.update(overrides)
    return identity


def test_runtime_identity_ref_reuses_canonical_schema_without_second_dto() -> None:
    runtime_identity = _load()
    identity = _identity()

    assert runtime_identity.RUNTIME_IDENTITY_SCHEMA.resolve() == CANONICAL_SCHEMA.resolve()
    assert runtime_identity.validate_runtime_identity_ref(identity) is identity
    assert runtime_identity.runtime_instance_key(identity) == ("inventory-mcp", "generation-42")
    assert not hasattr(runtime_identity, "RuntimeIdentity")


@pytest.mark.parametrize(
    "legacy",
    [
        {"schema_version": 1, "server_id": "inventory-mcp", "instance_generation": "generation-42"},
        {"schema_version": 1, "runtime_id": "inventory-mcp", "generation": "generation-42"},
        {
            "schema_version": 1,
            "runtime_id": "inventory-mcp",
            "instance_generation": "generation-42",
            "provenance": {"source_revision": "a" * 40},
        },
    ],
)
def test_runtime_identity_ref_rejects_alternate_identity_representations(legacy: dict[str, object]) -> None:
    runtime_identity = _load()
    with pytest.raises(ValueError, match="canonical runtime identity"):
        runtime_identity.validate_runtime_identity_ref(legacy)


def test_runtime_identity_ref_rejects_bad_canonical_provenance() -> None:
    runtime_identity = _load()
    with pytest.raises(ValueError, match="canonical runtime identity"):
        runtime_identity.validate_runtime_identity_ref(_identity(source_revision="short"))


def test_consumer_standard_and_manifest_publish_only_the_canonical_reference_tool() -> None:
    standard = STANDARD.read_text(encoding="utf-8")
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))

    assert "## Runtime identity references" in standard
    assert "runtime-identity.schema.json" in standard
    assert "`server_id`, `generation`, or a synthetic `provenance`" in standard
    assert "tools/runtime_identity_ref.py" in manifest["required"]
