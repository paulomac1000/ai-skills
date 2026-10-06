"""Regressions for generation-bound mutable MCP catalog discovery."""

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
TOOL = ARCHITECT / "tools/discovery_index_lifecycle.py"
STANDARD = ARCHITECT / "STANDARD.md"
SKILL = ARCHITECT / "SKILL.md"
REFERENCE = ARCHITECT / "references/catalog-discovery-lifecycle.md"
MANIFEST = ARCHITECT / "manifest.yaml"
RULES = ROOT / "contracts/rule-catalog.yaml"
RULE_MAP = ROOT / "contracts/standard-rule-map.yaml"
QUALITY_TARGETS = ROOT / "scripts/quality_targets.py"


def _load(name: str, path: Path = TOOL) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _component(
    lifecycle: ModuleType,
    source: str = "source-a",
    manifest: str = "m1",
    active: bool = True,
):
    return lifecycle.CatalogComponent("tool.deploy", source, manifest, active)


def _catalog(
    lifecycle: ModuleType,
    generation: str,
    *,
    source: str = "source-a",
    manifest: str = "m1",
    active: bool = True,
):
    return lifecycle.CatalogSnapshot(
        generation,
        "policy-1",
        (_component(lifecycle, source, manifest, active),),
    )


def _covered(targets: tuple[str, ...], path: str) -> bool:
    return any(
        path == target
        or path.startswith(f"{target.rstrip('/')}/")
        or ("*" in target and fnmatch.fnmatch(path, target))
        for target in targets
    )


def test_semantic_catalog_change_requires_new_generation_and_stale_hit_cannot_retarget() -> None:
    lifecycle = _load("catalog_generation")
    manager = lifecycle.DiscoveryIndexLifecycle(
        _catalog(lifecycle, "g1"),
        search_config_revision="s1",
    )
    owner = manager.request_build(
        requester_id="owner-a",
        attempt_id="attempt-1",
        trigger=lifecycle.BuildTrigger.LAZY_FIRST_USE,
    )
    manager.publish(owner)
    hit = manager.search("deploy")[0]
    assert hit.catalog_generation == "g1"
    assert hit.source_identity == "source-a"
    assert manager.resolve_for_invocation(hit).source_identity == "source-a"

    with pytest.raises(lifecycle.CatalogGenerationError):
        manager.replace_catalog(
            _catalog(lifecycle, "g1", source="source-b", manifest="m2")
        )

    manager.replace_catalog(
        _catalog(lifecycle, "g2", source="source-b", manifest="m2")
    )
    stale = manager.search("deploy", allow_stale=True)[0]
    assert stale.current is False
    with pytest.raises(lifecycle.StaleDiscoveryResultError):
        manager.resolve_for_invocation(stale)


def test_remove_then_add_or_rebind_requires_fresh_discovery() -> None:
    lifecycle = _load("catalog_add_remove_rebind")
    manager = lifecycle.DiscoveryIndexLifecycle(
        _catalog(lifecycle, "g1"),
        search_config_revision="s1",
    )
    owner = manager.request_build(
        requester_id="owner",
        attempt_id="attempt-1",
        trigger=lifecycle.BuildTrigger.LAZY_FIRST_USE,
    )
    manager.publish(owner)
    old_hit = manager.search("deploy")[0]

    manager.replace_catalog(lifecycle.CatalogSnapshot("g2", "policy-1", ()))
    with pytest.raises(lifecycle.StaleDiscoveryResultError):
        manager.resolve_for_invocation(old_hit)

    manager.replace_catalog(
        _catalog(lifecycle, "g3", source="source-b", manifest="m2")
    )
    with pytest.raises(lifecycle.StaleDiscoveryResultError):
        manager.resolve_for_invocation(old_hit)

    rebuilt = manager.request_build(
        requester_id="owner",
        attempt_id="attempt-2",
        trigger=lifecycle.BuildTrigger.LAZY_FIRST_USE,
    )
    manager.publish(rebuilt)
    fresh_hit = manager.search("deploy")[0]
    assert fresh_hit.catalog_generation == "g3"
    assert fresh_hit.source_identity == "source-b"
    assert manager.resolve_for_invocation(fresh_hit).manifest_revision == "m2"


def test_single_flight_join_waiter_cancel_and_owner_cancel_are_separate() -> None:
    lifecycle = _load("catalog_single_flight")
    manager = lifecycle.DiscoveryIndexLifecycle(
        _catalog(lifecycle, "g1"),
        search_config_revision="s1",
    )
    owner = manager.request_build(
        requester_id="owner",
        attempt_id="attempt-1",
        trigger=lifecycle.BuildTrigger.EAGER_WARMUP,
    )
    waiter = manager.request_build(
        requester_id="waiter",
        attempt_id="ignored-attempt",
        trigger=lifecycle.BuildTrigger.LAZY_FIRST_USE,
    )
    assert waiter.joined is True
    assert waiter.attempt_id == owner.attempt_id
    assert manager.cancel_waiter(waiter) is lifecycle.BuildState.BUILDING
    with pytest.raises(lifecycle.BuildOwnershipError):
        manager.publish(waiter)

    manager.cancel_build(owner)
    with pytest.raises(lifecycle.BuildNotActiveError):
        manager.publish(owner)

    retry = manager.request_build(
        requester_id="owner",
        attempt_id="attempt-2",
        trigger=lifecycle.BuildTrigger.LAZY_FIRST_USE,
    )
    assert retry.attempt_id != owner.attempt_id
    assert manager.publish(retry).identity == manager.current_identity


