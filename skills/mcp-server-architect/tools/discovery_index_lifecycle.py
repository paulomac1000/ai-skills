#!/usr/bin/env python3
"""Reference state model for generation-bound MCP catalog discovery."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class CatalogLifecycleError(RuntimeError):
    """Base error for discovery lifecycle violations."""


class CatalogGenerationError(CatalogLifecycleError):
    """A semantic catalog mutation reused an existing generation."""


class BuildOwnershipError(CatalogLifecycleError):
    """A non-owner attempted to settle a shared build."""


class BuildNotActiveError(CatalogLifecycleError):
    """A terminal or unknown build was used as if it were active."""


class BuildSupersededError(CatalogLifecycleError):
    """A build attempted publication after its identity stopped being current."""


class StaleDiscoveryIndexError(CatalogLifecycleError):
    """A stale derived index was used where current discovery was required."""


class StaleDiscoveryResultError(CatalogLifecycleError):
    """A discovery result no longer binds the current catalog/config identity."""


class ComponentUnavailableError(CatalogLifecycleError):
    """The exact current component exists but is not active."""


@dataclass(frozen=True, slots=True)
class CatalogComponent:
    canonical_id: str
    source_identity: str
    manifest_revision: str
    active: bool = True

    def __post_init__(self) -> None:
        for label, value in (
            ("canonical_id", self.canonical_id),
            ("source_identity", self.source_identity),
            ("manifest_revision", self.manifest_revision),
        ):
            if not value.strip():
                raise ValueError(f"{label} must be non-empty")


@dataclass(frozen=True, slots=True)
class CatalogSnapshot:
    generation: str
    policy_revision: str
    components: tuple[CatalogComponent, ...]

    def __post_init__(self) -> None:
        if not self.generation.strip() or not self.policy_revision.strip():
            raise ValueError("generation and policy_revision must be non-empty")
        ids = [component.canonical_id for component in self.components]
        if len(ids) != len(set(ids)):
            raise ValueError("catalog component identities must be unique")

    @property
    def semantic_digest(self) -> str:
        payload = {
            "policy_revision": self.policy_revision,
            "components": [
                {
                    "canonical_id": component.canonical_id,
                    "source_identity": component.source_identity,
                    "manifest_revision": component.manifest_revision,
                    "active": component.active,
                }
                for component in sorted(self.components, key=lambda item: item.canonical_id)
            ],
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    def component(self, canonical_id: str) -> CatalogComponent | None:
        return next((item for item in self.components if item.canonical_id == canonical_id), None)


@dataclass(frozen=True, slots=True)
class IndexIdentity:
    catalog_generation: str
    search_config_revision: str


class BuildTrigger(StrEnum):
    LAZY_FIRST_USE = "lazy_first_use"
    EAGER_WARMUP = "eager_warmup"


class BuildState(StrEnum):
    BUILDING = "building"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PUBLISHED = "published"


@dataclass(frozen=True, slots=True)
class BuildHandle:
    identity: IndexIdentity
    attempt_id: str
    owner_id: str
    requester_id: str
    joined: bool
    trigger: BuildTrigger


@dataclass(slots=True)
class _BuildAttempt:
    identity: IndexIdentity
    attempt_id: str
    owner_id: str
    state: BuildState = BuildState.BUILDING


@dataclass(frozen=True, slots=True)
class IndexedComponent:
    canonical_id: str
    source_identity: str
    manifest_revision: str


@dataclass(frozen=True, slots=True)
class DerivedDiscoveryIndex:
    identity: IndexIdentity
    attempt_id: str
    entries: tuple[IndexedComponent, ...]


@dataclass(frozen=True, slots=True)
class DiscoveryHit:
    canonical_id: str
    source_identity: str
    manifest_revision: str
    catalog_generation: str
    search_config_revision: str
    score: float | None
    current: bool


@dataclass(frozen=True, slots=True)
class DiscoveryHealth:
    catalog_generation: str
    index_generation: str | None
    index_state: str
    current_index_ready: bool
    invocation_ready: bool
    startup_ready: bool


@dataclass(frozen=True, slots=True)
class ExternalDiscoveryPolicy:
    enabled: bool
    allowlisted_sources: tuple[str, ...]


class DiscoveryIndexLifecycle:
    """Small deterministic model for catalog/index generation and publication rules."""

    def __init__(self, catalog: CatalogSnapshot, *, search_config_revision: str) -> None:
        if not search_config_revision.strip():
            raise ValueError("search_config_revision must be non-empty")
        self._catalog = catalog
        self._search_config_revision = search_config_revision
        self._attempts: dict[str, _BuildAttempt] = {}
        self._active_attempt_by_identity: dict[IndexIdentity, str] = {}
        self._seen_attempt_ids: set[str] = set()
        self._index: DerivedDiscoveryIndex | None = None

    @property
    def catalog(self) -> CatalogSnapshot:
        return self._catalog

    @property
    def current_identity(self) -> IndexIdentity:
        return IndexIdentity(self._catalog.generation, self._search_config_revision)

    @property
    def index(self) -> DerivedDiscoveryIndex | None:
        return self._index

    def replace_catalog(self, catalog: CatalogSnapshot) -> None:
        semantic_change = catalog.semantic_digest != self._catalog.semantic_digest
        if semantic_change and catalog.generation == self._catalog.generation:
            raise CatalogGenerationError("semantic catalog mutation requires a distinct generation")
        self._catalog = catalog

    def set_search_config_revision(self, revision: str) -> None:
        if not revision.strip():
            raise ValueError("search config revision must be non-empty")
        self._search_config_revision = revision

    def request_build(
        self,
        *,
        requester_id: str,
        attempt_id: str,
        trigger: BuildTrigger,
    ) -> BuildHandle:
        """Start or join the one logical build for the current index identity."""

        if not requester_id.strip() or not attempt_id.strip():
            raise ValueError("requester_id and attempt_id must be non-empty")
        identity = self.current_identity
        active_id = self._active_attempt_by_identity.get(identity)
        if active_id is not None:
            active = self._attempts[active_id]
            if active.state is BuildState.BUILDING:
                return BuildHandle(
                    identity,
                    active.attempt_id,
                    active.owner_id,
                    requester_id,
                    True,
                    trigger,
                )
        if attempt_id in self._seen_attempt_ids:
            raise ValueError("retry requires a new attempt_id")
        attempt = _BuildAttempt(identity, attempt_id, requester_id)
        self._attempts[attempt_id] = attempt
        self._active_attempt_by_identity[identity] = attempt_id
        self._seen_attempt_ids.add(attempt_id)
        return BuildHandle(identity, attempt_id, requester_id, requester_id, False, trigger)

    def cancel_waiter(self, handle: BuildHandle) -> BuildState:
        """A cancelled waiter never cancels a build owned by another request scope."""

        return self._attempt(handle).state

    def cancel_build(self, handle: BuildHandle) -> None:
        attempt = self._owned_active_attempt(handle)
        attempt.state = BuildState.CANCELLED
        self._clear_active(attempt)

    def fail_build(self, handle: BuildHandle) -> None:
        attempt = self._owned_active_attempt(handle)
        attempt.state = BuildState.FAILED
        self._clear_active(attempt)

    def publish(self, handle: BuildHandle, component_ids: Iterable[str] | None = None) -> DerivedDiscoveryIndex:
        attempt = self._owned_active_attempt(handle)
        if attempt.identity != self.current_identity:
            raise BuildSupersededError("older build cannot publish for a superseded catalog/config generation")

        requested = (
            tuple(component_ids)
            if component_ids is not None
            else tuple(component.canonical_id for component in self._catalog.components if component.active)
        )
        if len(requested) != len(set(requested)):
            raise ValueError("published component identities must be unique")

        entries: list[IndexedComponent] = []
        for canonical_id in requested:
            component = self._catalog.component(canonical_id)
            if component is None:
                raise ValueError(f"unknown component cannot be published: {canonical_id}")
            if not component.active:
                raise ValueError(f"inactive component cannot be published: {canonical_id}")
            entries.append(
                IndexedComponent(
                    component.canonical_id,
                    component.source_identity,
                    component.manifest_revision,
                )
            )

        published = DerivedDiscoveryIndex(attempt.identity, attempt.attempt_id, tuple(entries))
        self._index = published
        attempt.state = BuildState.PUBLISHED
        self._clear_active(attempt)
        return published

    def search(self, query: str, *, allow_stale: bool = False) -> tuple[DiscoveryHit, ...]:
        index = self._index
        if index is None:
            return ()
        current = index.identity == self.current_identity
        if not current and not allow_stale:
            raise StaleDiscoveryIndexError("discovery index is not current")

        needle = query.casefold().strip()
        hits: list[DiscoveryHit] = []
        for entry in index.entries:
            haystack = f"{entry.canonical_id} {entry.source_identity}".casefold()
            if needle and needle not in haystack:
                continue
            hits.append(
                DiscoveryHit(
                    canonical_id=entry.canonical_id,
                    source_identity=entry.source_identity,
                    manifest_revision=entry.manifest_revision,
                    catalog_generation=index.identity.catalog_generation,
                    search_config_revision=index.identity.search_config_revision,
                    score=1.0,
                    current=current,
                )
            )
        return tuple(hits)

    def resolve_for_invocation(self, hit: DiscoveryHit) -> CatalogComponent:
        """Re-resolve a discovery result against exact current catalog authority."""

        if (
            hit.catalog_generation != self._catalog.generation
            or hit.search_config_revision != self._search_config_revision
        ):
            raise StaleDiscoveryResultError("discovery result identity is stale; re-discovery is required")
        component = self._catalog.component(hit.canonical_id)
        if component is None:
            raise StaleDiscoveryResultError("discovered component no longer exists")
        if component.source_identity != hit.source_identity or component.manifest_revision != hit.manifest_revision:
            raise StaleDiscoveryResultError("discovered component provenance changed")
        if not component.active:
            raise ComponentUnavailableError("current component is inactive")
        return component

    def cache_key(self, query: str, *, strategy_revision: str) -> str:
        if not strategy_revision.strip():
            raise ValueError("strategy_revision must be non-empty")
        payload = {
            "catalog_generation": self._catalog.generation,
            "search_config_revision": self._search_config_revision,
            "strategy_revision": strategy_revision,
            "query": query,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    def health(self, *, require_current_index_for_startup: bool = False) -> DiscoveryHealth:
        identity = self.current_identity
        current_index = self._index is not None and self._index.identity == identity
        invocation_ready = any(component.active for component in self._catalog.components)
        index_state = self._index_state(identity)
        startup_ready = invocation_ready and (current_index or not require_current_index_for_startup)
        return DiscoveryHealth(
            catalog_generation=self._catalog.generation,
            index_generation=self._index.identity.catalog_generation if self._index else None,
            index_state=index_state,
            current_index_ready=current_index,
            invocation_ready=invocation_ready,
            startup_ready=startup_ready,
        )

    def _index_state(self, identity: IndexIdentity) -> str:
        if self._index is not None:
            return "current" if self._index.identity == identity else "stale"
        active_id = self._active_attempt_by_identity.get(identity)
        if active_id is not None:
            return self._attempts[active_id].state.value
        terminal = [attempt for attempt in self._attempts.values() if attempt.identity == identity]
        if terminal:
            return terminal[-1].state.value
        return "missing"

    def _attempt(self, handle: BuildHandle) -> _BuildAttempt:
        attempt = self._attempts.get(handle.attempt_id)
        if attempt is None or attempt.identity != handle.identity:
            raise BuildNotActiveError("unknown build attempt")
        return attempt

    def _owned_active_attempt(self, handle: BuildHandle) -> _BuildAttempt:
        attempt = self._attempt(handle)
        if handle.requester_id != attempt.owner_id or handle.joined:
            raise BuildOwnershipError("only the build owner may settle the shared build")
        if attempt.state is not BuildState.BUILDING:
            raise BuildNotActiveError(f"build is already terminal: {attempt.state.value}")
        return attempt

    def _clear_active(self, attempt: _BuildAttempt) -> None:
        if self._active_attempt_by_identity.get(attempt.identity) == attempt.attempt_id:
            del self._active_attempt_by_identity[attempt.identity]


def external_discovery_network_allowed(
    policy: ExternalDiscoveryPolicy,
    *,
    source_identity: str,
    capability_authorized: bool,
) -> bool:
    """Return whether network-backed federated discovery may begin."""

    if not capability_authorized or not policy.enabled:
        return False
    return source_identity in policy.allowlisted_sources
