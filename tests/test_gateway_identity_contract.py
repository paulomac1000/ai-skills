"""Regressions for source-qualified gateway identity and MCP re-export."""

from __future__ import annotations

import fnmatch
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
ARCHITECT = ROOT / "skills/mcp-server-architect"
TOOL = ARCHITECT / "tools/gateway_identity.py"
STANDARD = ARCHITECT / "STANDARD.md"
REFERENCE = ARCHITECT / "references/gateway-aggregation.md"
MANIFEST = ARCHITECT / "manifest.yaml"
QUALITY_TARGETS = ROOT / "scripts/quality_targets.py"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _source(module: ModuleType, *parts: str):
    return module.UpstreamSourceIdentity(parts)


def _covered(targets: tuple[str, ...], path: str) -> bool:
    return any(
        path == target
        or path.startswith(f"{target.rstrip('/')}/")
        or ("*" in target and fnmatch.fnmatch(path, target))
        for target in targets
    )


def test_same_normalized_tool_name_is_source_qualified_across_surfaces() -> None:
    gateway = _load("gateway_identity_surfaces", TOOL)
    source_a = _source(gateway, "tenant", "alpha")
    source_b = _source(gateway, "tenant", "beta")
    registration_a = gateway.SourceRegistration(source_a, "gen-1", "manifest-a", healthy=True)
    registration_b = gateway.SourceRegistration(source_b, "gen-9", "manifest-b", healthy=False)
    component_a = gateway.UpstreamComponent(source_a, gateway.GatewayComponentKind.TOOL, "Deploy Service")
    component_b = gateway.UpstreamComponent(source_b, gateway.GatewayComponentKind.TOOL, "deploy-service")

    catalog = gateway.build_gateway_catalog(
        (registration_b, registration_a),
        (component_b, component_a),
        max_id_length=64,
    )
    tools = catalog.list_components(gateway.GatewayComponentKind.TOOL)
    assert len(tools) == 2
    assert len({mapping.canonical_id for mapping in tools}) == 2

    mapping_a = next(mapping for mapping in tools if mapping.source == source_a)
    mapping_b = next(mapping for mapping in tools if mapping.source == source_b)
    assert catalog.detail(mapping_a.canonical_id) == mapping_a
    assert mapping_a in catalog.search("alpha", gateway.GatewayComponentKind.TOOL)
    route = catalog.invocation_route(mapping_a.canonical_id)
    assert route.canonical_id == catalog.task_subject(mapping_a.canonical_id)
    assert route.source == source_a
    assert route.upstream_identity == "Deploy Service"
    assert route.manifest_revision == "manifest-a"

    assert catalog.task_subject(mapping_b.canonical_id) == mapping_b.canonical_id
    with pytest.raises(gateway.GatewaySourceUnavailableError):
        catalog.invocation_route(mapping_b.canonical_id)


def test_collision_handling_is_order_health_case_and_truncation_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _load("gateway_identity_collisions", TOOL)
    source_a = _source(gateway, "a")
    source_b = _source(gateway, "b")
    registrations = (
        gateway.SourceRegistration(source_a, "1", "m1", healthy=True),
        gateway.SourceRegistration(source_b, "1", "m2", healthy=False),
    )
    components = (
        gateway.UpstreamComponent(source_a, gateway.GatewayComponentKind.TOOL, "A" * 300),
        gateway.UpstreamComponent(source_b, gateway.GatewayComponentKind.TOOL, "a" * 300),
    )

    first = gateway.build_gateway_catalog(registrations, components, max_id_length=48)
    second = gateway.build_gateway_catalog(
        tuple(reversed(registrations)),
        tuple(reversed(components)),
        max_id_length=48,
    )
    assert {mapping.canonical_id for mapping in first.mappings} == {
        mapping.canonical_id for mapping in second.mappings
    }
    assert len({mapping.canonical_id for mapping in first.mappings}) == 2
    assert all(len(mapping.canonical_id) <= 48 for mapping in first.mappings)

    upper_source = _source(gateway, "SOURCE")
    lower_source = _source(gateway, "source")
    upper = gateway.canonical_gateway_id(
        upper_source, gateway.GatewayComponentKind.TOOL, "same", max_length=48
    )
    lower = gateway.canonical_gateway_id(
        lower_source, gateway.GatewayComponentKind.TOOL, "same", max_length=48
    )
    assert upper != lower

    monkeypatch.setattr(
        gateway,
        "canonical_gateway_id",
        lambda *args, **kwargs: "gw-tool-forced-collision",
    )
    with pytest.raises(gateway.GatewayCollisionError, match="collision"):
        gateway.build_gateway_catalog(registrations, components)


def test_canonical_id_length_bound_is_component_kind_aware() -> None:
    gateway = _load("gateway_identity_length_bound", TOOL)
    source = _source(gateway, "source")

    for kind in gateway.GatewayComponentKind:
        canonical_id = gateway.canonical_gateway_id(
            source,
            kind,
            "x" * 300,
            max_length=64,
        )
        assert len(canonical_id) <= 64

    with pytest.raises(ValueError, match="resource-template"):
        gateway.canonical_gateway_id(
            source,
            gateway.GatewayComponentKind.RESOURCE_TEMPLATE,
            "template",
            max_length=40,
        )


