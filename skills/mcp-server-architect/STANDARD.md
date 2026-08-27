---
description: Normative language-neutral architecture and production rules for MCP servers.
doc_id: reference.mcp-server-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Generate fresh Python and .NET servers, execute each official-client suite, then run layered domain, manifest, policy, registration, lifecycle, race, transport-conformance, upstream-contract, and deployment-artifact tests for every advertised transport.
---

# MCP server standard

## Purpose

Define language-neutral invariants for servers consumed by agents. SDK profiles explain how to realize them without turning framework internals into architecture. The standard is hardened by migration simulations across read-only aggregators, device controllers, network appliances, multi-backend administrators, financial adapters, and browser-automation servers.

## Maturity levels

| Level | Use case | Required evidence |
| --- | --- | --- |
| L1 personal | local or experimental server | domain unit tests, schema validation, controlled errors |
| L2 team | shared internal server | L1 plus complete manifests, registration, integration, auth boundary, CI, health |
| L3 production | always-on critical service | L2 plus real-client smoke, lifecycle and race tests, observability, SLOs, cancellation, artifact tests |
| L4 hardened | public, multi-tenant, sensitive, or dangerous capabilities | L3 plus per-resource authorization, isolation, abuse controls, security tests, audit and recovery drills |

## Skill contract and precedence

At L2 and above, pin both the immutable repository revision and the skill version from `manifest.yaml`. A release-candidate skill is eligible for controlled pilots and independent review; a stable claim requires completed compatibility evidence and a migration path for every breaking change.

When resources disagree, apply this order:

1. this `STANDARD.md` and active normative decisions;
2. the applicable implementation profile;
3. `SKILL.md` workflow instructions;
4. generators and templates;
5. examples;
6. migration simulations.

A lower-ranked resource cannot weaken a higher-ranked requirement. A generator is a verified baseline, not a policy exception, and an example cannot create a new invariant. Stop the migration and request a standard decision when a conflict remains unresolved.

## Core architecture

- Domain operations do not depend on MCP transport or SDK types.
- Registration adapts typed operations to public tools, resources, prompts, schemas, and response contracts.
- One composition root owns validated configuration, dependencies, lifecycle, registration, middleware, and transport.
- One invocation kernel resolves the manifest, performs local validation, authenticates the principal, authorizes the capability and declared target namespace, resolves and authorizes the stable target, checks operator policy, revalidates target identity, applies deadlines and concurrency controls, executes, maps errors, sanitizes output, and emits telemetry.
- Every MCP transport and convenience adapter delegates to that kernel; no adapter calls a raw tool function or private wrapper directly.
- Process, tenant, target, session, request, dependency-client, cache, lock, executor, artifact, and background-task ownership are explicit.
- Optional integrations fail independently; mandatory dependency failure prevents readiness.
- SDK compatibility logic is isolated behind one adapter and never spread through domain code.

## Configuration and identity

Load and validate configuration before modules create clients or capture environment values. Freeze one typed settings snapshot for the process. Runtime mutation requires an explicit reload transaction and revalidation.

Secrets come from an intentional source and never from command-line arguments, example JSON, logs, capability discovery, or model-visible errors. A public-bind acknowledgement is not authentication, authorization, TLS, or network isolation.

Before authentication, code may only parse and normalize a locally declared target selector with no network I/O or protected-data access. Authenticate the principal and authorize the capability plus selector namespace before DNS, discovery, SSH, cloud API, device scan, account lookup, or other network-backed target resolution. Resolve the stable target only within that authorized namespace, then authorize the resolved target and resource. Bind every mutation to stable identity such as account ID, device identity, host fingerprint, tenant, or resource version. Never silently replace an unavailable requested or default target with another target. Revalidate mutable address-to-identity mappings immediately before side effects.

## Public component contracts

Every public component has a stable name, bounded input, structured output, documented empty-success behavior, version policy, and machine-readable failure shape. For state-changing operations, completion, returned identity, and returned representation are separate dimensions: confirmed success without an identity or representation is not an ambiguous completion, while an unknown completion requires reconciliation before retry. Tool descriptions and annotations improve discovery but are not authorization.

