"""Wave 2 regressions for provider-profile public schema compatibility."""

from __future__ import annotations

import fnmatch
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import yaml

ROOT = Path(__file__).resolve().parents[1]
ARCHITECT = ROOT / "skills/mcp-server-architect"
TOOL = ARCHITECT / "tools/provider_schema_compat.py"
STANDARD = ARCHITECT / "STANDARD.md"
MANIFEST = ARCHITECT / "manifest.yaml"
FIXTURES = ROOT / "tests/fixtures/provider_schema_compat"
QUALITY_TARGETS = ROOT / "scripts/quality_targets.py"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _profile(compat: ModuleType, raw: dict[str, object]) -> object:
    return compat.ProviderProfile(
        provider=raw["provider"],
        contractRevision=raw["contractRevision"],
        schemaRestrictions=raw["schemaRestrictions"],
        sourceEvidence=tuple(raw["sourceEvidence"]),
    )


def _covered(targets: tuple[str, ...], path: str) -> bool:
    return any(
        path == target
        or path.startswith(f"{target.rstrip('/')}/")
        or ("*" in target and fnmatch.fnmatch(path, target))
        for target in targets
    )


def test_recursive_nullable_object_array_fixture_is_provider_incompatible() -> None:
    compat = _load("wave2_provider_schema_nullable", TOOL)
    schema = json.loads((FIXTURES / "nullable_object_array.json").read_text(encoding="utf-8"))
    raw_profile = json.loads((FIXTURES / "restrictive_profile.json").read_text(encoding="utf-8"))
    result = compat.check_provider_schema(schema, _profile(compat, raw_profile))

    assert result.compatible is False
    assert result.activation_allowed is False
    assert any("$.properties.options:nullable_object_array_unsupported" in item for item in result.violations)
    assert any("$.properties.options.properties.tags:nullable_object_array_unsupported" in item for item in result.violations)


def test_unknown_provider_subset_never_optimistically_activates() -> None:
    compat = _load("wave2_provider_schema_unknown", TOOL)
    profile = compat.ProviderProfile(
        provider="unknown-provider",
        contractRevision="unknown",
        schemaRestrictions={},
        sourceEvidence=("unresolved-provider-contract",),
    )
    result = compat.check_provider_schema({"type": "object", "properties": {}}, profile)

    assert result.compatible is False
    assert result.activation_allowed is False
    assert result.violations[0].startswith("profile_unknown:missing=")


def test_recursive_checker_covers_unions_defaults_refs_and_additional_properties() -> None:
    compat = _load("wave2_provider_schema_keywords", TOOL)
    raw_profile = json.loads((FIXTURES / "restrictive_profile.json").read_text(encoding="utf-8"))
    schema = {
        "type": "object",
        "properties": {
            "choice": {"oneOf": [{"type": "string"}, {"$ref": "#/$defs/x"}], "default": "x"},
        },
        "additionalProperties": {"type": ["string", "null"]},
        "$defs": {"x": {"type": "string"}},
    }
    result = compat.check_provider_schema(schema, _profile(compat, raw_profile))
    joined = "\n".join(result.violations)
    assert "oneOf_unsupported" in joined
    assert "$ref_unsupported" in joined
    assert "default_unsupported" in joined
    assert "additionalProperties_unsupported" in joined
    assert "type_union_unsupported" in joined


def test_provider_profile_contract_is_documented_required_and_quality_gated() -> None:
    text = STANDARD.read_text(encoding="utf-8")
    for field in ("provider", "contract revision", "schema restrictions", "source evidence"):
        assert field in text.lower()

    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert "tools/provider_schema_compat.py" in manifest["required"]
    inventories = _load("wave2_quality_targets_provider", QUALITY_TARGETS)
    path = "skills/mcp-server-architect/tools/provider_schema_compat.py"
    for targets in (
        inventories.QUALITY_PATHS,
        inventories.TYPE_PATHS,
        inventories.BANDIT_PATHS,
        inventories.POLICY_COVERAGE_PATHS,
    ):
        assert _covered(targets, path)