def test_resource_uri_overlap_stale_readd_and_namespace_escape_fail_closed() -> None:
    gateway = _load("gateway_identity_resources", TOOL)
    source_a = _source(gateway, "a")
    source_b = _source(gateway, "b")
    registration_a = gateway.SourceRegistration(source_a, "g1", "m1")
    registration_b = gateway.SourceRegistration(source_b, "g1", "m2")
    uri = "file:///shared/config.json"
    catalog = gateway.build_gateway_catalog(
        (registration_a, registration_b),
        (
            gateway.UpstreamComponent(source_a, gateway.GatewayComponentKind.RESOURCE, uri),
            gateway.UpstreamComponent(source_b, gateway.GatewayComponentKind.RESOURCE, uri),
        ),
    )

    references = [gateway.export_resource_reference(mapping) for mapping in catalog.mappings]
    assert len(set(references)) == 2
    routes = [gateway.resolve_resource_reference(catalog, reference) for reference in references]
    assert {route.source for route in routes} == {source_a, source_b}
    assert {route.upstream_identity for route in routes} == {uri}

    with pytest.raises(gateway.GatewayIdentityError):
        gateway.resolve_resource_reference(catalog, "mcp-gateway://resource/../escape")

    mapping_a = next(mapping for mapping in catalog.mappings if mapping.source == source_a)
    with pytest.raises(gateway.StaleGatewayMappingError):
        catalog.with_registrations((registration_b,)).resolve(mapping_a.canonical_id)

    registration_a_v2 = gateway.SourceRegistration(source_a, "g2", "m3")
    with pytest.raises(gateway.StaleGatewayMappingError):
        catalog.with_registrations((registration_a_v2, registration_b)).resolve(mapping_a.canonical_id)

    refreshed = gateway.refresh_mapping(mapping_a, registration_a_v2)
    rebuilt = gateway.GatewayCatalog(
        (registration_a_v2, registration_b),
        tuple(refreshed if mapping == mapping_a else mapping for mapping in catalog.mappings),
    )
    assert refreshed.canonical_id == mapping_a.canonical_id
    assert rebuilt.resolve(refreshed.canonical_id).source == source_a


def test_same_named_prompts_require_explicit_composite_and_preserve_schema_shapes() -> None:
    gateway = _load("gateway_identity_prompts", TOOL)
    source_a = _source(gateway, "a")
    source_b = _source(gateway, "b")
    catalog = gateway.build_gateway_catalog(
        (
            gateway.SourceRegistration(source_a, "1", "ma"),
            gateway.SourceRegistration(source_b, "1", "mb"),
        ),
        (
            gateway.UpstreamComponent(source_a, gateway.GatewayComponentKind.PROMPT, "triage"),
            gateway.UpstreamComponent(source_b, gateway.GatewayComponentKind.PROMPT, "triage"),
        ),
    )
    prompts = catalog.list_components(gateway.GatewayComponentKind.PROMPT)
    assert len({prompt.canonical_id for prompt in prompts}) == 2

    composite = gateway.create_composite_prompt("prod", "triage-both", iter(prompts))
    assert set(composite.upstream_prompt_ids) == {prompt.canonical_id for prompt in prompts}

    schemas = (
        {"type": "array", "items": {"type": "string"}},
        {"oneOf": [{"type": "string"}, {"type": "integer"}]},
        True,
    )
    for schema in schemas:
        assert gateway.preserve_output_schema(schema) == schema


def test_stdio_child_environment_is_minimized_and_source_credentials_do_not_leak() -> None:
    gateway = _load("gateway_identity_stdio", TOOL)
    host = {
        "PATH": "/usr/bin",
        "LANG": "C.UTF-8",
        "GH_TOKEN": "ambient-secret",
        "AWS_SECRET_ACCESS_KEY": "ambient-aws",
    }
    child_a = gateway.build_stdio_child_environment(
        host,
        allowed_host_variables=("PATH", "LANG"),
        source_environment={"GITHUB_TOKEN": "source-a-token"},
    )
    child_b = gateway.build_stdio_child_environment(
        host,
        allowed_host_variables=("PATH", "LANG"),
    )

    assert child_a == {
        "PATH": "/usr/bin",
        "LANG": "C.UTF-8",
        "GITHUB_TOKEN": "source-a-token",
    }
    assert child_b == {"PATH": "/usr/bin", "LANG": "C.UTF-8"}
    assert "GH_TOKEN" not in child_a
    assert "AWS_SECRET_ACCESS_KEY" not in child_a
    assert "GITHUB_TOKEN" not in child_b


def test_gateway_contract_is_routed_required_and_quality_gated() -> None:
    standard = STANDARD.read_text(encoding="utf-8")
    reference = REFERENCE.read_text(encoding="utf-8")
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))

    normalized_standard = " ".join(standard.split())
    normalized_reference = " ".join(reference.split())
    assert "references/gateway-aggregation.md" in standard
    assert "one bounded deterministic source-qualified identity" in normalized_standard
    assert "stale mapping" in normalized_standard and "fail closed" in normalized_standard
    assert "tools/gateway_identity.py" in manifest["required"]
    assert "references/gateway-aggregation.md" in manifest["required"]
    assert "implicit prompt merging is forbidden" in normalized_reference
    assert "Ambient host tokens" in normalized_reference

    inventories = _load("gateway_identity_quality_targets", QUALITY_TARGETS)
    path = "skills/mcp-server-architect/tools/gateway_identity.py"
    for targets in (
        inventories.QUALITY_PATHS,
        inventories.TYPE_PATHS,
        inventories.BANDIT_PATHS,
        inventories.POLICY_COVERAGE_PATHS,
    ):
        assert _covered(targets, path)