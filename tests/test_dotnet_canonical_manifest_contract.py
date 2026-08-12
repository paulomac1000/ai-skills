"""Cross-language capability-manifest parity checks for the .NET baseline."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "skills/mcp-server-architect/tools/generate_dotnet_server.py"
JSON_PROPERTY = re.compile(r'JsonPropertyName\("([a-z0-9_]+)"\)')


def load_generator():
    spec = importlib.util.spec_from_file_location(
        "dotnet_canonical_manifest_generator",
        GENERATOR,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dotnet_generator_copies_the_canonical_schema_verbatim() -> None:
    generator = load_generator()
    files = generator.project_files("Acme", "Acme MCP")
    generated = files["contracts/capability-manifest.schema.json"]
    canonical = (ROOT / "contracts/capability-manifest.schema.json").read_text(encoding="utf-8")
    assert generated == canonical.rstrip() + "\n"


def test_dotnet_canonical_projection_covers_every_required_schema_field() -> None:
    schema = json.loads((ROOT / "contracts/capability-manifest.schema.json").read_text(encoding="utf-8"))
    adapter = (
        ROOT / "skills/mcp-server-architect/tools/dotnet-template/src/"
        "__NAMESPACE__.Mcp.Server/CanonicalCapabilityManifest.cs.template"
    ).read_text(encoding="utf-8")
    observed = set(JSON_PROPERTY.findall(adapter))
    assert set(schema["required"]) <= observed

    for required in (
        "ModuleInitializer",
        "GetManifestResourceStream",
        '"capability-manifest.schema.json"',
        'GetProperty("required")',
        'GetProperty("properties")',
        "ValidateRequiredFields",
        "ValidateNoUnknownFields",
        "ValidateSchemaEnums",
        "ValidateSemantics",
        '"arguments-digest"',
    ):
        assert required in adapter


def test_dotnet_projection_uses_only_canonical_enum_values_and_approval_fields() -> None:
    adapter = (
        ROOT / "skills/mcp-server-architect/tools/dotnet-template/src/"
        "__NAMESPACE__.Mcp.Server/CanonicalCapabilityManifest.cs.template"
    ).read_text(encoding="utf-8")

    for canonical in (
        '"environment-dependent"',
        '"nondeterministic"',
        '"bounded-long"',
        '"local"',
        '"principal-target"',
        '"capability"',
        '"server-side"',
        'JsonPropertyName("record_required")',
        'JsonPropertyName("record_ttl_seconds")',
    ):
        assert canonical in adapter

    for stale in (
        '"non-deterministic"',
        '"slow"',
        '"internal"',
        '"irreversible"',
        'JsonPropertyName("issuer")',
        'JsonPropertyName("ttl_seconds")',
        'JsonPropertyName("one_time")',
    ):
        assert stale not in adapter

    principal_target = adapter.index('"principal-target"')
    principal = adapter.index('\n                "principal",', principal_target)
    target = adapter.index('\n                "target",', principal)
    assert principal_target < principal < target


def test_dotnet_schema_is_embedded_and_rich_manifest_evidence_is_preserved() -> None:
    template_root = ROOT / "skills/mcp-server-architect/tools/dotnet-template"
    project = (template_root / "src/__NAMESPACE__.Mcp.Server/__NAMESPACE__.Mcp.Server.csproj.template").read_text(
        encoding="utf-8"
    )
    rich = (template_root / "src/__NAMESPACE__.Mcp.Server/CapabilityManifest.cs.template").read_text(encoding="utf-8")
    adapter = (template_root / "src/__NAMESPACE__.Mcp.Server/CanonicalCapabilityManifest.cs.template").read_text(
        encoding="utf-8"
    )

    assert "EmbeddedResource" in project
    assert "capability-manifest.schema.json" in project
    assert "CopyToOutputDirectory" not in project
    assert "CapabilityEvidence" in rich
    assert "RequireEvidence" in rich
    assert '["evidence"] = manifest.Evidence' in adapter
    assert '["retry_conditions"] = manifest.RetryConditions' in adapter


def test_dotnet_baseline_does_not_claim_unverified_sdk_candidate() -> None:
    manifest = yaml.safe_load((ROOT / "skills/mcp-server-architect/manifest.yaml").read_text(encoding="utf-8"))
    profile = manifest["protocol"]["sdk_profiles"]["dotnet-official-mcp"]
    packages = (ROOT / "skills/mcp-server-architect/tools/dotnet-template/Directory.Packages.props.template").read_text(
        encoding="utf-8"
    )

    assert profile["verified_baseline_versions"] == ["1.4.1"]
    assert profile["upstream_stable_candidate_versions"] == ["2.1.0"]
    assert 'Version="1.4.1"' in packages
    assert 'Version="2.1.0"' not in packages
