---
description: Core standard for AI agents consuming MCP tools — capability reasoning, decision policies, error recovery, workflow orchestration, and contract obedience
doc_id: ref.mcp-consumer-standards
type: ref
status: active
ttl_days: 180
rigor_tier: L2
stability: stable
ai_scope: editable
domain: mcp
tags: ["mcp", "consumer", "standards", "core", "agent", "decision-policy"]
owners: ["backend-team"]
upstream:
  - ref.documentation-standard
  - ref.mcp-server-standards
source_of_truth: true
last_verified: 2026-06-01
standard_version: "2.1.0"
---

# MCP Consumer Core Standard

> **Document family:** This is the CORE standard for consuming MCP servers — universal, framework-agnostic rules for AI agents that discover, invoke, and interpret MCP tools.
> The server-side standard (`ref.mcp-server-standards`) defines the contract this document consumes.

## PURPOSE

Define universal, framework-agnostic patterns and rules for AI agents that consume MCP (Model Context Protocol) tools. Covers tool discovery through manifest interpretation, capability-based decision making, response contract handling, error recovery strategies, workflow orchestration with safety gates, observability diagnostics, and version compatibility. Every AI agent consuming MCP servers SHOULD follow these patterns.

This document is the CONSUMER counterpart to `ref.mcp-server-standards` (the server builder's standard). Where the server standard defines HOW to build tools, this standard defines HOW to reason about them.

## SCOPE

- INCLUDED: tool discovery and selection, token-aware invocation (batch/composite preference, minimal detail first, progressive disclosure, pagination awareness, negative capability, parameter carry-forward, cross-server workflows), manifest field interpretation and decision rules, response parsing and error branching, error strategy matrix (all 13 error codes from the server standard), retry policy with backoff, confirmation gates for write/destructive tools, multi-tool workflow orchestration with checkpoints, observability pattern (request_id correlation, diagnostics), version compatibility and schema negotiation, decision policy as testable tables
- EXCLUDED: MCP protocol specification, tool implementation, server deployment, network-level security, application-level authorization

## DEFINITIONS

- `MCP consumer`: An AI agent that discovers, selects, invokes, and interprets responses from MCP tools. [L1+]
- `capability reasoning`: The process of evaluating a tool's manifest fields (risk, side_effects, determinism, retryable, concurrent_safe, latency, cost, requires_confirmation, impact, privacy, reversible) to determine invocation safety. [L1+]
- `decision policy`: A deterministic, testable table mapping (manifest fields + situation context) → (agent action). The policy is normative — a correct decision is defined by the table, not by model preference. [L1+]
- `error strategy matrix`: A complete mapping from every error code defined in `ref.mcp-server-standards` to the consumer's recovery action (retry / abort / escalate / ask_user). [L1+]
- `retry policy`: Rules governing whether, when, and how to retry a failed tool call, including backoff strategy and max retry count. [L2+]
- `confirmation gate`: A decision point where the agent MUST pause and request explicit user approval before proceeding. Triggered by `risk` class and `requires_confirmation` field. [L1+]
- `checkpoint`: A saved state enabling rollback of a multi-step workflow when a downstream step fails. [L2+]
- `rollback`: Reversing the effects of prior steps in a workflow after a later step fails. [L2+]
- `escalation`: Informing the user of a non-recoverable error with diagnostic context. [L1+]
- `contract obedience`: The agent's adherence to the tool's declared manifest — never calling a DESTRUCTIVE tool without confirmation, never retrying a non-retryable error, never parallelizing a non-concurrent-safe tool. [L1+]
- `manifest`: A machine-readable JSON object describing a tool's capability profile, version, and constraints. Defined in `ref.mcp-server-standards` (Tool Manifest Schema, 15 fields). [L2+]
- `response contract`: The structured JSON format every MCP tool MUST return — `{"success": bool, ...}`. Defined in `ref.mcp-server-standards` (Response Contract). [L1+]
- `extensible envelope`: Optional `_meta` fields (`request_id`, `duration_ms`, `tool_version`, `cached`, `retry_safe`) in tool responses. [SHOULD]
- `workflow`: A sequence of tool invocations where outputs of earlier tools feed into later tools. [L2+]
- `error code`: A machine-readable UPPER_SNAKE_CASE identifier in `error.code` that agents branch on. [L1+]
- `version negotiation`: The process by which an agent inspects a tool's version and adapts its invocation accordingly. [SHOULD]
- `capability introspection tool`: A zero-I/O, `[READ]`, `instant`-latency MCP tool named `describe_<domain>_capabilities` that returns the full tool catalog with manifests. Required at L3+ server-side. [L2+]

## RULES

### Design Philosophy

Every rule in this standard flows from five principles:

#### 1. The Manifest Is the Primary Source of Truth When Available

Capability decisions come from the manifest when one exists. When no manifest exists, use the risk prefix annotation in the docstring as the capability profile. If both are absent, apply the documented safe fallback. Never override an existing manifest with docstring inference.

#### 2. Decide Before Invoking

The consumer evaluates risk, retry safety, and confirmation requirements BEFORE issuing a tool call. A decision made after the response arrives is too late — the operation already executed.

#### 3. Fail Safely, Never Silently

When a tool fails, the consumer produces a diagnostic explanation the user can act on. Error codes are not swallowed. Retries are bounded. Every non-recoverable failure escalates.

#### 4. Defense in Depth

The consumer enforces confirmation gates even when the server does not. Two independent layers: the server's `ENABLE_WRITE_OPERATIONS` flag (server authorization) and the consumer's confirmation gate (user consent). The consumer assumes neither is sufficient alone.

#### 5. Deterministic Over Heuristic

Every decision the consumer makes SHOULD be reducible to a logic table that a human can audit and a test can verify. "The model chose X" is not a design. "The policy table says X given these inputs" is a design.

### Maturity Levels

This standard defines three compliance levels for consumers. Each rule, pattern, and section is annotated with the minimum level at which it becomes required.

| Level | Name       | Target Consumer                   | Key Additions                                            |
|-------|------------|-----------------------------------|----------------------------------------------------------|
| L1    | Basic      | Single-tool invocation, simple agents | Response parsing, error branching, confirmation gates |
| L2    | Orchestrated | Multi-tool workflows, team agents | Retry policy, checkpoint/rollback, error strategy matrix |
| L3    | Hardened   | Critical operations, multi-agent   | Full capability reasoning, version negotiation, audit trails |

This document's own `rigor_tier` is `L2` — reflecting the authoring rigor (frontmatter compliance, test coverage, review requirements). The `[L3+]` annotations within describe rules that apply when consuming at L3, which this document commits to maintaining for reference.

**Annotation convention:**

- `[L1+]` — Required at all levels (core invariant)
- `[L2+]` — Required at L2 and above
- `[L3+]` — Required at L3 and above
- `[SHOULD]` — Strongly recommended at all levels but may be overridden with documented rationale

Rules without an explicit annotation default to `[L2+]`.

### 1. Tool Discovery

1. [L1+] The consumer MUST discover available tools through `tools/list` or the capability introspection tool (`describe_<domain>_capabilities`) when available. The consumer MUST NOT invoke a tool by name without first confirming it exists in the tool list.
2. [L1+] The consumer MUST prefer the manifest over the docstring for capability decisions when a manifest exists. When no manifest exists, fall back to the risk prefix annotation in the docstring as the capability profile. If both are absent, apply the documented safe default (treat as `READ`). Never override an existing manifest with docstring inference.
3. [L2+] The consumer SHOULD call the capability introspection tool before any other tool. This provides the full catalog with manifests in a single zero-I/O call.
4. [L1+] When a required tool is not found in the catalog, the consumer MUST NOT invoke it. Report the missing tool to the user with the available tool list.
5. [L2+] The consumer SHOULD select tools by matching manifest fields (or risk prefix fallback) to task requirements: READ tools for diagnostics, WRITE tools for configuration changes, DESTRUCTIVE tools only with explicit user intent.

### 2. Token-Aware Invocation

[L1+] AI consumers operate under token budgets. The consumer MUST prefer efficient invocation patterns that minimize round-trips and payload size.

#### Batch and Composite Preference

1. [L1+] When a task would require repeated identical or similar READ calls, the consumer SHOULD scan the tool catalog for batch, bulk, composite, diagnostic, or summary variants before issuing individual calls. Tool name hints such as `*_batch`, `bulk_*`, `diagnose_*`, `investigate_*`, `composite_*`, `overview_*`, and `summary_*` are efficiency signals — not safety authorities. Risk and confirmation decisions still flow from the manifest or risk prefix.
2. [L2+] When no batch or composite alternative exists but repeated calls are unavoidable, the consumer MAY proceed with sequential individual calls and optionally note the tooling gap.

#### Minimal Detail First

3. [L1+] For initial discovery, the consumer SHOULD use `detail_level="minimal"`, `compact=true`, `summary=true`, appropriate `limit` values, or equivalent narrowing parameters when the tool supports them. Request full detail (`detail_level="full"`, `include_code=true`) only for selected candidates after narrowing scope.
4. [L2+] The consumer SHOULD NOT fetch full detail for all items in a large result set before filtering. List or search first, filter by criteria, then drill into detail.

#### Progressive Disclosure

5. [L2+] The consumer SHOULD apply progressive disclosure: list, search, or diagnose first with minimal detail; filter candidates using returned identifiers and metadata; fetch full detail only for selected items. Never fetch full detail for all items before narrowing scope unless the user explicitly requested a full export.

#### Pagination Awareness

6. [L1+] If a response contains pagination markers — `has_more`, `next_offset`, `next_cursor`, `offset`, `limit`, `total`, `page`, or `cursor` — at the top level, inside `_meta`, or inside an object-shaped `data` envelope, the consumer MUST treat the result as partial until pagination is exhausted or the task scope is satisfied. The consumer MUST NOT conclude that an item does not exist from a partial page alone.

#### Negative Capability

7. [L1+] When `success` is `true` and `data` is an empty list, empty dict, `null`, `0`, or an object with `count: 0`, the consumer SHOULD treat this as a meaningful result: the query completed and found no matching items or problems. This is not an error.

#### Parameter Carry-Forward

8. [L2+] The consumer SHOULD maintain a session-local context map of identifiers discovered during workflow execution: entity IDs, automation IDs, device IDs, area IDs, tool names, manifests, request IDs, and versions. Carry resolved identifiers forward across workflow steps to avoid redundant lookups. This map is session-local only — it MUST NOT persist across sessions. SENSITIVE data MUST NOT be stored in the context map.

#### Cross-Server Workflows

9. [L2+] When operating across multiple MCP servers, the consumer MUST maintain separate tool catalogs, capability profiles, response assumptions, and confirmation scopes per server. A tool named `get_entity` on server A does not share the contract of a tool named `set_entity` on server B.

### 3. Manifest Intelligence

The tool manifest (15 fields, defined in `ref.mcp-server-standards` Tool Manifest Schema) is the primary input to the consumer's decision engine. Every field informs a specific decision.

#### Risk Class — "Should I invoke this?"

[L1+] The `risk` field determines the confirmation requirement.

| `risk`       | Default action                                               |
|--------------|--------------------------------------------------------------|
| `READ`       | Invoke freely. No confirmation required.                     |
| `WRITE`      | Confirm with user before first invocation in a workflow.     |
| `DESTRUCTIVE`| REQUIRE explicit user confirmation for every invocation.     |
| `DANGEROUS`  | Reject unless the user explicitly requested the tool by name; then confirm and display the full command. |
| `SENSITIVE`  | Invoke unless `requires_confirmation: true`. NEVER log, store, or echo the response data. |

1. [L1+] `risk: DESTRUCTIVE` or `risk: DANGEROUS` REQUIRES explicit user confirmation for every invocation. The agent MUST NOT proceed without it.
2. [L1+] `risk: WRITE` REQUIRES user confirmation at least once per workflow. Within a single confirmed workflow, subsequent WRITE invocations MAY proceed without re-confirmation.
3. [L1+] `risk: SENSITIVE` triggers a data handling constraint: the consumer MUST NOT log, cache, or display the response data. Pass it through, use it, discard it.
4. [L1+] `risk: READ` imposes no confirmation requirement. The consumer MAY invoke freely.

#### Side Effects — "What will this change?"

[L3+] The `side_effects` field refines the invocation decision.

| `side_effects` | Consumer implication                                       |
|----------------|------------------------------------------------------------|
| `none`         | Pure computation, no external state change. Fully safe.    |
| `read`         | Reads external state. Safe but may have latency/cost.      |
| `write`        | Persists state change. Combine with `reversible` for rollback planning. |
| `destructive`  | Destroys data or state. ALWAYS combined with risk: DESTRUCTIVE. |

#### Determinism — "Should I trust the result?"

[L3+] The `determinism` field informs whether the consumer can cache, compare, or rely on results.

| `determinism`         | Consumer behavior                                         |
|-----------------------|-----------------------------------------------------------|
| `deterministic`       | Results are cacheable. Same input → same output.          |
| `probabilistic`       | Results vary. Rerun may give different output. Do not cache. |
| `env-dependent`       | Results depend on environment state. Cache briefly.       |
| `eventually-consistent` | Results may lag behind reality. Do not treat as current. |

#### Retry Safety — "Should I retry on failure?"

[L1+] The `retryable` and `idempotent` fields together determine retry behavior.

- `retryable: true` + `idempotent: true` → Safe to retry with any backoff.
- `retryable: true` + `idempotent: false` → Retry only if the error code indicates idempotent failure (e.g., `TIMEOUT`).
- `retryable: false` → NEVER retry, regardless of error code. Escalate to user.

1. [L1+] The consumer MUST check `retryable` before retrying. Retrying a non-retryable tool is a contract violation.
2. [L2+] Retries MUST use exponential backoff: 1s → 2s → 4s → 8s → max 3 retries → escalate. This is the canonical retry policy.

#### Concurrency Safety — "Can I run this in parallel?"

[L3+] The `concurrent_safe` field governs parallel execution.

- `concurrent_safe: true` → Multiple invocations MAY run in parallel.
- `concurrent_safe: false` → Serialize. MUST NOT invoke concurrently.

1. [L3+] When orchestrating a batch of tool calls, the consumer MUST group by `concurrent_safe`. Parallel-safe tools run together; serial-only tools execute sequentially.

#### Latency and Cost — "How should I sequence calls?"

[L3+] The `latency`, `timeout_ms`, and `cost` fields inform invocation ordering.

1. [L3+] Prefer `instant`/`fast` tools for initial diagnostics and validation steps.
2. [L3+] Defer `slow`/`long-running` tools to later in the workflow or run them in parallel with independent tasks.
3. [L3+] Prefer `cheap` tools for repeated polling or iterative workflows.
4. [L3+] The `timeout_ms` field sets the consumer's expectation for how long the tool MAY take. The consumer SHOULD set its own invocation timeout to `timeout_ms + buffer` (e.g., `timeout_ms * 1.2`).

#### Impact, Privacy, Reversible — "What is the blast radius?"

[L3+] These fields inform workflow planning.

| Field        | Consumer use                                                    |
|--------------|-----------------------------------------------------------------|
| `impact`     | `service_outage` → warn user, schedule during low-activity.     |
| `privacy`    | `personal` → apply data handling constraints.                   |
| `reversible` | `false` → checkpoint BEFORE invocation in multi-step workflows. |

### 4. Capability Reasoning

[L1+] The consumer applies a structured decision tree before every tool invocation. The decision tree consumes manifest fields and produces one of four actions: `invoke`, `confirm_then_invoke`, `reject`, or `defer`.

#### Decision Tree

```
Given: tool manifest M, user intent I

1. Does M.risk == DANGEROUS?
   → YES: REJECT unless user explicitly requested this specific tool by name.
          If user did: CONFIRM_THEN_INVOKE (display full command).

2. Does M.risk == DESTRUCTIVE?
   → YES: CONFIRM_THEN_INVOKE (every invocation).

3. Is M.requires_confirmation == true?
   → YES: CONFIRM_THEN_INVOKE regardless of risk class.
          This step fires BEFORE WRITE/SENSITIVE/READ to ensure the override is never short-circuited.

4. Does M.risk == WRITE?
   → YES: If first WRITE in this workflow → CONFIRM_THEN_INVOKE.
          If already confirmed in this workflow → INVOKE.

5. Does M.risk == SENSITIVE?
   → YES: INVOKE (with data handling constraints — no logging, no caching, no display).

6. Does M.risk == READ?
   → YES: INVOKE freely.
```

1. [L1+] The consumer MUST follow this decision tree. Deviations REQUIRE documented rationale.
2. [L1+] `requires_confirmation: true` in the manifest ALWAYS triggers a confirmation gate, even for READ tools. This field overrides the risk-class default behavior.
3. [L2+] When the user confirms a WRITE workflow, the consumer SHOULD record the confirmation scope. Subsequent WRITE tools within the same explicit scope MAY proceed without re-confirmation.

#### Decision Policy Table

[L2+] The complete decision policy MUST be expressible as a testable table:

| `risk`         | `requires_confirmation` | `user_intent`       | `decision`              |
|----------------|-------------------------|---------------------|-------------------------|
| `READ`         | `false`                 | any                 | `invoke`                |
| `READ`         | `true`                  | any                 | `confirm_then_invoke`   |
| `WRITE`        | `false`                 | `general`           | `confirm_then_invoke`   |
| `WRITE`        | `false`                 | `confirmed_workflow`| `invoke`                |
| `WRITE`        | `true`                  | any                 | `confirm_then_invoke`   |
| `DESTRUCTIVE`  | any                     | any                 | `confirm_then_invoke`   |
| `DANGEROUS`    | any                     | `not_explicit`      | `reject`                |
| `DANGEROUS`    | any                     | `general`           | `reject`                |
| `DANGEROUS`    | any                     | any                 | `reject`                |
| `DANGEROUS`    | any                     | `explicit_by_name`  | `confirm_then_invoke`   |
| `SENSITIVE`    | `false`                 | any                 | `invoke`                |
| `SENSITIVE`    | `true`                  | any                 | `confirm_then_invoke`   |
| unknown/malformed | any                  | any                 | `defer`                 |

1. [L2+] Every row in this table MUST have a corresponding test case in the consumer test suite.
2. [L1+] Unknown or malformed `risk` values MUST NOT fall through to `invoke`. The consumer MUST defer or require confirmation with an explanation of the uncertainty.

### 5. Response Contract Handling

Every MCP tool returns a structured JSON response per the contract in `ref.mcp-server-standards`. The consumer MUST parse and branch on this contract.

#### Core Parsing

```
if response["success"] is True:
    data = response["data"]
    meta = response.get("_meta", {})
    proceed with data
else:
    error = response["error"]
    determine recovery action
```

1. [L1+] The consumer MUST check `"success"` as the first branching point in every response handler. Its absence is an error.
2. [L1+] The consumer MUST handle both string errors (`"error": "message"`) and structured errors (`"error": {"code": "...", ...}`).
3. [L1+] The consumer MUST ignore unknown fields in responses. New fields added by the server are backward-compatible.
4. [L1+] The consumer MUST NOT reject responses containing unrecognized keys in `data` or `_meta` objects.

#### Extended Error Parsing

[L2+] When `error` is a dict:

```
code = error["code"]          # e.g., "DEVICE_OFFLINE"
message = error["message"]     # Human-readable
retryable = error["retryable"] # bool
suggestion = error.get("suggestion")  # Optional: one-sentence next step
```

1. [L2+] The consumer MUST branch on `error.code`, not on `error.message`. The code is machine-readable and stable; the message is human-readable and may change.
2. [L2+] The consumer MUST use `error.retryable` to gate retry decisions, combined with the manifest's `retryable` field (see Error Recovery).

#### Pagination Awareness

[L1+] When a response contains pagination markers, the consumer MUST treat the result as incomplete.

1. [L1+] If a successful response contains `has_more`, `next_offset`, `next_cursor`, `offset`, `limit`, `total`, `page`, or `cursor` at the top level, inside `_meta`, or inside an object-shaped `data` envelope, the consumer MUST treat the result as partial until pagination is exhausted or the task scope is satisfied. The consumer MUST NOT conclude that an item does not exist from a partial page alone.
2. [L2+] The consumer SHOULD continue paginating when `has_more: true` and the task scope requires completeness. The consumer MAY stop paginating early if the desired scope is satisfied.

#### Negative Capability

[L1+] Empty successful results are meaningful signals, not errors.

1. [L1+] When `success` is `true` and `data` is an empty list `[]`, empty dict `{}`, `null`, `0`, or an object with `count: 0`, the consumer SHOULD interpret this as: the query completed successfully and found no matching items or problems. This result is meaningful and MUST NOT be treated as failure.
2. [L2+] The consumer SHOULD communicate empty results to the user as a positive diagnostic signal (e.g., "No issues found" rather than silence).

### 6. Error Recovery and Retry Logic

#### Error Strategy Matrix

[L1+] Every error code defined in `ref.mcp-server-standards` maps to a consumer recovery action. This matrix is normative.

| `error.code`              | `retry`      | `action`                                    |
|---------------------------|-------------|---------------------------------------------|
| `TIMEOUT`                 | YES          | Retry up to 3x with exponential backoff.    |
| `DEVICE_OFFLINE`          | YES          | Retry after delay (min 5s). Inform user.    |
| `RESOURCE_LOCKED`         | YES          | Re-read config, then retry with fresh hash. |
| `INTERNAL_ERROR`          | CONDITIONAL   | Retry once. If persists, escalate.          |
| `HTTP_ERROR`              | CONDITIONAL   | Retry if 5xx; escalate if 4xx.              |
| `AUTH_FAILED`             | NO           | Escalate. Check credentials.                |
| `INVALID_PARAM`           | NO           | Escalate. Fix the parameter.                |
| `UNSUPPORTED`             | NO           | Escalate. Operation not available.          |
| `DEPENDENCY_MISSING`      | NO           | Escalate. Install the dependency.           |
| `DEVICE_NOT_FOUND`        | NO           | Escalate. Suggest running a device scan.    |
| `VALIDATION_FAILED`       | NO           | Escalate. Fix the input to match schema.    |
| `RESOURCE_ALREADY_EXISTS` | NO           | Escalate. Choose a different name or delete.|
| `RESOURCE_NOT_FOUND`      | NO           | Escalate. Verify the identifier exists.     |

1. [L1+] The consumer MUST use this matrix to determine recovery actions. "Model discretion" is not an acceptable substitute for a defined error strategy.
2. [L2+] When retrying, the consumer MUST use exponential backoff: 1s initial → 2s → 4s → 8s (cap). Maximum 3 retries. After max retries, escalate to user.
3. [L1+] When escalating, the consumer MUST include: the tool name, the error code, the error message, the retry count (if applicable), and the error suggestion (if present).
4. [L2+] For `HTTP_ERROR` with a 4xx status code, the consumer MUST NOT retry and MUST escalate with the full status code and response body (sanitized).
5. [L2+] For `HTTP_ERROR` with a 5xx status code, the consumer MAY retry once.

#### Compound Error Checking

[L2+] The consumer MUST cross-reference the server's `error.retryable` with the manifest's `retryable`:

```
if manifest.retryable == false:
    NEVER retry, regardless of error.retryable
elif error.retryable == false:
    NEVER retry, regardless of manifest.retryable
elif both are true:
    retry per the error strategy matrix and backoff policy
```

1. [L2+] Both the manifest AND the error response must agree for a retry to proceed. If either says `retryable: false`, retry is forbidden.

### 7. Workflow Orchestration

[L2+] Multi-step workflows chain tool invocations where later steps depend on earlier results.

#### Confirmation Gates

1. [L2+] The consumer MUST place confirmation gates BEFORE any DESTRUCTIVE or DANGEROUS tool in a workflow. The gate pauses execution and displays to the user: the tool name, the risk class, the expected impact, and the reversibility status.
2. [L2+] WRITE confirmation scope is bounded by target set, operation type, and user-stated objective. Changing multiple distinct targets requires a confirmation summary listing all targets. A new target outside the confirmed scope requires re-confirmation. DESTRUCTIVE always requires separate confirmation regardless of scope.
3. [L2+] A WRITE confirmation scope is bounded by the explicit user request. A new user request resets the confirmation scope.

#### Checkpoint and Rollback

1. [L2+] When a workflow step has `reversible: false` in the manifest, the consumer MUST save a checkpoint of relevant state BEFORE invoking that tool.
2. [L2+] When a downstream step fails after a non-reversible step, the consumer MUST inform the user that automatic rollback is not possible and report the checkpoint state.
3. [L3+] For reversible operations (`reversible: true`, idempotent writes), the consumer SHOULD execute a compensating action on downstream failure.

#### Workflow Safety Rules

1. [L2+] A workflow MUST NOT contain more than one DESTRUCTIVE tool without an explicit user re-confirmation between them.
2. [L2+] A workflow MUST NOT execute a DESTRUCTIVE tool followed by a WRITE tool without a checkpoint between them.
3. [L2+] When building a shell command workflow from agent input, the consumer MUST ensure the command passes through server-side allowlist validation before execution. The consumer MUST NOT concatenate user input into a command string without validation.
4. [L2+] A workflow containing a SENSITIVE tool MUST NOT pass its un-sanitized output to a non-SENSITIVE tool that persists or displays data. SENSITIVE data stays within the SENSITIVE boundary.

#### Cross-Server Workflows

[L2+] When a task spans multiple MCP servers:

1. [L2+] The consumer MUST maintain separate tool catalogs, capability profiles, response assumptions, and confirmation scopes per server. A tool on server A does not share the contract of a similarly-named tool on server B.
2. [L2+] The consumer SHOULD use READ tools from a read-only server for discovery and diagnostics, WRITE tools from a writable server for modifications, and READ tools from the first server (or any trusted source) for verification.
3. [L2+] The consumer MUST NOT assume that tools with similar names across servers have the same parameters, return types, or error codes.

### 8. Observability and Diagnostics

[L1+] The consumer uses `_meta` fields to correlate requests, detect regressions, and diagnose failures.

#### Standard Meta Fields

| Field           | Consumer use                                                  |
|-----------------|---------------------------------------------------------------|
| `request_id`    | Correlate logs across invocations. Include in error reports.  |
| `duration_ms`   | Detect performance regressions. Flag if > 2x historical norm. |
| `tool_version`   | Inspect before invoking. Adapt to version-specific behavior.  |
| `cached`        | If `true`, the result may be stale. Consider `force` param.   |
| `retry_safe`    | If `true`, safe to re-issue with the same arguments.          |

1. [L1+] When reporting an error to the user, the consumer MUST include the `request_id` from the `_meta` envelope for correlation.
2. [L2+] The consumer SHOULD track `duration_ms` across invocations of the same tool to detect performance regressions.
3. [L2+] When `cached: true`, the consumer SHOULD mention this to the user and offer a `force` re-fetch option if the data appears stale.
4. [L3+] The consumer SHOULD maintain a local invocation log with: timestamp, tool name, request_id, duration_ms, success/failure, error code.

#### Diagnostic Workflow

[L2+] When a non-recoverable error occurs, the consumer executes a diagnostic sequence:

1. Extract `error.code` and `error.message` from the response
2. Look up `error.suggestion` for actionable next step
3. Retrieve `request_id` from `_meta`
4. Check if the same `request_id` has prior errors in the local log
5. Present to the user: tool name, error code, message, suggestion, request_id, retry count, correlation context

### 9. Version Compatibility

[SHOULD] The consumer adapts to different versions of the same tool without hardcoded assumptions about the response shape.

#### Forward Compatibility

1. [L1+] The consumer MUST ignore unknown fields in tool responses. Adding new fields to responses is backward-compatible by definition.
2. [L1+] The consumer MUST ignore unknown fields in manifest objects. New manifest fields defined by future server versions are invisible to older consumers.
3. [L1+] The consumer MUST NOT crash or reject a response because it contains an unrecognized error code. Handle unrecognized error codes as non-retryable escalation with the original code preserved in diagnostics.

#### Backward Compatibility

1. [L2+] The consumer MUST tolerate missing `_meta` fields. Older servers may not return the envelope.
2. [L2+] The consumer MUST tolerate missing extended error fields (`code`, `retryable`, `suggestion`). Fall back to string error parsing.
3. [L2+] The consumer MUST tolerate missing manifest fields. Treat absent fields as their safest default: `risk: READ`, `retryable: false`, `requires_confirmation: false`, `concurrent_safe: false`.

#### Version-Aware Invocation

1. [SHOULD] Before invoking a tool, the consumer SHOULD inspect `tool_version` from the health endpoint or capability introspection tool.
2. [SHOULD] When invoking a tool first seen at a new version, the consumer SHOULD verify the response shape matches expectations by checking that required fields exist.

#### Contract Degradation

[L1+] When an L4 tool (full manifest, structured errors, metadata envelope) is queried by an L1 consumer, the L1 consumer MUST still function correctly using only the core response contract (`success`, `data`, `error`). This is the fundamental compatibility guarantee.

## INTERFACES

- INPUT: Tool manifest (15-field JSON object from `ref.mcp-server-standards` Tool Manifest Schema), tool response (structured JSON per Response Contract), user intent classification, workflow state (confirmation scope, invocation log, checkpoints), capability introspection tool output
- OUTPUT: Invocation decisions (`invoke` / `confirm_then_invoke` / `reject` / `defer`), parsed response data, error recovery actions (`retry` / `abort` / `escalate`), confirmation requests to user, diagnostic reports, rollback instructions
- SIDE_EFFECTS: Confirmations prompt user interaction. Retries issue additional tool calls. Workflows modify external state through invoked tools.

## STATE

- Assumptions: The server follows the response contract defined in `ref.mcp-server-standards`. Tool manifests are available via capability introspection or `tools/list`. Error codes match the 13 defined in the server standard. The consumer has access to the tool catalog before any invocation. The user provides intent classification through natural language interactions.
- Constraints: The decision policy table is finite and testable. Every row in the normative decision policy table MUST have a corresponding test. The error strategy matrix covers all 13 error codes exactly. Retry count is bounded at 3 per invocation. Workflow depth is bounded by the number of chained tool calls.
- Known_Limitations: Consumer cannot verify manifest accuracy — it trusts the server's self-declared capabilities. A misconfigured manifest (e.g., DESTRUCTIVE tool labelled WRITE) leads to incorrect consumer decisions. The consumer cannot prevent a server from executing a tool after invocation; confirmation gates are advisory. Version compatibility relies on the server honoring backward compatibility rules.

## EDGE_CASES

- CASE: Tool returns `success: true` but `data` contains an error message in prose → EXPECTED: Consumer treats the response as successful. It cannot parse intent from prose. If the data appears anomalous, the consumer MAY note this to the user.
- CASE: Manifest says `retryable: false` but error says `retryable: true` → EXPECTED: Consumer does NOT retry. Manifest is authoritative over error response. Escalate to user.
- CASE: Manifest is absent (L1 server, no capability introspection) → EXPECTED: Consumer falls back to risk annotation in docstring (`[READ]`, `[WRITE]`, and other prefixes). If both absent, treat as `READ`.
- CASE: User confirms WRITE workflow, but a tool in the workflow is reclassified to DESTRUCTIVE mid-execution → EXPECTED: Consumer pauses and re-requests confirmation specifically for the DESTRUCTIVE step.
- CASE: Retry count exhausted (3 retries) and error persists → EXPECTED: Consumer escalates with full diagnostic context (tool name, error code, retry log, request_id, suggestion).

### Pitfalls

#### Decision Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| **Invoking DESTRUCTIVE without confirmation** | Agent reboots a device or deletes data without asking | Follow the decision tree: DESTRUCTIVE ALWAYS requires confirmation. |
| **Retrying non-retryable errors** | Agent retries `AUTH_FAILED` 3 times, locking the account | Check the error strategy matrix: `AUTH_FAILED` → NO retry. |
| **Displaying SENSITIVE data** | Credentials or PII appear in agent output | SENSITIVE data constraint: pass through, use, never display or log. |
| **Trusting docstring over manifest** | Docstring says "safe read" but manifest says `risk: WRITE` | Manifest is authoritative. Never override manifest with docstring inference. |
| **Parallelizing non-concurrent-safe tools** | Two `reboot_device` calls execute simultaneously | Check `concurrent_safe` before batch execution. |

#### Workflow Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| **No checkpoint before DESTRUCTIVE** | Factory reset succeeds, subsequent config push fails, state lost | Save checkpoint before every non-reversible step. |
| **Silently swallowing workflow errors** | Step 3 of 5 fails, agent proceeds to step 4 with bad data | Halt workflow on any error. Never proceed with corrupted inputs. |
| **Confirmation scope leak** | User confirms "restart service X", agent also restarts service Y | Confirmation scope is bounded by the explicit user request. |
| **Unbounded retry loop** | Agent retries indefinitely, consuming resources | Maximum 3 retries. Always bounded. |

#### Version Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| **Hardcoding response shape** | Agent breaks when a new field is added to responses | Ignore unknown fields. Never fail on unrecognized keys. |
| **Assuming error codes are complete** | New error code added server-side, consumer crashes | Unknown codes → treat as `INTERNAL_ERROR`. |
| **Relying on absent manifest fields** | Agent fails on L1 server with no manifest | Fall back to docstring risk prefix. Absent → READ. |

## EXAMPLES

### Canonical Templates

These are strict decision templates for AI agents consuming MCP tools. They are the consumer-side equivalent of the server-side canonical templates in `ref.mcp-server-standards`.

#### Canonical Template C1 — Risk-Based Decision Tree

Every tool invocation starts with this decision tree. This template matches the implementation in `evaluate_decision()` from `decision_engine.py`. The function is table-driven — the pseudocode below shows the equivalent logic for clarity; the actual engine uses `DECISION_POLICY` (see C6) to produce identical results:

```python
def evaluate_decision(risk: str, requires_confirmation: bool, user_intent: str) -> str:
    # The engine uses DECISION_POLICY (Canonical Template C6) as a lookup
    # table. This pseudocode produces the same results for illustration.

    # DANGEROUS requires explicit user request by tool name
    if risk == "DANGEROUS":
        if user_intent != "explicit_by_name":
            return "reject"
        return "confirm_then_invoke"

    # DESTRUCTIVE always requires confirmation
    if risk == "DESTRUCTIVE":
        return "confirm_then_invoke"

    # requires_confirmation overrides all lower risk classes
    if requires_confirmation:
        return "confirm_then_invoke"

    # WRITE: confirm unless already in a confirmed workflow
    if risk == "WRITE":
        if user_intent == "confirmed_workflow":
            return "invoke"
        return "confirm_then_invoke"

    # SENSITIVE: invoke with data handling constraints
    if risk == "SENSITIVE":
        return "invoke"

    # READ: invoke freely
    if risk == "READ":
        return "invoke"

    # Unknown risk: defer (never invoke)
    return "defer"
```

Note: C1 takes pre-extracted `risk` and `requires_confirmation` as direct parameters. The caller (consumer) is responsible for extracting these from the manifest or capability profile before calling this function. Workflow confirmation state is passed via `user_intent="confirmed_workflow"` rather than a separate boolean parameter.

#### Canonical Template C2 — Response Parsing with Error Branching

```
def handle_response(response: dict) -> tuple[bool, object, str | None]:
    success = response.get("success")
    if success is None:
        return False, None, "MISSING_SUCCESS_FIELD"

    if success is True:
        data = response.get("data")
        meta = response.get("_meta", {})
        return True, data, None

    error = response.get("error")
    if isinstance(error, dict):
        code = error.get("code", "UNKNOWN")
        return False, error, code
    elif isinstance(error, str):
        return False, error, "UNKNOWN"
    return False, "Unknown error", "UNKNOWN"
```

#### Canonical Template C3 — Error Strategy Matrix

```
ERROR_STRATEGY = {
    "TIMEOUT":                {"retry": True,  "max_retries": 3, "action": "retry"},
    "DEVICE_OFFLINE":         {"retry": True,  "max_retries": 3, "action": "retry"},
    "RESOURCE_LOCKED":        {"retry": True,  "max_retries": 3, "action": "retry_reread"},
    "INTERNAL_ERROR":         {"retry": True,  "max_retries": 1, "action": "retry_once"},
    "HTTP_ERROR":             {"retry": False, "max_retries": 0, "action": "escalate"},
    "AUTH_FAILED":            {"retry": False, "max_retries": 0, "action": "escalate"},
    "INVALID_PARAM":          {"retry": False, "max_retries": 0, "action": "escalate"},
    "UNSUPPORTED":            {"retry": False, "max_retries": 0, "action": "escalate"},
    "DEPENDENCY_MISSING":     {"retry": False, "max_retries": 0, "action": "escalate"},
    "DEVICE_NOT_FOUND":       {"retry": False, "max_retries": 0, "action": "escalate"},
    "VALIDATION_FAILED":      {"retry": False, "max_retries": 0, "action": "escalate"},
    "RESOURCE_ALREADY_EXISTS":{"retry": False, "max_retries": 0, "action": "escalate"},
    "RESOURCE_NOT_FOUND":     {"retry": False, "max_retries": 0, "action": "escalate"},
}

def get_error_strategy(error_code: str, manifest: dict) -> dict:
    strategy = ERROR_STRATEGY.get(error_code, {"retry": False, "max_retries": 0, "action": "escalate"})

    if not manifest.get("retryable", False):
        strategy = {**strategy, "retry": False, "max_retries": 0, "action": "escalate"}

    return strategy
```

#### Canonical Template C4 — Confirmation Gate

```
def requires_user_confirmation(manifest: dict, user_intent: str, workflow_confirmed: bool) -> tuple[bool, str]:
    risk = manifest.get("risk", "READ")
    requires_confirm = manifest.get("requires_confirmation", False)

    if risk == "DANGEROUS":
        if user_intent != "explicit_by_name":
            return False, "DANGEROUS tool rejected: user must request it by name"
        return True, f"Confirm execution of DANGEROUS tool: {manifest['name']}"

    if risk == "DESTRUCTIVE":
        impact = manifest.get("impact", "unknown")
        reversible = manifest.get("reversible", False)
        extra = f" (impact: {impact}, reversible: {reversible})"
        return True, f"Confirm DESTRUCTIVE operation: {manifest['name']}{extra}"

    if risk == "WRITE" and not workflow_confirmed:
        return True, f"Confirm WRITE operation: {manifest['name']}"

    if requires_confirm:
        return True, f"Tool requires confirmation: {manifest['name']}"

    return False, ""
```

#### Canonical Template C5 — Retry with Exponential Backoff

```
async def invoke_with_retry(tool_fn, error_strategy: dict, *args, **kwargs):
    max_retries = error_strategy["max_retries"]
    for attempt in range(max_retries + 1):
        response = await tool_fn(*args, **kwargs)
        if response.get("success") is True:
            return response

        error = response.get("error", {})
        if isinstance(error, dict) and not error.get("retryable", True):
            return response

        if attempt < max_retries:
            delay = 2 ** attempt  # 1s, 2s, 4s
            await asyncio_sleep(delay)
        else:
            return response

    return response
```

#### Canonical Template C6 — Decision Policy Table (Complete)

The full normative table — every cell is testable:

```
DECISION_POLICY = [
    # (risk, requires_confirmation, user_intent, expected_decision)
    ("READ",        False,  "any",                "invoke"),
    ("READ",        True,   "any",                "confirm_then_invoke"),
    ("WRITE",       False,  "general",            "confirm_then_invoke"),
    ("WRITE",       False,  "confirmed_workflow", "invoke"),
    ("WRITE",       False,  "any",                "confirm_then_invoke"),
    ("WRITE",       True,   "confirmed_workflow", "confirm_then_invoke"),
    ("WRITE",       True,   "general",            "confirm_then_invoke"),
    ("WRITE",       True,   "any",                "confirm_then_invoke"),
    ("DESTRUCTIVE", False,  "any",                "confirm_then_invoke"),
    ("DESTRUCTIVE", True,   "any",                "confirm_then_invoke"),
    ("DANGEROUS",   False,  "general",            "reject"),
    ("DANGEROUS",   True,   "general",            "reject"),
    ("DANGEROUS",   False,  "any",                "reject"),
    ("DANGEROUS",   True,   "any",                "reject"),
    ("DANGEROUS",   False,  "not_explicit",       "reject"),
    ("DANGEROUS",   True,   "not_explicit",       "reject"),
    ("DANGEROUS",   False,  "explicit_by_name",   "confirm_then_invoke"),
    ("DANGEROUS",   True,   "explicit_by_name",   "confirm_then_invoke"),
    ("SENSITIVE",   False,  "any",                "invoke"),
    ("SENSITIVE",   True,   "any",                "confirm_then_invoke"),
]

def evaluate_decision(risk: str, requires_confirmation: bool, user_intent: str) -> str:
    for r, rc, ui, decision in DECISION_POLICY:
        if r == risk and rc == requires_confirmation and ui in (user_intent, "any"):
            return decision
    return "defer"
```

Unknown or malformed risk values are intentionally absent from `DECISION_POLICY`; the `return "defer"` fallback is the normative behavior.

#### Canonical Template C7 — Capability-Based Tool Selection

```
def select_tool_for_task(tools: list[dict], task_type: str) -> dict | None:
    """Select the best tool for a task type based on manifest fields."""
    candidates = {
        "diagnose": lambda m: m.get("risk") == "READ" and m.get("latency") in ("instant", "fast"),
        "configure": lambda m: m.get("risk") == "WRITE" and m.get("reversible", False),
        "destroy": lambda m: m.get("risk") == "DESTRUCTIVE",
        "scan": lambda m: m.get("determinism") == "eventually-consistent",
        "read_sensitive": lambda m: m.get("risk") == "SENSITIVE",
    }

    matcher = candidates.get(task_type)
    if not matcher:
        return None

    for tool in tools:
        manifest = tool.get("manifest", {})
        if matcher(manifest):
            return tool
    return None
```

#### Canonical Template C8 — Workflow Orchestration with Checkpoint

```
async def run_workflow(steps: list[dict], tools: dict):
    """Execute a workflow with checkpoints before non-reversible steps."""
    checkpoints = {}
    confirmations = set()

    for i, step in enumerate(steps):
        tool_name = step["tool"]
        manifest = step.get("manifest", {})
        params = step.get("params", {})

        decision = decide_invocation(manifest, step.get("intent", "general"),
                                     bool(confirmations))
        if decision == "reject":
            raise WorkflowError(f"Step {i} ({tool_name}) rejected by policy")
        if decision == "confirm_then_invoke" and tool_name not in confirmations:
            confirmations.add(tool_name)

        if not manifest.get("reversible", True):
            checkpoints[i] = await save_checkpoint(tool_name, params)

        response = await tools[tool_name](**params)

        if not response.get("success"):
            if not manifest.get("reversible", True):
                return WorkflowResult(
                    success=False,
                    error=response.get("error"),
                    checkpoint=checkpoints[i],
                    message="Non-reversible step failed. Manual rollback required."
                )
            else:
                await rollback_steps(steps[:i], tools, checkpoints)
                return WorkflowResult(success=False, error=response.get("error"))

    return WorkflowResult(success=True, data=response.get("data"))
```

#### Canonical Template C9 — Progressive Disclosure

[L2+] The consumer starts with minimal detail and drills into selected items.

```
# Phase 1 — List/search with minimal detail
list_result = await tools["list_resources"](detail_level="minimal")
items = list_result.get("data", [])
candidates = [item for item in items if matches_criteria(item)]

# Phase 2 — Fetch detail only for candidates
for c in candidates:
    detail = await tools["get_resource"](identifier=c["id"], detail_level="full")
    process(detail)
```

1. Start with list, overview, search, summary, or diagnostic tool with minimal parameters.
2. Filter candidates using returned identifiers, names, states, or metadata.
3. Drill into selected items with full-detail tools.
4. Never fetch full detail for all items before narrowing scope unless the user explicitly requested a full export.

#### Canonical Template C10 — Batch/Composite Preference

[L1+] Before N individual calls, scan for batch alternatives.

```
def select_tool_for_multi_read(tools: list[dict], task: dict) -> dict | None:
    """Prefer a batch/composite READ tool over N individual calls."""
    repeat_count = task.get("repeated_count", 1)
    if repeat_count <= 1:
        return None

    for tool in tools:
        name = tool.get("name", "")
        manifest = tool.get("manifest", {})
        if manifest.get("risk", "READ") != "READ":
            continue
        if any(hint in name.lower() for hint in BATCH_HINTS):
            return tool

    return None
```

Batch hints in tool names (`_batch`, `bulk_`, `diagnose_`, `composite_`, `summary_`, and similar prefixes) are efficiency heuristics — they do not replace capability verification through the manifest or risk prefix.

## NON_GOALS

- Does not cover MCP server implementation — that is the domain of `ref.mcp-server-standards`.
- Does not define wire protocol, transport binding, or message serialization.
- Does not specify agent runtime architecture, model selection, or prompt engineering.
- Does not cover authentication or authorization between agent and MCP server — the consumer operates with the credentials it has.
- Does not define how the user interface presents confirmations or diagnostic information.
- Does not replace project-specific `AGENTS.md` files.
- Does not cover multi-agent coordination or agent-to-agent communication.