At L2 and above, every public tool has a complete governed manifest. Missing or malformed metadata fails registration or CI; it never defaults to `READ`. The manifest, schema, description, runtime policy, active profile, SDK annotations, and tested behavior describe the same operation.

Distinguish the supported catalog from the active catalog. Profiles, unavailable dependencies, operator policy, caller scopes, and deployment topology may reduce the active set, but discovery explains why a supported capability is inactive. Large catalogs provide bounded categories, search, minimal listings, or on-demand schemas.

List and search tools return identifiers accepted by detail or mutation tools. Large results support bounded summaries, fields, pagination, or progressive discovery. Pagination defines stable ordering, continuation semantics, and a terminating condition; a non-empty page alone never proves another page exists.

Use server-level instructions for cross-tool ordering, stable ID flow, async polling, profile limitations, and reconciliation. Instructions improve agent behavior but never replace runtime validation or authorization.

## Multi-axis safety classification

A single risk label is insufficient. Every capability independently declares:

- side effects: none, read, write, or destructive;
- confidentiality: public, internal, personal, sensitive, credential, financial, or a stricter domain class;
- operational impact: none, transient, persistent, outage, safety-critical, or financial;
- cost and abuse potential;
- reversibility and compensation;
- idempotency mechanism and retry conditions;
- target-binding and concurrency scope;
- artifact, task, browser-profile, or privileged-adapter ownership when applicable.

`READ`, `WRITE`, `DESTRUCTIVE`, `DANGEROUS`, and `SENSITIVE` may remain compatibility or UI projections, but policy evaluates every axis. Read-only financial data, logs, configuration, snapshots, browser profiles, and credentials remain confidential.

## Side effects, retries, and workflows

Write operations define idempotency, reversibility, concurrency preconditions, and conflict tokens. Never infer that every write is idempotent, retryable, reversible, or concurrent-safe from a factory name or SDK annotation. Each positive claim has operation-specific evidence.

Automatic retry requires all of the following: an eligible error category, an unexpired deadline, a proven idempotency mechanism from trusted local policy, no explicit veto, preserved target identity, and any required refreshed precondition. Create, publish, copy, payment-state, command, browser-action, OTA, restart, and update operations default to no automatic retry.

Multi-step changes use plan, execute, verify, and compensate phases. Per-step results preserve partial success. Operations that intentionally disconnect a target or continue after the request return an accepted or in-progress state, a verification window, and a follow-up method instead of disguising expected disconnect as generic timeout.

Destructive and dangerous operations require narrow allowlists and explicit server-side authorization. Filesystem paths, commands, URLs, service names, network targets, content sizes, and resolved addresses are validated before I/O. Arbitrary command execution uses fixed executables, argument arrays, isolation, output limits, deadlines, and audit events. A read execution path cannot reach write commands.

## Transport and lifecycle

The only standard transports for new servers are stdio and Streamable HTTP. The deprecated two-endpoint HTTP+SSE transport from protocol revision 2024-11-05 is forbidden for every new server at L1-L4. It must not appear in generated projects, examples, or default configuration.

Existing L2+ servers using legacy HTTP+SSE must migrate to Streamable HTTP. A temporary compatibility adapter is allowed only as a documented exception when a named legacy client cannot migrate yet. The adapter is disabled by default, isolated from the primary host, restricted to an explicit client or network allowlist, covered by dedicated conformance and policy-parity tests, assigned an owner and removal deadline, and receives no new feature development. This exception does not make legacy HTTP+SSE a supported transport.

Do not confuse legacy HTTP+SSE with optional `text/event-stream` responses or GET streams inside modern Streamable HTTP. The latter remain part of the current protocol. Avoid invented removal dates; follow the normative MCP deprecation lifecycle and reviewed SDK release notes.

