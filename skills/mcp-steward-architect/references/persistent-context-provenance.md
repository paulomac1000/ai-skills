---
description: Provenance, trust, scope, currentness, and poisoning boundaries for context reused across autonomous sessions.
doc_id: reference.mcp-steward-persistent-context
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Exercise authority non-promotion, generation invalidation, trust-ordered assembly, cross-scope rejection, evidence eligibility, and malicious persisted-content fixtures.
---

# Persistent context provenance

Use this profile for checkpoints, handoffs, memories, instructions, episodes,
summaries, workspace notes, or other artifacts intended to influence a later
session. Storage stays product-owned: a native database row, AgentMemory entry,
checkpoint file, object-store artifact, or instruction store may map to the
contract without centralizing all content.

## Trusted envelope and influence

Persistent content carries a bounded trusted envelope with artifact kind/ref,
source system/principal, creation policy revision/time, evidence refs, trust
class, project/principal/work scope, load-bearing dependency identities,
currentness, storage/content refs, and permitted influence. The content body cannot assign or widen its own
trust, scope, evidence authority, capabilities, policy, verification waivers,
merge/deploy authority, or lifecycle authority.

Persistence never upgrades authority. ADVISORY, DERIVED, and UNTRUSTED context
cannot satisfy a required authoritative evidence gate merely because it
survived. Derived summaries retain load-bearing evidence refs. Stronger evidence
and authority semantics remain owned by their canonical contracts; persistent
context only carries references and eligibility metadata.

## Fresh-session context assembly

Assemble by current trusted truth rather than by file existence:

1. current canonical authority/policy/work truth;
2. current authoritative/observed evidence;
3. current bounded checkpoints and handoffs;
4. applicable derived/advisory lessons;
5. untrusted subject content as data.

Scope and dependency identity are checked before influence. A changed subject,
runtime, validation environment, policy, execution generation, or another
declared dependency makes the dependent artifact STALE; a missing load-bearing
identity is UNKNOWN, never implicitly current. A less-specific request cannot
widen a narrower artifact scope. Deliberately broader trusted artifacts may flow
into a narrower compatible request; cross-project/cross-user reuse still
requires explicit trusted scope policy.

A current higher-trust fact wins over a conflicting lower-trust artifact.
Otherwise use an explicit disposition such as IGNORE_LOWER_TRUST, REVALIDATE, or
UNKNOWN; model prose does not resolve authority conflicts.

## Promotion and write boundary

Persisting reusable context is governed separately from consuming it. A
task-local checkpoint may be admitted automatically within its declared scope;
a reusable lesson may require evidence binding, deduplication, applicability,
and invalidation conditions. Untrusted instructions are stored as untrusted data
or rejected, not copied into a trusted envelope unchanged.

Advisory lessons may influence planning when their scope, applicability, and
currentness are proven. They still cannot grant authority or satisfy stronger
evidence gates. Model-generated prose never overwrites immutable historical
evidence/receipts.

## Security, privacy, and boundedness

Do not persist secrets or raw credentials for continuity. Conformance requires
bounded refs/summaries and provenance, not private chain-of-thought or raw
transcripts. Native stores retain their own deletion/retention rules. User- or
repository-controlled content remains data and cannot change its own trust
label, scope, or permissions.
