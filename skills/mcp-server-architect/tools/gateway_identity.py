from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

_CANONICAL_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_RESOURCE_KINDS = {"resource", "resource-template", "extension-reference"}


class GatewayIdentityError(ValueError):
    """Base error for invalid or stale gateway identity state."""


class GatewayCollisionError(GatewayIdentityError):
    """Two distinct upstream components produced one canonical gateway identity."""


class StaleGatewayMappingError(GatewayIdentityError):
    """A gateway mapping no longer matches the current source registration."""


class GatewaySourceUnavailableError(GatewayIdentityError):
    """The exact mapped source is currently unavailable; no fallback is allowed."""


class GatewayComponentKind(StrEnum):
    TOOL = "tool"
    PROMPT = "prompt"
    RESOURCE = "resource"
    RESOURCE_TEMPLATE = "resource-template"
    EXTENSION_REFERENCE = "extension-reference"
    COMPOSITE_PROMPT = "composite-prompt"


@dataclass(frozen=True)
class UpstreamSourceIdentity:
    """Stable configured source namespace, independent of health or registration order."""

    namespace: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.namespace or any(not part.strip() for part in self.namespace):
            raise ValueError("source namespace must contain non-empty components")

    @property
    def key(self) -> tuple[str, ...]:
        return self.namespace


@dataclass(frozen=True)
class SourceRegistration:
    """Current source registration and manifest generation used to fence stale mappings."""

    source: UpstreamSourceIdentity
    generation: str
    manifest_revision: str
    healthy: bool = True

    def __post_init__(self) -> None:
        if not self.generation.strip() or not self.manifest_revision.strip():
            raise ValueError("source generation and manifest revision must be non-empty")


@dataclass(frozen=True)
class UpstreamComponent:
    """One upstream public component before gateway projection."""

    source: UpstreamSourceIdentity
    kind: GatewayComponentKind
    original_identity: str

    def __post_init__(self) -> None:
        if not self.original_identity.strip():
            raise ValueError("upstream component identity must be non-empty")


@dataclass(frozen=True)
class GatewayMapping:
    """Deterministic gateway projection plus exact upstream provenance."""

    canonical_id: str
    source: UpstreamSourceIdentity
    source_generation: str
    manifest_revision: str
    kind: GatewayComponentKind
    original_identity: str
    normalized_label: str

    def __post_init__(self) -> None:
        if not _CANONICAL_ID.fullmatch(self.canonical_id):
            raise ValueError("canonical gateway identity must be lowercase kebab-safe")
        if not self.original_identity.strip() or not self.normalized_label.strip():
            raise ValueError("gateway mapping identity fields must be non-empty")


@dataclass(frozen=True)
class GatewayRoute:
    """Exact current route after stale/source-health fencing."""

    canonical_id: str
    source: UpstreamSourceIdentity
    source_generation: str
    manifest_revision: str
    kind: GatewayComponentKind
    upstream_identity: str


@dataclass(frozen=True)
class GatewayCompositePrompt:
    """Explicit gateway-owned prompt composition; upstream prompts are never implicitly merged."""

    canonical_id: str
    upstream_prompt_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _CANONICAL_ID.fullmatch(self.canonical_id):
            raise ValueError("composite prompt identity must be canonical")
        if len(self.upstream_prompt_ids) < 2 or len(set(self.upstream_prompt_ids)) != len(self.upstream_prompt_ids):
            raise ValueError("composite prompt needs at least two distinct upstream prompt identities")