Stdio reserves stdout for protocol messages and sends diagnostics to stderr. Remote HTTP validates canonicalized Origin values, binds intentionally, authenticates before capability execution, and applies restrictive host and CORS policy. Stateless HTTP is preferred when server-to-client or cross-request state is unnecessary, and the choice is explicit rather than inherited from an SDK default.

Startup, readiness, liveness, capability health, task health, and shutdown have separate meanings. Tool count or successful transport binding alone never means ready. Resources initialize once at their declared owner scope and close once on every owner-scope exit path. Partial startup reports unavailable capabilities and targets; it does not silently mark the workload healthy or redirect operations.

## Deadlines, cancellation, retries, and concurrency

- Propagate request deadlines and cancellation to every cancellable I/O operation.
- Never use unbounded external calls, request bodies, headers, executor queues, subprocess output, sessions, caches, scans, task registries, or generated exports.
- Cleanup after cancellation is bounded and does not mask cancellation.
- Rate limiters are concurrency-safe and scoped to the actual upstream quota key such as credential, tenant, target, or endpoint.
- Honor upstream retry hints within the remaining deadline and apply jittered bounded backoff.
- Conflict retry requires a refreshed precondition or re-read.
- `concurrent_safe` is an enforced runtime property, not documentation.
- Shared mutable clients use immutable per-call options, a pool, a keyed lock, or a narrow semaphore.
- Blocking work is offloaded to a bounded executor from asynchronous hosts.
- Request-scoped identifiers and principals use request context, not process-global or thread-local mutable state in asynchronous code.
- Session, approval, artifact, and task identifiers use a cryptographically secure generator with at least 128 bits of entropy and remain bound to the authenticated principal.

## Data, errors, and responses

Errors distinguish validation, authentication, authorization, not found, conflict, rate limit, timeout, cancellation, unavailable dependency, upstream failure, UI drift, ambiguous outcome, and internal failure. `ambiguous outcome` means the operation's effect is not established; it MUST NOT be used merely because a confirmed success omitted a resource identity or response representation. Preserve upstream status and retry guidance without leaking secrets or raw protected bodies.

Responses preserve protocol-native content, structured content, correlation identifiers, target identity, data provenance, freshness, and partial-result state. A custom DTO containing `success: false` does not automatically become a protocol-native tool error; tests assert `isError` or the SDK equivalent. Schema and data annotations improve discovery but do not enforce runtime validation.

Domain values use unambiguous contracts. Money uses decimal or minor units plus currency and rounding policy. Dates use ISO 8601 with timezone or explicit date-only semantics. Localized upstream formats are converted only inside the upstream adapter.

Content returned by a webpage or another AI system is marked with provenance and treated as untrusted input. Citations, hidden text, page instructions, and generated answers cannot grant tool authority or reduce risk.

## Authentication and authorization

Authenticate the calling principal and intended audience before any network-backed target resolution. Authorize the capability and locally declared selector namespace before discovery; after resolution, authorize the exact stable target, resource, operation, data classification, artifact, task, and browser account. Bind downstream credentials and target selection to approved caller context to prevent confused-deputy behavior. Revalidate stable identity immediately before I/O without changing the authorized target.

Operator write gates, user confirmation hints, per-principal authorization, target allowlists, and execution isolation are independent controls. A model-supplied boolean is not approval. Approval records are opaque, bounded, expiring, and bound to principal, capability, target, and resource.

## Runtime boundaries, artifacts, and browser automation

Filesystem containment uses resolved component-aware paths, not string prefixes. Writes define symlink and time-of-check/time-of-use policy. Archives, uploads, and generated files enforce byte, type, destination, and extraction limits.

Screenshots, reports, audio, backups, firmware, and exports are governed artifacts with owner, operation ID, MIME type, size, checksum when useful, retention, and deletion behavior. A host path is not a public artifact identity.

Background work is tracked by a bounded task registry or durable store. Daemon threads, untracked tasks, and fire-and-forget `Task.Run` are not operation records. Protocol task metadata does not replace a supervised executor or durable queue. Session disconnect releases session-owned handles but does not erase durable task records before terminal state or retention expiry.

