---
description: Generation-bound lifecycle for mutable MCP catalogs, derived discovery state, single-flight rebuilds, caches, and invocation re-resolution.
doc_id: reference.mcp-catalog-discovery-lifecycle
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Exercise generation changes, stale search results, single-flight rebuild, cancellation/failure, cache invalidation, warmup/lazy parity, health separation, and current invocation re-resolution.
---

# Mutable catalog and discovery-index lifecycle

Use this profile when an MCP gateway can change its supported/active catalog at runtime and keeps derived search, graph, vector, embedding, category, normalized-descriptor, or query-cache state. The canonical catalog remains the authority; discovery state is a bounded projection of one exact catalog generation and search-configuration revision.

## Generation and projection identity

Create a distinct catalog generation for every semantic mutation: source add/remove/reconfiguration, public component contract change, active-profile or routing-policy change, contract-changing capability refresh, or operator catalog replacement. Transient health may remain a separate live dimension when it does not change the supported contract.

Every derived index and result carries the catalog generation plus every search/configuration revision that can change its meaning. Query, result, embedding, normalization, and ranking caches include those identities in their key or are invalidated atomically when one changes. A derived index never becomes a second registry or a source of invocation authority.

## Build publication and single-flight

One logical build owns one catalog-generation/search-config identity. Concurrent callers join that build instead of duplicating upstream reads or index construction. Cancelling a waiter does not cancel a build owned by another scope. Cancelling the owner propagates to cancellable source/index work, and failed/cancelled work never publishes a partial index as current.

Publication is atomic and fenced by build-attempt plus generation identity. A build started for G1 cannot publish after G2 becomes current, and a retry after failure uses a new attempt identity. Every wait/build path has a bounded deadline/cancellation/resource policy; there is no unbounded lock or polling loop.

Lazy first-use and eager warmup call the same canonical builder. Production may require current-index warmup as a fail-fast startup condition, while another profile may start with catalog invocation readiness and expose discovery as not-yet-ready. Eager warmup is therefore policy, not a second implementation.

## Search is advisory; invocation re-resolves

Search output includes stable canonical component identity, source/manifest provenance, catalog generation, search-config revision, and freshness/currentness needed to detect staleness. Ranking or confidence is advisory only.

Before invocation, resolve the selected canonical component again against the current catalog, manifest/source binding, active policy/profile, target binding, and authorization. A stale result from G1 after G2 removed or rebound the identifier returns stale/conflict/re-discovery; it never silently retargets to the current same-named component.

## Strategies, federation, and health

Graph, vector, lexical, keyword, category-first, hybrid, translation, and normalization strategies are optional. Strategy fallback records bounded provenance when it affects interpretation; normalization cannot rewrite target/security identity.

Federated or external discovery is explicit and allowlisted. Authentication/capability authorization happens before any network-backed source resolution, and the normal target/network-I/O trust boundary still applies. External discovery is not a reason to scan or call unapproved sources.

Health separates at least:

- canonical catalog currentness;
- current index readiness versus stale/degraded/missing index state;
- source health when relevant;
- invocation readiness for the exact current component/policy.

Index ready never implies every component is executable, and an invocation-ready catalog does not imply a lazy discovery index has already been built.

## Verification matrix

Exercise semantic add/remove/rebind with generation advancement; stale-result invocation; same-generation semantic mutation rejection; concurrent single-flight joins; waiter cancellation; owner cancellation; failed build and explicit retry; old-build publication after a newer generation; search-config/cache-key invalidation; lazy/eager builder parity; fail-fast versus lazy startup health; external discovery allowlisting/authorization; and high-ranking stale results that still fail current invocation re-resolution.
