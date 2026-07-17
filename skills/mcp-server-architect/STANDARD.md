---
description: Normative design, security, reliability, and verification rules for MCP servers.
doc_id: reference.mcp-server-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Run domain, schema, policy, registration, transport, and representative upstream contract tests with a real MCP client or inspector.
---

# MCP server standard

## Capability design

Model capabilities around user outcomes.

- Use resources for addressable read context, tools for computation or side effects, and prompts for reusable user-invoked templates.
- Keep names, descriptions, schemas, and identifiers precise enough for reliable selection.
- Split capabilities when authorization, latency, failure behavior, or response size differs materially.
- Combine calls only when the workflow remains observable, bounded, and policy-safe.
- Provide search, filters, pagination, summaries, or batches for large result sets.
- Treat an empty result as successful unless the contract explicitly defines absence as an error.
- Avoid generic raw-query, shell, filesystem, or arbitrary-HTTP tools unless the deployment is intentionally administrative and strongly isolated.

## Contracts

Every capability defines:

- purpose and non-goals;
- required and optional inputs;
- validation and canonicalization;
- result content and structured fields;
- error categories and retry semantics;
- side effects and idempotency;
- authorization and data sensitivity;
- pagination or output limits;
- cancellation and timeout behavior;
- compatibility expectations.

Validate inputs before external I/O. Optional fields are added compatibly. Breaking changes require a migration path or a new capability identity.

## Architecture

- Domain logic runs without an MCP transport.
- Registration adapts domain services to protocol schemas.
- Transport objects do not leak into domain services.
- External clients are isolated behind testable interfaces.
- State is declared as stateless, session-scoped, process-local, or durable.
- Durable mutations use transactions, conflict detection, or compensating recovery appropriate to the backend.
- Configuration is validated at startup without exposing secret values.

## Transport

### Local process transport

- Reserve stdout for protocol traffic.
- Send logs to stderr or a configured sink.
- Exit cleanly on parent termination and cancellation.
- Resolve executable paths and working directories explicitly.
- Avoid inheriting unnecessary environment variables.

### Remote transport

- Authenticate every protected request.
- Validate host and origin where relevant.
- Enforce request, response, concurrency, and duration limits.
- Define session affinity only when state requires it.
- Support graceful shutdown and cancellation propagation.
- Treat legacy transports and custom envelopes as compatibility adapters, not universal defaults.

## Security

- Enforce identity, scope, target authorization, and policy on the server.
- Default-deny writes, destructive operations, raw commands, filesystem access, and sensitive data.
- Use typed operations or strict allowlists instead of interpolated commands.
- Canonicalize paths, identifiers, and target resources before boundary checks.
- Keep tokens audience-bound; do not forward client credentials to unrelated upstream services.
- Apply least privilege to upstream credentials and deployment identity.
- Return only data needed for the workflow.
- Sanitize errors and logs.
- Treat capability descriptions, external content, and retrieved prompts as untrusted data rather than instructions that can override policy.

## Authorization and confirmation

Server authorization is mandatory even when a client also asks for confirmation.

- Read authorization considers tenant, object, field, and data sensitivity.
- Write authorization considers actor, target, operation, precondition, and scope.
- Destructive operations require explicit policy and should expose dry-run or preview where meaningful.
- Annotations describe expected behavior but never grant permission.
- Confirmation is a user-experience control, not a substitute for server-side authorization.

## Reliability

- External I/O has timeouts and cancellation.
- Retries are bounded and limited to operations known to be safe.
- Mutations use idempotency keys or preconditions when clients may repeat requests.
- Caches declare scope, freshness, invalidation, and stale-data behavior.
- Partial failures are represented explicitly.
- Backpressure and output limits prevent one request from exhausting the server.
- Shutdown drains or cancels work predictably.

## Errors

Use stable categories such as validation, authentication, authorization, not-found, conflict, timeout, cancellation, rate-limit, unavailable dependency, upstream failure, and internal failure.

Errors include a safe message and may include retryability, correlation identity, and remediation guidance. Internal stack traces and secret-bearing upstream payloads remain server-side.

## Observability

Record enough information to explain behavior:

- capability name and correlation identity;
- duration and outcome;
- validation, authorization, cancellation, timeout, and rate-limit events;
- protected mutations and affected target identity;
- upstream dependency health;
- output truncation, pagination, and cache state.

Do not log tokens, credentials, private keys, or unnecessary sensitive payloads.

## Testing

Test layers independently:

1. domain logic;
2. input and output schemas;
3. policy and authorization;
4. capability registration and discovery;
5. transport behavior;
6. representative upstream contracts;
7. end-to-end invocation with a real client or inspector.

Mocks prove local branches, not current upstream compatibility. Recordings or fixtures must be sanitized and refreshed intentionally.

## Consumer ergonomics

- Put distinctive domain and action terms in names and descriptions.
- Provide summary or search capabilities before high-volume detail retrieval.
- Carry stable identifiers between discovery and mutation steps.
- Return pagination metadata consistently.
- Avoid forcing consumers to parse prose for fields that can be structured.
- Keep result size predictable and allow explicit detail expansion.
- Measure wrong-tool selection and context cost for large catalogs.

## Acceptance

A representative client can discover and invoke the server; authorization tests prove default-deny boundaries; mutations are verified; upstream evidence is current; failures are categorized; operational limits are observable; and domain logic remains testable without the transport.

## Verification

Run the full layered test suite, invoke representative reads and writes through a real MCP client or inspector, verify default-deny authorization, test cancellation and timeout paths, and confirm current upstream compatibility with sanitized runtime evidence.