Persistent browser profiles are credential stores. Account isolation, directory permissions, process locking, interactive-auth state, shared-context serialization, selector-drift diagnostics, sanitized screenshots, and explicit cleanup are part of the security contract.

## Multi-backend and embedded hosting

Multi-backend servers preserve configured target identity and namespace. A failed default does not become the first healthy backend. Gateways preserve source-server and manifest provenance so equal tool names cannot collide or transfer authority.

An embedded MCP server does not own the host process, global event loop, global logging, dependency container, or unrelated listeners. It receives host services explicitly, participates in host lifecycle, avoids route and port collisions, closes only owned resources, and never exits the process from a request path.

## Observability and operations

Emit structured logs, traces, duration, result category, resolved target, dependency state, policy decision, cancellation, saturation, retry, artifact and task state, and partial success. Correlate transport and domain operations with one request identifier.

Health reports mandatory and optional dependencies separately. Circuit breakers and graceful degradation prevent cascading failure. Audit failures are observable but follow an explicit fail-open or fail-closed policy. Full repository suites are CI or deployment gates, not unbounded production startup checks.

## Generated project acceptance

The bundled Python and .NET generators are part of the standard, not illustrative snippets. A clean invocation creates a deterministic, installable or restore-ready project containing typed immutable settings, application-owned manifests, a transport-independent domain service, one invocation kernel, official SDK registration, stdio and loopback Streamable HTTP, structured output, protocol-native errors, conservative write controls, CI, packaging, security guidance, and tests.

Each generated project must compile and pass its own tests through an official MCP client using the stable production SDK lane. Tests prove public tool listing with real schemas, representative invocation, complete manifest coverage, fail-closed writes, principal-bound approval, optimistic conflict handling, bounded HTTP input, action pinning, deterministic generation, and smoke of the exact published artifact.

The Python baseline carries complete runtime and development lock graphs with artifact hashes for every declared operating-system, architecture, and Python-version tuple. Acceptance installs the selected lock with `--require-hashes`, runs `pip check`, builds a wheel, installs that exact wheel into an isolated environment without dependency resolution, proves imports resolve from the installed artifact rather than `PYTHONPATH` or an editable tree, and executes the official-client suite. The container installs the committed Linux runtime lock, copies the same prebuilt wheel that passed the official-client suite, verifies its SHA-256 before installation, and smokes the resulting non-root image; the image must never rebuild the package from source. Candidate dependency upgrades are separate, non-authoritative evidence until locks and compatibility tests are reviewed together.

Generation uses exclusive no-replace publication and refuses an existing file, directory, or symlink target even under concurrent creation. The operating-system-specific publication primitive is tested on every declared supported platform. Production adoption still requires replacing sample domain code, reviewing every manifest, adding real authentication and resource authorization, upstream contract tests, deployment-artifact smoke tests, and all applicable runtime-boundary scenarios.

## Migration acceptance

Existing projects begin with bounded read-only discovery rather than a handwritten final assessment. Discovery records observed package identity, transports, packaging, external boundaries, live-test prerequisites, and unresolved facts. An external, legacy, poorly documented, or contradicted backend requires an observed `upstream-contract.yaml` before its adapter contract is redesigned. Inferred upstream behavior is a discovery state, not acceptance evidence.

Implementation state and formal assurance state are independent. A useful implementation lifecycle is `planned -> implemented -> merged -> released`; assurance progresses separately through `discovered -> locally-verified -> provider-verified -> independent-review-pending -> adopted`. Repository policy MAY permit merge or release before formal adoption, but that implementation state MUST NOT be represented as `adopted`. Pending provider or review state likewise MUST NOT become a durable requirement that a particular PR remain draft. Normal unfinished work does not require a waiver. A waiver represents an intentional final deviation from an applicable rule, not the fact that implementation has not reached adoption yet.