def test_failed_or_superseded_build_cannot_publish_partial_or_overwrite_newer_generation() -> None:
    lifecycle = _load("catalog_publication_fence")
    manager = lifecycle.DiscoveryIndexLifecycle(
        _catalog(lifecycle, "g1"),
        search_config_revision="s1",
    )
    failed = manager.request_build(
        requester_id="owner",
        attempt_id="failed-1",
        trigger=lifecycle.BuildTrigger.LAZY_FIRST_USE,
    )
    manager.fail_build(failed)
    assert manager.index is None
    with pytest.raises(lifecycle.BuildNotActiveError):
        manager.publish(failed)

    old = manager.request_build(
        requester_id="owner-old",
        attempt_id="old-2",
        trigger=lifecycle.BuildTrigger.LAZY_FIRST_USE,
    )
    manager.replace_catalog(
        _catalog(lifecycle, "g2", source="source-b", manifest="m2")
    )
    with pytest.raises(lifecycle.BuildSupersededError):
        manager.publish(old)
    assert manager.index is None

    current = manager.request_build(
        requester_id="owner-new",
        attempt_id="new-1",
        trigger=lifecycle.BuildTrigger.EAGER_WARMUP,
    )
    with pytest.raises(ValueError, match="unknown component"):
        manager.publish(current, ("tool.missing",))
    assert manager.index is None
    assert manager.publish(current).identity.catalog_generation == "g2"


def test_search_config_and_strategy_identity_bound_cache_and_health() -> None:
    lifecycle = _load("catalog_cache_health")
    manager = lifecycle.DiscoveryIndexLifecycle(
        _catalog(lifecycle, "g1"),
        search_config_revision="s1",
    )
    lazy_health = manager.health(require_current_index_for_startup=False)
    strict_health = manager.health(require_current_index_for_startup=True)
    assert lazy_health.invocation_ready is True and lazy_health.current_index_ready is False
    assert lazy_health.startup_ready is True and strict_health.startup_ready is False

    owner = manager.request_build(
        requester_id="warmup",
        attempt_id="attempt-1",
        trigger=lifecycle.BuildTrigger.EAGER_WARMUP,
    )
    manager.publish(owner)
    assert manager.health(require_current_index_for_startup=True).startup_ready is True
    first_key = manager.cache_key("deploy", strategy_revision="rank-v1")

    manager.set_search_config_revision("s2")
    assert manager.health().index_state == "stale"
    second_key = manager.cache_key("deploy", strategy_revision="rank-v1")
    assert first_key != second_key
    with pytest.raises(lifecycle.StaleDiscoveryIndexError):
        manager.search("deploy")

    manager.replace_catalog(_catalog(lifecycle, "g2"))
    third_key = manager.cache_key("deploy", strategy_revision="rank-v1")
    assert second_key != third_key


def test_federated_discovery_requires_explicit_allowlist_and_pre_network_authority() -> None:
    lifecycle = _load("catalog_federation")
    policy = lifecycle.ExternalDiscoveryPolicy(True, ("source-a",))
    assert lifecycle.external_discovery_network_allowed(
        policy,
        source_identity="source-a",
        capability_authorized=True,
    )
    assert not lifecycle.external_discovery_network_allowed(
        policy,
        source_identity="source-a",
        capability_authorized=False,
    )
    assert not lifecycle.external_discovery_network_allowed(
        policy,
        source_identity="source-b",
        capability_authorized=True,
    )


def test_contract_is_routed_mapped_required_and_quality_gated() -> None:
    standard = " ".join(STANDARD.read_text(encoding="utf-8").split()).casefold()
    skill = " ".join(SKILL.read_text(encoding="utf-8").split())
    reference = " ".join(REFERENCE.read_text(encoding="utf-8").split())
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    rules = yaml.safe_load(RULES.read_text(encoding="utf-8"))
    mapping = yaml.safe_load(RULE_MAP.read_text(encoding="utf-8"))

    assert "## Mutable catalog discovery lifecycle" in STANDARD.read_text(encoding="utf-8")
    assert "derived discovery state is a projection" in standard
    assert "re-resolve" in standard and "current catalog" in standard
    assert "references/catalog-discovery-lifecycle.md" in skill
    assert "ranking or confidence is advisory only" in reference.casefold()
    assert "tools/discovery_index_lifecycle.py" in manifest["required"]
    assert "references/catalog-discovery-lifecycle.md" in manifest["required"]

    rule_ids = {
        rule["id"]
        for rule in rules["skills"]["mcp-server-architect"]["rules"]
    }
    assert "mcp.discovery.generation-bound" in rule_ids
    map_entry = mapping["skills"]["mcp-server-architect"]["headings"][
        "mutable-catalog-discovery-lifecycle"
    ]
    assert map_entry == {
        "rule_id": "mcp.discovery.generation-bound",
        "primary": True,
    }

    inventories = _load("catalog_quality_targets", QUALITY_TARGETS)
    path = "skills/mcp-server-architect/tools/discovery_index_lifecycle.py"
    for targets in (
        inventories.QUALITY_PATHS,
        inventories.TYPE_PATHS,
        inventories.BANDIT_PATHS,
    ):
        assert _covered(targets, path)