def _normalized_label(value: str) -> str:
    """Produce a bounded display slug without using it as authority."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    return slug or "component"


def canonical_gateway_id(
    source: UpstreamSourceIdentity,
    kind: GatewayComponentKind,
    upstream_identity: str,
    *,
    max_length: int = 96,
) -> str:
    """Derive a deterministic bounded identity from exact source, kind, and upstream identity."""
    if not upstream_identity.strip():
        raise ValueError("upstream identity must be non-empty")
    material = json.dumps(
        [list(source.namespace), kind.value, upstream_identity],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(material).hexdigest()[:20]
    prefix = f"gw-{kind.value}-"
    minimum_length = len(prefix) + len(digest) + 2
    if max_length < minimum_length:
        raise ValueError(f"max_length must be >= {minimum_length} for component kind {kind.value}")
    available = max_length - len(prefix) - len(digest) - 1
    slug = _normalized_label(upstream_identity)[:available].strip("-") or "component"
    return f"{prefix}{slug}-{digest}"


def map_component(
    registration: SourceRegistration,
    component: UpstreamComponent,
    *,
    max_id_length: int = 96,
) -> GatewayMapping:
    """Project one component while preserving current source/manifest provenance."""
    if registration.source != component.source:
        raise GatewayIdentityError("component source must match the selected registration")
    return GatewayMapping(
        canonical_id=canonical_gateway_id(
            component.source,
            component.kind,
            component.original_identity,
            max_length=max_id_length,
        ),
        source=component.source,
        source_generation=registration.generation,
        manifest_revision=registration.manifest_revision,
        kind=component.kind,
        original_identity=component.original_identity,
        normalized_label=_normalized_label(component.original_identity),
    )


@dataclass(frozen=True)
class GatewayCatalog:
    """Configured source registrations plus collision-safe public mappings."""

    registrations: tuple[SourceRegistration, ...]
    mappings: tuple[GatewayMapping, ...]

    def __post_init__(self) -> None:
        source_keys = [registration.source.key for registration in self.registrations]
        if len(set(source_keys)) != len(source_keys):
            raise GatewayIdentityError("source registrations must have unique stable identities")

        mapping_ids: dict[str, GatewayMapping] = {}
        for mapping in self.mappings:
            previous = mapping_ids.get(mapping.canonical_id)
            if previous is not None:
                if previous != mapping:
                    raise GatewayCollisionError(f"canonical gateway identity collision: {mapping.canonical_id}")
                raise GatewayCollisionError(f"duplicate upstream component registration: {mapping.canonical_id}")
            mapping_ids[mapping.canonical_id] = mapping

    def _source_index(self) -> dict[tuple[str, ...], SourceRegistration]:
        return {registration.source.key: registration for registration in self.registrations}

    def _mapping_index(self) -> dict[str, GatewayMapping]:
        return {mapping.canonical_id: mapping for mapping in self.mappings}

    def resolve(
        self,
        canonical_id: str,
        *,
        expected_kind: GatewayComponentKind | None = None,
        require_healthy: bool = True,
    ) -> GatewayMapping:
        """Resolve exactly one current mapping; stale/unhealthy sources never fall back by name."""
        mapping = self._mapping_index().get(canonical_id)
        if mapping is None:
            raise GatewayIdentityError(f"unknown gateway component identity: {canonical_id}")
        registration = self._source_index().get(mapping.source.key)
        if registration is None:
            raise StaleGatewayMappingError("mapped source is no longer registered")
        if (
            registration.generation != mapping.source_generation
            or registration.manifest_revision != mapping.manifest_revision
        ):
            raise StaleGatewayMappingError("gateway mapping does not match current source generation")
        if expected_kind is not None and mapping.kind is not expected_kind:
            raise GatewayIdentityError("gateway component kind does not match the requested operation")
        if require_healthy and not registration.healthy:
            raise GatewaySourceUnavailableError("exact mapped source is unavailable")
        return mapping

    def list_components(self, kind: GatewayComponentKind | None = None) -> tuple[GatewayMapping, ...]:
        """List current configured mappings in deterministic canonical order."""
        current = []
        for mapping in self.mappings:
            self.resolve(mapping.canonical_id, expected_kind=mapping.kind, require_healthy=False)
            if kind is None or mapping.kind is kind:
                current.append(mapping)
        return tuple(sorted(current, key=lambda item: item.canonical_id))

    def search(self, query: str, kind: GatewayComponentKind | None = None) -> tuple[GatewayMapping, ...]:
        """Search current mappings while returning the same canonical identities used elsewhere."""
        needle = query.casefold()
        matches = []
        for mapping in self.list_components(kind):
            haystack = " ".join((mapping.canonical_id, mapping.original_identity, *mapping.source.namespace)).casefold()
            if needle in haystack:
                matches.append(mapping)
        return tuple(matches)

    def detail(self, canonical_id: str) -> GatewayMapping:
        """Return current detail using the canonical identity directly."""
        return self.resolve(canonical_id, require_healthy=False)

    def invocation_route(self, canonical_id: str) -> GatewayRoute:
        """Resolve invocation to the exact current source/component without alias fallback."""
        mapping = self.resolve(canonical_id)
        return GatewayRoute(
            canonical_id=mapping.canonical_id,
            source=mapping.source,
            source_generation=mapping.source_generation,
            manifest_revision=mapping.manifest_revision,
            kind=mapping.kind,
            upstream_identity=mapping.original_identity,
        )

    def task_subject(self, canonical_id: str) -> str:
        """Keep durable task identity stable even while the exact upstream is degraded."""
        return self.resolve(canonical_id, require_healthy=False).canonical_id

    def with_registrations(self, registrations: Iterable[SourceRegistration]) -> GatewayCatalog:
        """Replace current sources without silently rebinding existing mappings."""
        return GatewayCatalog(tuple(registrations), self.mappings)


def build_gateway_catalog(
    registrations: Iterable[SourceRegistration],
    components: Iterable[UpstreamComponent],
    *,
    max_id_length: int = 96,
) -> GatewayCatalog:
    """Build a deterministic catalog whose identity is independent of source order and health."""
    registrations_tuple = tuple(registrations)
    source_index = {registration.source.key: registration for registration in registrations_tuple}
    if len(source_index) != len(registrations_tuple):
        raise GatewayIdentityError("source registrations must have unique stable identities")
    mappings = []
    for component in components:
        registration = source_index.get(component.source.key)
        if registration is None:
            raise GatewayIdentityError("component references an unregistered source")
        mappings.append(map_component(registration, component, max_id_length=max_id_length))
    return GatewayCatalog(registrations_tuple, tuple(mappings))


def refresh_mapping(mapping: GatewayMapping, registration: SourceRegistration) -> GatewayMapping:
    """Refresh source generation/provenance while preserving the stable canonical component identity."""
    if registration.source != mapping.source:
        raise GatewayIdentityError("mapping can only refresh from the same stable source identity")
    return replace(
        mapping,
        source_generation=registration.generation,
        manifest_revision=registration.manifest_revision,
    )


def export_resource_reference(mapping: GatewayMapping) -> str:
    """Create an opaque gateway-owned resource reference that excludes the raw upstream URI."""
    if mapping.kind.value not in _RESOURCE_KINDS:
        raise GatewayIdentityError("only resource-like components can be exported as gateway references")
    return f"mcp-gateway://{mapping.kind.value}/{mapping.canonical_id}"


def resolve_resource_reference(catalog: GatewayCatalog, reference: str) -> GatewayRoute:
    """Resolve a strict gateway resource reference back to the exact source and original URI/template."""
    parsed = urlsplit(reference)
    if (
        parsed.scheme != "mcp-gateway"
        or parsed.query
        or parsed.fragment
        or not parsed.netloc
        or not parsed.path.startswith("/")
        or parsed.path.count("/") != 1
    ):
        raise GatewayIdentityError("invalid gateway resource reference")
    try:
        kind = GatewayComponentKind(parsed.netloc)
    except ValueError as exc:
        raise GatewayIdentityError("unknown gateway resource kind") from exc
    if kind.value not in _RESOURCE_KINDS:
        raise GatewayIdentityError("gateway reference kind is not resource-like")
    canonical_id = parsed.path[1:]
    if not _CANONICAL_ID.fullmatch(canonical_id):
        raise GatewayIdentityError("gateway resource reference contains an invalid canonical identity")
    mapping = catalog.resolve(canonical_id, expected_kind=kind)
    return GatewayRoute(
        canonical_id=mapping.canonical_id,
        source=mapping.source,
        source_generation=mapping.source_generation,
        manifest_revision=mapping.manifest_revision,
        kind=mapping.kind,
        upstream_identity=mapping.original_identity,
    )


def create_composite_prompt(
    gateway_namespace: str,
    name: str,
    upstream_prompts: Iterable[GatewayMapping],
    *,
    max_id_length: int = 96,
) -> GatewayCompositePrompt:
    """Create an explicit gateway-owned composite from already source-qualified prompt mappings."""
    if not gateway_namespace.strip() or not name.strip():
        raise ValueError("gateway namespace and composite prompt name must be non-empty")
    prompts = tuple(upstream_prompts)
    prompt_ids = tuple(mapping.canonical_id for mapping in prompts)
    if any(mapping.kind is not GatewayComponentKind.PROMPT for mapping in prompts):
        raise GatewayIdentityError("composite prompts may reference only prompt mappings")
    source = UpstreamSourceIdentity(("gateway", gateway_namespace))
    canonical_id = canonical_gateway_id(
        source,
        GatewayComponentKind.COMPOSITE_PROMPT,
        name,
        max_length=max_id_length,
    )
    return GatewayCompositePrompt(canonical_id, prompt_ids)


def preserve_output_schema(schema: Any) -> Any:
    """Round-trip JSON-compatible schema data without object-only coercion."""
    try:
        encoded = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise GatewayIdentityError("public schema must be JSON-compatible") from exc
    return json.loads(encoded)


def build_stdio_child_environment(
    host_environment: Mapping[str, str],
    *,
    allowed_host_variables: Iterable[str] = (),
    source_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build a minimized child environment; ambient host secrets are absent unless explicitly allowed."""
    result: dict[str, str] = {}
    seen: set[str] = set()
    for name in allowed_host_variables:
        if not name or name in seen:
            raise ValueError("allowed host environment names must be unique and non-empty")
        seen.add(name)
        if name in host_environment:
            result[name] = host_environment[name]
    for name, value in (source_environment or {}).items():
        if not name or not isinstance(value, str):
            raise ValueError("source environment entries must use non-empty names and string values")
        result[name] = value
    return result