Every L2+ migration eventually produces `migration-assessment.yaml` from `templates/migration-assessment.yaml.template`, covers every `mcp-server-architect` rule in `contracts/rule-catalog.yaml`, preserves the complete normative-heading mapping in `contracts/standard-rule-map.yaml`, and follows `references/migration-assessment.md`. The final assessment pins the immutable source revision, skill version, maturity target, profiles, scope, applicability matrix, implementation evidence, verification commands, preserved and intentionally changed behavior, removed legacy behavior, waivers, exact artifact identity, rollback, residual risks, and independent decision.

`not-applicable` requires an architectural rationale. `deferred` requires an owned, expiring waiver and compensating controls. No waiver may permit model-controlled authorization, fail-open risk, target substitution, unbounded privileged execution, or a new legacy HTTP+SSE implementation. A green aggregate check without rule-to-code-to-test evidence is insufficient.

A canonical independent reviewer may approve only through provider-backed evidence whose review state and commit ID match the immutable assessed revision, after every advertised transport passes official-client smoke against the exact deployment artifact and all applicable rules have executable evidence. Review evidence from an earlier head is stale after implementation changes even when all earlier bot threads are resolved. Runtime risk and publication exposure are separate axes: destructive local-single-user capabilities still require strong runtime authorization, but independent protected-release authority is driven by maturity and actual distribution/exposure rather than the mere presence of a delete operation. An undocumented behavioral difference or unresolved normative conflict is a migration defect.

## Verification layers

1. domain unit tests;
2. schema, serialization, domain-value, and manifest-consistency tests;
3. policy, authorization, target-binding, filesystem, artifact, and sanitization tests;
4. public registration, active-profile, resources, prompts, instructions, and discovery tests;
5. lifecycle, configuration-order, task, browser-profile, cancellation, executor, and concurrency tests;
6. transport conformance and invocation-kernel parity tests;
7. representative official-client workflows;
8. deployment-artifact smoke tests;
9. upstream contract tests with controlled fakes, recordings, canaries, or test containers; for unknown or legacy upstreams this layer moves before adapter refactoring;
10. live-backend mutation evidence, when applicable, only after independent operator opt-in and independent proof that the resolved target is an exclusive disposable environment; pre-clean is forbidden before that proof and cleanup uses captured identities, a unique namespace, or verified baseline difference according to resource semantics;
11. the implementation-language migration simulation for consumer work, while ai-skills self-validation runs both Python and .NET simulations;
12. fresh-project generation followed by installation or restore, compilation, and its own real-client suite;
13. completed migration assessment with independent decision for every L2+ adoption or migration.

No layer substitutes for another.

## Implementation profiles

- [Migration assessment](references/migration-assessment.md)
- [Capability manifests and versioning](references/capability-manifests-and-versioning.md)
- [Transport, lifecycle, and conformance](references/transport-lifecycle-and-conformance.md)
- [Runtime boundaries and artifacts](references/runtime-boundaries-and-artifacts.md)
- [Container artifact source provenance](references/container-provenance-dataflow.md)
- [Python and FastMCP](references/python-fastmcp.md)
- [Python migration simulation](references/python-migration-simulation.md)
- [.NET MCP](references/dotnet-mcp.md)
- [.NET migration simulation](references/dotnet-migration-simulation.md)
- [Cross-language invariant map](references/cross-language-invariant-map.md)
- [Security and operations](references/security-and-operations.md)
- [Problem-solution matrix](references/problem-solution-matrix.md)

## Verification

Generate fresh Python and .NET projects and execute their complete official-client suites first. Then run all applicable layers once at their proper abstraction level; repeat transport conformance, invocation-kernel policy parity, representative client workflows, and artifact smoke tests for every advertised transport. Review public contracts, target identity, lifecycle ownership, trust boundaries, data classification, runtime enforcement, artifacts, tasks, profile isolation, and embedded-host ownership independently from framework-specific code. For every L2+ migration, validate the completed provider-backed assessment with `python contracts/validate_adoption.py migration-assessment.yaml --require-approval` against the immutable reviewed revision before approval.
