---
description: Core architectural standard for MCP servers — tool design, response contracts, versioning, capability model, logging, testing, security, and operational safety
doc_id: ref.mcp-server-standards
type: ref
status: active
ttl_days: 180
rigor_tier: L2
stability: stable
ai_scope: editable
domain: mcp
tags: ["mcp", "server", "standards", "core", "testing", "security"]
owners: ["backend-team"]
upstream:
  - ref.documentation-standard
  - ref.ci-cd-standard
  - ref.mcp-consumer-standards
source_of_truth: true
last_verified: 2026-05-17
---

# MCP Server Core Standard

> **Document family:** This is the CORE standard — universal, framework-agnostic rules for MCP server design.
> Python/FastMCP implementation notes are integrated in this document (see Python/FastMCP Implementation Notes section under RULES).

## PURPOSE

Define universal, framework-agnostic patterns and rules for building MCP (Model Context Protocol) servers. Covers tool design, response contracts, versioning, capability metadata, logging, common pitfalls, implementation patterns, testing standards, security, and operational safety. Every MCP server project SHOULD follow the applicable maturity-level requirements.

This document integrates the testing standards (test hierarchy, skip patterns, coverage, CI, mock patterns) and security standards (SSE transport security, cancellation, concurrency, blocked data, filesystem access control, secret management, observability).

This document is the CORE.

## SCOPE

- INCLUDED: tool implementation patterns, response contract design, capability descriptors, manifest schema, versioning policy, parameter design, logging, secret management, documentation conventions, testing standards (test hierarchy, skip patterns, coverage, CI, mock patterns), security standards (SSE transport security, cancellation, concurrency, blocked data, filesystem access control, secret management, observability), consumer ergonomics (batch/composite tools, minimal-detail parameters, pagination, empty-success contracts, stable identifiers)
- EXCLUDED: MCP protocol specification, deployment infrastructure, domain-specific business logic, network-level firewall rules, application-level authorization

## DEFINITIONS

- `MCP tool`: A function exposed through MCP transport that returns a structured response with a `"success"` boolean or equivalent status indicator. [L1+]
- `internal function`: A private function (`_function_name`) that implements the actual logic. Directly testable without MCP infrastructure. [L1+]
- `registration function`: A `register_<category>_tools(mcp)` function that registers all tools in a module. [L1+]
- `tool wrapper`: The transport-facing layer that delegates to the internal function. Contains `try/except Exception` and formats the response. [L1+]
- `SSOT (Single Source of Truth)`: A principle requiring each configuration default to be defined in exactly one location (`tools/constants.py`). [L1+]
- `response wrapper`: Helper functions (`_success_response`, `_error_response`) that format every tool response consistently. [L1+]
- `capability descriptor`: Metadata annotation on a tool describing its operational profile: risk, side effects, determinism, retry safety, latency, cost. [L3+]
- `tool manifest`: A machine-readable JSON schema describing a tool's capability profile, version, and constraints. [L2+]
- `extensible envelope`: A response structure that MAY include optional `_meta` fields (`request_id`, `duration_ms`, `tool_version`) alongside the core response fields. [SHOULD]
- `SSE (Server-Sent Events)`: HTTP-based transport for MCP that exposes tools over HTTP. Without authentication, binding to a public interface grants remote code execution to anyone on the network.
- `Cancellation`: Aborting an in-flight operation in response to a signal (agent disconnect, transport close), with resource cleanup and controlled error response.
- `Concurrency`: Multiple tool invocations executing simultaneously. Without a defined model, shared state access and resource contention become non-deterministic.
- `Blocked Data`: Registries/namespaces (e.g., `auth`, `onboarding`) that are prohibited from being read by AI agents as defense-in-depth.
- `Observability`: Telemetry including correlation IDs (`request_id`), audit trails, per-tool metrics, log sanitization, and stderr logging.
- `Test hierarchy`: The four-level test suite model (unit, integration, smoke, e2e) defined by the maturity levels L1-L4.
- `Smoke test`: A minimal test that verifies basic server startup and tool registration without external dependencies.

## RULES

### 1. Tool Design

1. [L1+] Every tool MUST return a structured machine-readable response. JSON string is the default and recommended format. Alternative serialization formats are permitted when the transport layer supports structured outputs natively, provided a `"success"` boolean or equivalent status indicator is present.
2. [L1+] The first line of every tool docstring MUST be a complete sentence ending with a period describing what the tool does.
3. [L2+] Every tool docstring SHOULD include `Args:` and `Returns:` blocks. At L1, a one-line description is sufficient.
4. [L1+] All tool descriptions, response strings, and error messages MUST be in English. No emoji in any API-facing string.
5. [L1+] The implementation MUST follow a two-layer pattern: an internal function (`_do_operation`) containing all logic, directly unit-testable, and a transport-facing wrapper that delegates to the internal function.
6. [L1+] Every tool wrapper MUST wrap the internal function call in `try/except Exception` and return a structured error response on failure. The internal function MUST NOT need this handler itself.
7. [L1+] All tools MUST use consistent response helper functions (`_success_response(data)`, `_error_response(msg)`) instead of raw serialization calls.
8. [L1+] The server MUST NOT crash when a single tool raises an unhandled exception. Every tool MUST catch `Exception` at the top level.
9. [L2+] Parameters serving the same semantic role across tools SHOULD use the same name. `read_file(file_path=...)` and `read_config_file(file_path=...)` both use `file_path`.
10. [L2+] Every `list_*` tool SHOULD return the identifier needed to call the corresponding `get_*` tool. The identifier field name SHOULD match the parameter name of the get tool.

### 2. REST API and Health Endpoints

1. [L2+] The server SHOULD expose a health endpoint returning `{"status": "healthy"}` with tool count and version information. At L1 this is optional.
2. [L2+] If a REST API is provided, it SHOULD expose: `GET /api/health`, `GET /api/tools`, `POST /api/tools/{tool_name}`. At L1, health-only is sufficient.
2a. [L2+] The REST API SHOULD expose `GET /api/tools/{tool_name}/manifest` returning the tool's manifest entry from `TOOL_MANIFESTS`. This enables AI agents to inspect capability metadata without invoking the tool itself (see L3+ Exposure rule).
2b. [L3+] The server SHOULD expose a capability-introspection MCP tool (naming convention: `describe_<domain>_capabilities`) that returns the full tool catalog with manifests, supported transports, and `schema_version`. The REST manifest endpoint (2a) is unreachable for agents connected over pure MCP/SSE; an MCP tool exposes the same metadata over the MCP transport itself. The introspection tool MUST be zero-I/O, `[READ]`, and `instant` latency. Reference: `openwrt-mcp` `describe_router_capabilities` at `src/openwrt_mcp/tools/registration.py`.
2c. [L2+] `GET /api/tools` MUST return a JSON object with BOTH `total` and `tool_count` keys for backward compatibility. `GET /api/health` MUST include `tool_count` (not `total`). Implementations that use `total` alone (legacy) MUST add `tool_count` as an alias. This ensures CI smoke tests and AI agents can rely on a single key name across all MCP servers.

```json
{
  "total": 24,
  "tool_count": 24,
  "tools": [...]
}
```

```json
{
  "status": "healthy",
  "tool_count": 24,
  "tools_version": "1.2.0"
}
```

3. [L2+] The server SHOULD expose MCP transport on a dedicated port. SSE and REST ports MUST be distinct when both are used.
4. [L1+] All HTTP requests to external services MUST include a timeout parameter. The default timeout SHOULD be between 5 and 10 seconds.

### 3. Documentation

1. [L1+] `README.md` SHOULD include: project overview, requirements, quick start, available tools table, configuration reference, testing instructions.
2. [L1+] `.env.example` MUST list every supported environment variable with its default value in commented form.
3. [L1+] Test fixtures and examples MUST use generic names. Never use real device names, real IP addresses, or real credentials in documentation examples.

### 4. Input Validation

1. [L2+] All input validation SHOULD be centralized in a dedicated module (e.g., `validators.py`). At L1, inline validation is acceptable.
2. [L1+] Validation MUST run BEFORE any I/O operation. Validate parameters at function entry, never after a network call.
3. [L2+] A `ValidationError(Exception)` class SHOULD be defined. All `validate_*` functions SHOULD raise `ValidationError` for invalid input.
4. [L2+] Validation SHOULD cover: path traversal (`..`, `~`), port range (1–65535), dangerous shell commands, invalid service names, empty strings, and content size limits.
5. [L1+] `None` MUST NEVER be passed to string operations. Validate that required parameters are present and non-empty before use.

### 5. Project Structure

1. [L2+] Source code SHOULD live under `src/` for install isolation. A `tools/` directory with one Python module per tool category is RECOMMENDED.
2. [L1+] The project MUST have a `tools/constants.py` file as the SSOT for all environment variable defaults.
3. [L2+] `pyproject.toml` SHOULD define a CLI entry point. At L1, `python -m <package>` is sufficient.
4. [L2+] `__init__.py` SHOULD be empty except for a version string. It SHOULD NOT import submodules.
5. [L2+] Optional utility modules MUST be importable but their absence MUST NOT crash the server.

### Design Philosophy

Every rule in this standard flows from five principles. Understanding these prevents cargo-cult compliance.

#### 1. AI-First Operability

MCP tools are consumed primarily by AI agents, not humans. Agents cannot infer intent from ambiguous output. They need structured, deterministic, machine-readable contracts. Every tool MUST expose its semantics through data structures the agent can branch on — not through prose the agent must parse.

#### 2. Graceful Degradation

A single tool failure MUST NOT take down the server. A missing optional dependency MUST NOT prevent unrelated tools from functioning. A corrupted cache MUST NOT crash the loader. The server survives partial failure because agents depend on it for every action.

#### 3. Testability Over Cleverness

Internal functions are directly callable without MCP infrastructure. Every branch has a unit test. Tools that cannot be tested in isolation cannot be trusted in production. The two-layer pattern (internal function + decorated wrapper) is non-negotiable because it enables this.

#### 4. Survivability Under Partial Failure

External services become unreachable. Devices go offline. Brokers disconnect. The server MUST return controlled errors, not exceptions. Every integration point has a timeout. Every tool handler catches `Exception` at the top level.

#### 5. Human + Agent Co-Maintainability

Code is maintained by both humans and AI coding agents. Conventions must be explicit. Structure must be navigable by pattern matching. Standards must be falsifiable — a rule that cannot be checked by a test or a linter is not a rule.

### Maturity Levels

This standard defines four compliance levels. Each rule, pattern, and section is annotated with the minimum level at which it becomes required. Higher levels inherit all requirements from lower levels.

| Level | Name     | Target Use Case                        | Required Test Suites         | Key Additions                                           |
|-------|----------|----------------------------------------|------------------------------|---------------------------------------------------------|
| L1    | Personal | Solo MCP, prototypes, 3–10 tools       | Unit tests only              | Core tool design, error handling, SSOT, English only    |
| L2    | Team     | Internal team server, shared MCP       | Unit + Integration           | Test hierarchy, CI pipeline, REST API/health endpoints  |
| L3    | Production | Critical AI infra, always-on service | Unit + Smoke + Integ + E2E   | Coverage targets (≥80%), compliance tests, logging      |
| L4    | Hardened | Multi-tenant, dangerous tools, public  | All suites + compliance matrix | Blocked data sources, input sanitization, allowlist I/O |

**Annotation convention used throughout this document:**

- `[L1+]` — Required at all levels (core invariant; override requires explicit justification)
- `[L2+]` — Required at L2 and above
- `[L3+]` — Required at L3 and above
- `[L4]`  — Required only at Hardened level
- `[SHOULD]` — Strongly recommended at all levels but may be overridden with documented rationale
- `[MAY]` — Optional convenience; adopt when applicable

Rules without an explicit annotation default to `[L2+]` (team-level baseline).

### Tool Capability Model

Every MCP tool MUST communicate its operational profile to AI agents. This enables agents to make informed decisions about invocation safety, retry behavior, and resource consumption.

#### Risk Annotations (L1+)

Every tool description MUST include a risk prefix as the first text.

| Prefix         | Meaning                                  | When to use                                     | Examples                                    |
|----------------|------------------------------------------|-------------------------------------------------|---------------------------------------------|
| `[READ]`       | Read-only, no side effects               | Pure diagnostics, queries, data listings        | `get_status`, `list_items`, `ping_host`     |
| `[WRITE]`      | Modifies state — designed as **reversible** or **idempotent** | Config changes, value updates, reversible toggles | `update_config`, `set_setting`, `enable_feature` |
| `[DESTRUCTIVE]`| Kills processes, deletes data, or causes service outage — designed as **irreversible** | Deleting files, factory reset, device reboot  | `delete_item`, `reboot_device`, `factory_reset` |
| `[DANGEROUS]`  | Executes arbitrary shell commands        | Unrestricted command execution                  | `run_command`, `execute_script`             |
| `[SENSITIVE]`  | Returns credentials, tokens, or personal data | Auth tokens, passwords, PII                  | `get_token`, `read_secret`, `list_wifi_passwords` |

Rules:

1. [L2+] The Tool Manifest is the Single Source of Truth (SSOT) for tool capabilities. Risk annotations in docstrings MUST NOT be manually authored if a manifest exists; they SHOULD be dynamically injected by the framework. For L1 (no manifest), the manual prefix is REQUIRED.
2. [L1+] The default prefix is `[READ]` when no write, destructive, or sensitive effects exist.
3. [L3+] Unit tests SHOULD verify that every tool has a risk prefix matching its behavior.
4. [L1+] AI agents use the prefix to decide whether to request user confirmation. A missing prefix implies `[READ]`.

#### Side Effects (L3+)

| Class       | Meaning                                              | Guidance                                      |
|-------------|------------------------------------------------------|-----------------------------------------------|
| `none`      | Pure read; no state mutation on any system           | Always `[READ]` tools                         |
| `read`      | Reads from external systems (caches, network calls)  | Always `[READ]` tools                         |
| `write`     | Mutates persistent state (files, DB, config)         | `[WRITE]` — **reversible** in normal operation   |
| `destructive` | Destroys or permanently deletes data                | Always `[DESTRUCTIVE]` — designed as **irreversible** |

#### Determinism Classes (L3+)

| Class                 | Meaning                                                           |
|-----------------------|-------------------------------------------------------------------|
| `deterministic`       | Same input always produces the same output                        |
| `probabilistic`       | Output includes randomness or model-generated content             |
| `env-dependent`       | Output depends on environment state (current temperature, uptime) |
| `eventually-consistent` | Output may lag behind reality (cache-based queries, discovery)  |

#### Latency Profile (L3+)

| Class            | Threshold        |
|------------------|------------------|
| `instant`        | < 100ms          |
| `fast`           | < 1s             |
| `moderate`       | < 5s             |
| `slow`           | < 30s            |
| `long-running`   | > 30s            |

#### Retry Semantics (L3+)

| Class              | Meaning                                                    |
|--------------------|------------------------------------------------------------|
| `safe`             | Idempotent — can retry without side effects                |
| `idempotent-only`  | Retry only when the operation is guaranteed idempotent     |
| `unsafe`           | Duplicate execution causes problems (toggle, create, send) |
| `requires-cleanup` | Retry needs compensating action (delete + recreate)        |

#### Cost (L3+)

| Class       | Meaning                                                     |
|-------------|-------------------------------------------------------------|
| `cheap`     | Negligible resource consumption                             |
| `moderate`  | Some resource impact (network calls, small computations)    |
| `expensive` | Significant resource impact (scans, large transfers)        |

### Tool Manifest Schema

[L2+] Every tool SHOULD expose a machine-readable manifest as structured metadata. This enables AI agents to reason about tool capabilities without parsing natural language descriptions.

#### Schema

```json
{
  "name": "restart_service",
  "version": "1.0.0",
  "risk": "DESTRUCTIVE",
  "side_effects": "destructive",
  "idempotent": false,
  "retryable": false,
  "concurrent_safe": false,
  "timeout_ms": 30000,
  "requires_confirmation": true,
  "determinism": "env-dependent",
  "latency": "moderate",
  "cost": "expensive",
  "impact": "service_outage",
  "privacy": "none",
  "reversible": false
}
```

#### Field Definitions

| Field                    | Type    | Levels | Description                                              |
|--------------------------|---------|--------|----------------------------------------------------------|
| `name`                   | string  | L2+    | Tool identifier matching the registered tool name         |
| `version`                | string  | L2+    | Semantic version of the tool schema (see TOOL_VERSIONING) |
| `risk`                   | string  | L1+    | One of: READ, WRITE, DANGEROUS, DESTRUCTIVE, SENSITIVE   |
| `side_effects`           | string  | L3+    | none / read / write / destructive                        |
| `idempotent`             | bool    | L3+    | Whether repeated identical calls produce identical results |
| `retryable`              | bool    | L3+    | Whether a failed invocation can safely be retried         |
| `concurrent_safe`        | bool    | L3+    | Whether multiple concurrent invocations are safe          |
| `timeout_ms`             | int     | L3+    | Expected maximum execution time in milliseconds           |
| `requires_confirmation`  | bool    | L3+    | Whether the agent SHOULD request user confirmation. This is an **agent-level** hint, distinct from a server-level enable flag (see Write Guard). The agent MUST request user confirmation when this is `true`, even if the server has otherwise authorized the operation. |
| `impact`                 | string  | L3+    | none / transient / persistent / service_outage. Describes the operational impact of the tool on system availability. |
| `privacy`                | string  | L3+    | none / metadata / personal. Describes whether the tool accesses personally identifiable or sensitive data. |
| `reversible`             | bool    | L3+    | Whether the tool's effects can be reversed or undone at the application level. `true` for idempotent writes, `false` for destructive operations. |
| `determinism`            | string  | L3+    | deterministic / probabilistic / env-dependent / eventually-consistent |
| `latency`                | string  | L3+    | instant / fast / moderate / slow / long-running           |
| `cost`                   | string  | L3+    | cheap / moderate / expensive                              |

#### Risk Consistency Matrix

[L3+] The manifest fields are not independent. `risk`, `side_effects`, `idempotent`, `retryable`, `reversible`, `requires_confirmation`, and `impact` MUST form a consistent profile. A compliance test SHOULD assert each registered tool against this matrix.

| `risk`         | `side_effects`          | `idempotent` | `retryable` | `reversible` | `requires_confirmation` | `impact`                        |
|----------------|-------------------------|--------------|-------------|--------------|-------------------------|---------------------------------|
| `READ`         | `none` / `read`         | `true`       | `true`      | `true`       | `false`                 | `none`                          |
| `WRITE`        | `write`                 | `true`       | `true`      | `true`       | `true`                  | `transient` / `persistent`      |
| `DESTRUCTIVE`  | `destructive`           | `false`      | `false`     | `false`      | `true`                  | `persistent` / `service_outage` |
| `DANGEROUS`    | `write` / `destructive` | `false`      | `false`     | `false`      | `true`                  | depends on command              |
| `SENSITIVE`    | `none` / `read`         | `true`       | `true`      | `true`       | `false` / `true`       | `none` (set `privacy` accordingly) |

Rules:

1. [L1+] `[DANGEROUS]` is reserved EXCLUSIVELY for tools that execute arbitrary, unbounded shell commands. A device reboot, service restart, or factory reset is NOT `[DANGEROUS]` — it is `[DESTRUCTIVE]`, because the command set is fixed and known.
2. [L3+] A tool whose effect cannot be undone at the application level (reboot, reset, delete) MUST have `risk: DESTRUCTIVE`, `reversible: false`, `idempotent: false`, `retryable: false`. It MUST NOT be created with the WRITE manifest factory — use `_make_destructive_manifest()` (Canonical Template 5c).
3. [L3+] `requires_confirmation` MUST be `true` for every `WRITE`, `DESTRUCTIVE`, and `DANGEROUS` tool. `SENSITIVE` tools MAY set it to `true` when the disclosure requires explicit user consent; consumers MUST honor the flag when present.
4. [L3+] A tool returning credentials, tokens, or PII MUST have `risk: SENSITIVE` and `privacy` set to `metadata` or `personal`.

#### Exposure

[L2+] Manifests MAY be exposed through:
- A `tool.__manifest__` attribute on the registered function
- A `GET /api/tools/{name}/manifest` REST endpoint
- A `manifest` key in the tool listing response

[L3+] The manifest SHOULD be accessible programmatically without invoking the tool itself.

[L2+] AI agents SHOULD prefer manifest data over docstring parsing for capability decisions. The manifest is the machine-readable contract.

### Tool Versioning

MCP tools that AI agents depend on SHOULD version their schemas. Agents form prompts around specific tool signatures; silent breaking changes corrupt agent behavior.

#### Rules

1. [L2+] Every tool module or registration function SHOULD expose a version constant: `TOOLS_VERSION = "1.0.0"`. At L1, versioning is optional.
2. [L2+] New parameters SHOULD be added as optional (`param = None`) with backward-compatible defaults. Removing or changing required parameters breaks the agent contract.
3. [L3+] Deprecation lifecycle: `deprecated` (parameter works, docstring warns) → `warning` (parameter works, emits log warning) → `removed` (parameter removed). Minimum 2 minor versions between `deprecated` and `removed`.
4. [L3+] Tool description docstrings SHOULD include `@since vX.Y.Z` and `@deprecated vX.Y.Z` annotations.
5. [SHOULD] Server health endpoint MAY include `"tools_version"` so the AI client can detect version mismatches.
6. [L3+] Breaking changes MUST be documented in CHANGELOG with migration instructions for agent prompt authors.

#### Example

```python
TOOLS_VERSION = "2.1.0"

@mcp.tool()
async def get_logs(
    server: str | None = None,    # @since v2.0.0
    follow: bool = False,          # @since v2.1.0
    lines: int = 50,               # @deprecated v2.0.0 — renamed from 'count'
) -> str:
    """[READ] Fetches recent logs from the server.
    @since v1.0.0
    @updated v2.1.0 — added 'follow' parameter
    """
    ...
```

### Version Compatibility

For the MCP tooling ecosystem to evolve without breaking AI agents, a clear compatibility policy is required.

#### Forward Compatibility

1. [L1+] AI clients MUST ignore unknown fields in tool responses. New fields added to responses are backward-compatible by default.
2. [L1+] AI clients MUST NOT reject responses containing unrecognized keys in `data` or `_meta` objects.

#### Backward Compatibility

1. [L2+] New parameters MUST be optional with sensible defaults. Required parameters MUST NOT be added without a version bump.
2. [L2+] Response fields MUST NOT be removed. Deprecated fields SHOULD remain present for at least 2 minor versions.
3. [L2+] The semantics of an existing parameter or response field MUST NOT change within a major version.

#### Inter-Tier Compatibility

1. [L1+] An L1 tool (basic error format) MUST work with an L4-capable agent. The agent adapts to the simpler contract.
2. [L2+] An L4 tool (full manifest + structured errors) SHOULD degrade gracefully when queried by an L1 client. The tool always returns the core `success` field.

#### Schema Version Negotiation

1. [SHOULD] Tools MAY expose their schema version in the manifest (`"version"` field) and health endpoint (`"tools_version"`).
2. [SHOULD] Agents MAY inspect the version before calling a tool and adapt their logic accordingly. The version serves as a capability negotiation signal.

### Response Contract

Every tool MUST return a structured, machine-readable response. The contract has three layers: core (L1+), extended errors (L2+), and metadata envelope (SHOULD).

#### Core Contract (L1+)

```json
{
  "success": true,
  "data": <any>
}
```

```json
{
  "success": false,
  "error": "<message>"
}
```

The `"success"` boolean MUST be the first layer the agent checks. Its absence is an error.

#### Extended Error Contract (L2+)

[L2+] Error responses SHOULD include structured fields beyond the human-readable message:

```json
{
  "success": false,
  "error": {
    "code": "DEVICE_OFFLINE",
    "message": "Device 'LivingRoom' did not respond within 5s",
    "retryable": true,
    "suggestion": "Check device power and network, then retry",
    "available_names": ["Kitchen", "Garage"]
  }
}
```

[L2+] `error.code` MUST be a machine-readable identifier (UPPER_SNAKE_CASE) that agents can branch on:
- `TIMEOUT` — operation exceeded its deadline
- `DEVICE_OFFLINE` — target device unreachable
- `AUTH_FAILED` — authentication/authorization rejected
- `INVALID_PARAM` — parameter validation failed
- `UNSUPPORTED` — operation not available for this target
- `DEPENDENCY_MISSING` — required optional dependency not installed
- `INTERNAL_ERROR` — unexpected failure, retry may help
- `HTTP_ERROR` — external HTTP endpoint returned a non-2xx status
- `DEVICE_NOT_FOUND` — target device not found in discovery cache; suggest running a scan first
- `VALIDATION_FAILED` — server-side schema validation against existing config failed
- `RESOURCE_LOCKED` — optimistic locking failure (config_hash mismatch); re-read and retry
- `RESOURCE_ALREADY_EXISTS` — attempted to create a resource that already exists
- `RESOURCE_NOT_FOUND` — attempted to update or delete a resource that does not exist

[L2+] `error.retryable` MUST be a boolean. `true` means the agent SHOULD retry with backoff. `false` means retry is pointless or dangerous.

[L2+] `error.suggestion` SHOULD be a one-sentence actionable next step.

[L2+] `error.available_*` fields SHOULD list valid alternatives when an unknown identifier is the cause. Limit to 50 entries.

#### Extensible Envelope (SHOULD)

The response wrapper MAY include an optional `_meta` field:

```json
{
  "success": true,
  "data": {"key": "value"},
  "_meta": {
    "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "duration_ms": 42,
    "tool_version": "1.2.0",
    "cached": false,
    "retry_safe": true
  }
}
```

[SHOULD] Standard `_meta` fields: `request_id` (UUID), `duration_ms` (int), `tool_version` (str), `cached` (bool), `retry_safe` (bool).

[L1+] AI clients MUST handle responses with or without `_meta`. Unknown `_meta` fields MUST be ignored.

### Logging Standards

MCP servers communicate over stdio or SSE. Log output on stdout corrupts the MCP protocol.

#### Rules

1. [L1+] All log output MUST target stderr. Logging to stdout corrupts the MCP stdio transport.
2. [L2+] Log format SHOULD include timestamp, level, and component name. At L1, any structured format is acceptable.
3. [L2+] Log level SHOULD be configurable via `LOG_LEVEL` environment variable (default `INFO`).
4. [L1+] API keys, passwords, tokens, and credentials MUST NOT appear in log output.
5. [L2+] Connection lifecycle events SHOULD be logged at INFO level. Tool invocation success/failure at DEBUG level.
6. [L2+] Logging configuration SHOULD be initialized once at startup, before any tool or client is instantiated.

### Secret Management

Credentials MUST never appear in code, test fixtures, or commit history.

#### Rules

1. [L1+] `.env` MUST be listed in `.gitignore`. Zero exceptions.
2. [L1+] `.env.example` MUST exist and document every supported variable with placeholder values (`your_api_key_here`). It MUST NOT contain real credentials.
3. [L1+] `os.getenv()` calls MUST NOT have hardcoded secrets as default values.
4. [L1+] Credentials discovered in repository history or working directory MUST be rotated on the originating service immediately.
5. [L1+] Test fixtures MUST use synthetic test values. No test file MAY contain real server names, API keys, or IP addresses.

[L3+] Additional secret management rules — pipeline injection, key file permissions — are defined in the Security and Operational Safety section below.

### Tool Parameter Design

MCP tools that manage multiple backend connections need a parameter to select the target.

#### Rules

1. [L2+] Every tool operating on a backend connection SHOULD accept an optional `server: str | None = None` parameter. When `None`, the tool uses the default server.
2. [L2+] The `server` parameter SHOULD be the last positional/keyword parameter for backward compatibility.
3. [L2+] A resolver function `_get_client(server)` SHOULD select the correct client and raise `ValueError` for unknown server names.
4. [L2+] Tools specific to one backend type SHOULD validate the client type with `isinstance()`.
5. [L2+] Parameter descriptions in docstrings SHOULD state the default behavior when `server` is omitted.
6. [L2+] Multi-server tools MUST NOT hardcode server-specific logic. Differentiation lives in the client class.
7. [L2+] Timeout parameters MUST use `int = <DEFAULT_TIMEOUT>` (a concrete integer), never `int | None = None`. JSON Schema handles plain integer defaults correctly across all MCP framework versions, but `int | None` may be rejected depending on the framework's schema validation implementation, causing MCP SSE transport errors. Use the project's timeout constant (e.g., `SSH_TIMEOUT`) as the default value.

### Consumer Ergonomics

[L2+] MCP servers are consumed by AI agents operating under token budgets and latency constraints. Tools SHOULD be designed to minimize round-trips and payload sizes.

1. [L2+] Large collections SHOULD expose list, search, overview, summary, or diagnostic tools before detail tools. The consumer should be able to narrow scope before fetching full detail.
2. [L2+] Tools returning potentially large payloads SHOULD support a lightweight initial response mode such as `detail_level="minimal"`, `compact=true`, `summary=true`, `fields=[...]`, or equivalent narrowing parameters. Full-detail payloads SHOULD be opt-in for large resources.
3. [L2+] Tools returning potentially large collections SHOULD expose pagination metadata: `has_more`, `next_offset` or `next_cursor`, `limit`, `total`. The first page MUST NOT imply completeness when `has_more` is `true`.
4. [L2+] When a common workflow requires calling the same READ tool over many identifiers, the server SHOULD provide a batch or composite READ tool. Batch tools MUST preserve the same response contract and SHOULD report per-item success/error when partial failure is possible. Batch tools MUST NOT silently drop results on partial failure.
5. [L1+] `list_*` tools SHOULD return the stable identifier needed by the corresponding `get_*` tool. The identifier field name SHOULD match the parameter name of the get tool (already required by Tool Design Rule 10).
6. [L1+] Empty query results are not errors. A tool that completes successfully and finds no matching items MUST return `success: true` with an empty data shape (`data: []`, `data: {}`, `null`, or an explicit `count: 0`). It MUST NOT return `success: false` solely because no items were found.

### Code Quality Stack

[L2+] Every MCP server project SHOULD use a standardized code quality toolchain. Configuration lives in `pyproject.toml`.

| Tool   | Purpose              | Minimum Config                                              |
|--------|----------------------|-------------------------------------------------------------|
| `ruff` | Linting + formatting | `line-length = 100`, `select = ["E", "F", "I", "W", "UP"]`  |
| `mypy` | Static type checking | `strict = true`, `python_version = "3.11"`                  |
| `bandit` | Security linting   | Default rules                                                |
| `pytest` | Test runner        | `asyncio_mode = "auto"`                                      |

#### Rules

1. [L2+] Configuration for all tools SHOULD live in `pyproject.toml`. No separate config files.
2. [L2+] Test files MAY be exempted from line-length limits.
3. [L2+] CI SHOULD run `ruff check`, `ruff format --check`, `mypy`, and `bandit` before tests.
4. [L1+] The project SHOULD target Python 3.11 or newer.
5. [L2+] Dependencies SHOULD be split into runtime and dev.

### Package Layout

Standard layout for Python MCP server projects:

```text
src/<package>/
    __init__.py
    __main__.py
    server.py
    config.py
    client.py
    validators.py
    rest_bridge.py          # optional

tests/
    conftest.py
    fixtures.py
    unit/
    integration/            # L2+
    smoke/                  # L3+
    e2e/                    # L3+
```

#### Rules

1. [L2+] `pyproject.toml` SHOULD define a CLI entry point.
2. [L2+] `__main__.py` SHOULD delegate to the CLI entry point.
3. [L2+] `__init__.py` SHOULD be empty except for a version string.
4. [L2+] Optional utility modules MUST use `try/except ImportError`.

### Response Helpers

[L1+] All tools MUST use helper functions for consistent response formatting.

```python
def _success_response(data: Any) -> str:
    return json.dumps({"success": True, "data": data})

def _error_response(error: str) -> str:
    return json.dumps({"success": False, "error": error})
```

[L2+] Consider an extended variant for structured errors (see RESPONSE_CONTRACT):

```python
def _error_response_extended(code: str, message: str, retryable: bool,
                              suggestion: str | None = None,
                              available_names: list[str] | None = None) -> str:
    error = {"code": code, "message": message, "retryable": retryable}
    if suggestion:
        error["suggestion"] = suggestion
    if available_names:
        error["available_names"] = available_names
    return json.dumps({"success": False, "error": error})
```

[L2+] For internal function composition (before JSON serialization), provide a dict-returning variant:

```python
def _error_dict_extended(code: str, message: str, retryable: bool,
                          suggestion: str | None = None,
                          available_names: list[str] | None = None) -> dict:
    """Return an error dict for internal function composition (before JSON serialization)."""
    error = {"code": code, "message": message, "retryable": retryable}
    if suggestion:
        error["suggestion"] = suggestion
    if available_names:
        error["available_names"] = available_names[:50]
    return {"success": False, "error": error}
```

### Testing Standards

**[RULE: TEST-REG-1] [L1+]** Each tool module MUST export one `register_<category>_tools(mcp)` function that registers all tools in that category.
**[RULE: TEST-REG-2] [L1+]** Unit tests MUST test registration functions by: calling `register_<category>_tools(mock_mcp)`, retrieving registered tools via `mock_mcp.get_tool("tool_name")`, invoking them, and asserting the response.
**[RULE: TEST-REG-3] [L1+]** Unit tests MUST test exception handlers in tool wrappers by patching the internal function with `side_effect=Exception` and asserting `success: false` with the exception text.
**[RULE: TEST-REG-4] [L3+]** Integration test conftest MUST register ALL tool modules present in `server.py`. When a new tool module is added to the project, the conftest MUST be updated in the same commit. At L1/L2, a comment listing expected registration calls is acceptable.

#### Test Hierarchy

**[RULE: TEST-HIERARCHY-1] [L2+]** The project SHOULD implement a four-tier test hierarchy: unit, smoke, integration, e2e. At L1, only unit tests are required.
**[RULE: TEST-HIERARCHY-2] [L1+]** **Unit tests** MUST have zero I/O. All external calls MUST be mocked via `unittest.mock.patch`. Unit tests MUST pass without environment variables, credentials, or network access. Unit tests MUST run in CI on every commit.
**[RULE: TEST-HIERARCHY-3] [L3+]** **Smoke tests** MUST make direct REST API calls via the `requests` library to `localhost:{REST_API_PORT}`. Smoke tests MUST skip when the MCP server is not running, using a dynamic socket connection check. Smoke tests MUST NOT import MCP server modules.
**[RULE: TEST-HIERARCHY-4] [L2+]** **Integration tests** MUST create a real MCP instance with tools registered in-process. Integration tests MUST skip when required environment variables are not configured. Integration tests MUST NOT mock external dependencies.
**[RULE: TEST-HIERARCHY-5] [L3+]** **E2E tests** MUST exercise the full pipeline: REST API endpoint calls to tool execution and response validation. E2E tests MUST skip when the MCP server is not running, using the same dynamic skip pattern as smoke tests.
**[RULE: TEST-HIERARCHY-6] [L2+]** `pytest.ini` or `pyproject.toml` MUST register standard markers for the four suites:

```ini
markers =
    unit: Unit tests (fast, mocked, no I/O)
    integration: Integration tests (slow, requires real backend)
    smoke: Smoke tests (quick health check, requires local MCP server)
    e2e: End-to-end tests (full pipeline, requires real backend + local MCP server)
```

#### Skip Patterns

**[RULE: TEST-SKIP-1] [L1+]** Unit tests MUST NEVER skip. They MUST pass without any external dependencies.
**[RULE: TEST-SKIP-2] [L3+]** Smoke and E2E tests MUST use a dynamic socket check: define `_server_running()` that attempts a socket connection to `localhost:{port}` with a 1-second timeout.
**[RULE: TEST-SKIP-3] [L2+]** Integration tests MUST check for required environment variables.
**[RULE: TEST-SKIP-4] [L2+]** The `pytestmark` skip marker MUST be placed in each test file directly.
**[RULE: TEST-SKIP-5] [L2+]** Skip conditions MUST also check for placeholder credential values.

#### Coverage Requirements

**[RULE: TEST-COV-1] [L3+]** Each module in `tools/` MUST have at least 80% line coverage from unit tests.
**[RULE: TEST-COV-2] [L3+]** Overall `tools/` coverage across all modules MUST be at least 80%.
**[RULE: TEST-COV-3] [L3+]** Unit tests MUST achieve ≥80% line coverage and explicitly test both the success path and the primary error handler. 100% reachable path coverage is an anti-pattern and MUST NOT be enforced.
**[RULE: TEST-COV-4] [L3+]** Integration tests MUST cover at least 50% of each module.
**[RULE: TEST-COV-5] [L3+]** Smoke and E2E tests produce 0% coverage by `coverage.py` — normal.
**[RULE: TEST-COV-6] [L3+]** Overall project coverage MUST exceed 85%.

#### CI Pipeline

**[RULE: TEST-CI-1] [L2+]** CI MUST run linting and format checking before tests. Implementation is delegated to `ref.ci-cd-standard` — the CI/CD Architect standard defines the exact workflow structure, action versions, and quality gates.
**[RULE: TEST-CI-2] [L2+]** CI MUST run unit tests.
**[RULE: TEST-CI-3] [L2+]** CI MUST build a Docker image and verify tool count.
**[RULE: TEST-CI-4] [L3+]** CI MUST run a Docker-based smoke test.

### Security and Operational Safety

#### SSE Transport Security

1. [L1+] The default host MUST be `127.0.0.1` (localhost only). Binding to `0.0.0.0` MUST require an explicit confirmation variable.
2. [L3+] When the server starts on `0.0.0.0`, it MUST log a CRITICAL-level warning.
3. [SHOULD] For remote access, use a reverse proxy with TLS encryption.
4. [L2+] SSE transport SHOULD use a configurable port via `MCP_PORT`.
5. [L2+] The SSE port and the REST API port MUST be distinct.
6. [L2+] Health checks MUST be available without SSE transport initialization.

#### Write Guard

Write and destructive operations present a security risk: an agent could invoke them without user awareness. A two-layer defense is RECOMMENDED: a server-level enable flag and an agent-level confirmation hint.

1. [L2+] Write/destructive tools MUST be gated behind an explicit server-level enable flag
   (e.g., `ENABLE_WRITE_OPERATIONS` or equivalent), defaulting to `false`. When the flag is
   `false`, the tool MUST return a structured error before any I/O. This is a **server-level
   authorization check**, not a user-consent mechanism.
2. [L3+] The enable flag check MUST run before any I/O operation. ValidationError
   (or equivalent) MUST be raised if the flag is `false`.
3. [L2+] The `requires_confirmation` manifest field is distinct from the enable flag:
   - `ENABLE_WRITE_OPERATIONS=false`: tool returns error at the server level — agent never
     gets to ask the user.
   - `ENABLE_WRITE_OPERATIONS=true` + `requires_confirmation=false`: agent MAY call directly.
   - `ENABLE_WRITE_OPERATIONS=true` + `requires_confirmation=true`: agent MUST request user
     confirmation before calling.
   Both layers MUST be implemented for defense in depth.

#### Cancellation and Timeouts

1. [L3+] Every tool that performs I/O MUST accept an optional `timeout_seconds` parameter.
2. [L3+] The tool manifest MUST declare `timeout_ms`.
3. [L3+] HTTP clients, SSH connections, and subprocess calls MUST propagate timeouts.
4. [L3+] Tools SHOULD check a cancellation signal during long-running operations.
5. [L3+] Cancellation MUST propagate: if the agent disconnects, in-flight operations SHOULD be aborted.
6. [L3+] On cancellation, the tool SHOULD clean up resources and return a controlled error response.
7. [L3+] Tools that allocate resources MUST clean them up in a `finally` block.
8. [L3+] When a tool operation partially fails, the response MUST indicate this.

#### Concurrency Model

1. [L3+] Each tool MUST declare its concurrency safety in the manifest.
2. [L3+] `concurrent_safe: false` means the tool MUST NOT be invoked concurrently.
3. [L3+] Tools that mutate shared state MUST either be serialized or implement locking.
4. [L2+] The lifespan context MUST be treated as read-only after the first invocation.
5. [L3+] Discovery caches and other shared data structures MUST use locking.
6. [L2+] Sync code invoked from an async context MUST NOT block the event loop.

#### Blocked Data Sources

[L4] MCP servers with filesystem access to backend storage MUST prevent AI agents from accessing authentication, credential, and onboarding data.

1. [L4] Define a blocklist of registry/storage names using a `frozenset`.
2. [L4] The data-loading function MUST check the blocklist before reading any file.
3. [L4] The blocklist check MUST run at the data-loading boundary.
4. [L4] Unit tests MUST verify that each blocked registry name returns an empty result.

```python
BLOCKED_REGISTRIES = frozenset({"auth", "auth_provider.homeassistant", "onboarding"})

def load_registry(registry_name, config_path):
    if registry_name in BLOCKED_REGISTRIES or any(
        registry_name.startswith(prefix) for prefix in BLOCKED_REGISTRIES
    ):
        _stats["blocked"] += 1
        return {}
    ...
```

#### Filesystem Access Control

[L4] Filesystem tools exposed to AI agents MUST implement allowlist-based access control.

1. [L4] Define a set of allowed directories. Reject paths containing `..` and `~`.
2. [L4] Validate resolved real paths against the allowlist before any read or write.
3. [L4] Enforce maximum file size and maximum directory depth.
4. [L4] Detect binary files and return a controlled error.

#### Command Execution Allowlist

[L2+] MCP servers that execute shell commands on a backend (SSH, `subprocess`) MUST NOT build a command from agent input and pass it to a shell unchecked. Every command MUST be validated against an explicit allowlist before execution. This is the command-level analogue of Filesystem Access Control.

1. [L2+] Define a regex allowlist of permitted commands. A command runs ONLY when it `re.fullmatch`-es an allowlist entry. Default-deny: anything unmatched is rejected. Substring/prefix matching is forbidden — `fullmatch` only.
2. [L2+] Define a denylist of dangerous metacharacters (`;`, `|`, `&&`, `||`, `$(`, `` ` ``, `{`, `}`) and dangerous operations. The denylist MUST be checked BEFORE the allowlist — defense in depth, so an input crafted to slip a loose allowlist regex is still caught.
3. [L2+] Read commands and write commands MUST use SEPARATE allowlists (`ALLOWED_PATTERNS` vs `ALLOWED_WRITE_PATTERNS`) and SEPARATE execution methods (`execute()` vs `execute_write()`). This structurally prevents a write command from being smuggled through the read path. The write method MUST be unreachable unless the server-level write guard (`ENABLE_WRITE_OPERATIONS`) is enabled.
4. [L2+] Validation MUST return a controlled `(allowed: bool, message: str)` result, never raise into the transport. A rejected command MUST be logged at WARNING with the reason.
5. [L3+] Unit tests MUST cover: an allowed read command passes; an allowed write command passes only via the write path; an unknown command is rejected; a metacharacter-injected command is rejected by the denylist before the allowlist is consulted.

```python
class SecurityValidator:
    ALLOWED_PATTERNS = [r"^uci show$", r"^uci get [a-zA-Z0-9._@:\[\]-]+$", ...]
    ALLOWED_WRITE_PATTERNS = [r"^uci commit [a-zA-Z0-9._-]+$", r"^ubus call system reboot$", ...]
    DANGEROUS_METACHARACTERS = [";", "&&", "||", "|", "$(", "`", "{", "}"]

    @classmethod
    def validate_command(cls, command: str) -> tuple[bool, str]:
        cmd = (command or "").strip()
        if not cmd:
            return False, "Empty command"
        for ch in cls.DANGEROUS_METACHARACTERS:          # denylist FIRST
            if ch in cmd:
                return False, f"Blocked dangerous character: '{ch}'"
        for pattern in cls.ALLOWED_PATTERNS:             # then allowlist
            if re.fullmatch(pattern, cmd):
                return True, "Command approved"
        return False, f"Unsupported command: '{cmd[:50]}'"
```

Reference: `openwrt-mcp` `src/openwrt_mcp/validators.py` (`validate_command` / `validate_write_command`) and `tools/ssh_client.py` (`execute` / `execute_write`).

#### Secret Management

1. [L3+] CI/CD pipelines MUST inject credentials through sealed secrets or environment variables.
2. [L3+] SSH private key files MUST have permissions `600` or `400`.
3. [L1+] `.env` MUST be listed in `.gitignore`.
4. [L1+] `os.getenv()` calls MUST NOT have hardcoded secrets as default values.
5. [L1+] Credentials discovered in repository history MUST be rotated immediately.

#### Observability

1. [L3+] Each tool invocation SHOULD be assigned a unique `request_id` (UUID).
2. [L3+] The `request_id` SHOULD appear in every log line.
3. [L3+] Response `_meta` envelope SHOULD include the `request_id`.
4. [L4] Every tool invocation MUST produce an audit log entry.
5. [L4] Write operations SHOULD produce additional audit detail.
6. [L3+] The health endpoint SHOULD include per-tool invocation counts (see Canonical Template 4c).
7. [L4] Log output returned to AI agents MUST be sanitized. Log sanitization protects log files only — the payload returned to the agent is a separate boundary, see Canonical Template 4b.
8. [L1+] All log output MUST target stderr.
9. [L3+] The `request_id` context MUST be stored in a `contextvars.ContextVar` (async servers) or `threading.local()` (sync-only servers), NEVER a module-level global variable. A module global is shared across all in-flight invocations: a concurrent call overwrites it and every subsequent log line is misattributed. `contextvars` is REQUIRED when tool handlers are `async` — `threading.local()` does not isolate concurrent asyncio tasks running on the same thread.
10. [L3+] The `request_id` placed in the `_meta` envelope MUST be the SAME id written to that invocation's log lines. Generating a fresh UUID inside the `_meta` builder breaks log-to-response correlation — set the id once at tool entry, then read it in both the logger and `build_meta()`.
11. [L4] Audit logging MUST be gated by an `ENABLE_AUDIT_LOGGING` flag (default `false`). The audit write MUST be wrapped in `try/except` and fail open — an unwritable audit file MUST NOT crash the tool.

```python
import re

_SENSITIVE_PATTERNS = [
    (r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', 'Bearer <REDACTED>'),
    (r'Authorization:\s*[^\s]+', 'Authorization: <REDACTED>'),
    (r'password[=:]\s*[^\s&]+', 'password=<REDACTED>'),
    (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '<IP_REDACTED>'),
]

def sanitize_log_line(line: str) -> str:
    for pattern, replacement in _SENSITIVE_PATTERNS:
        line = re.sub(pattern, replacement, line, flags=re.IGNORECASE)
    return line
```

Request-id context — use `contextvars`, not a module global (Observability rule 9):

```python
import contextvars, uuid

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

def set_request_id(value: str) -> None:
    _request_id.set(value)

def get_request_id() -> str:
    return _request_id.get()

def start_tool_context() -> str:
    """Call at the start of every tool wrapper, before any I/O or logging."""
    rid = str(uuid.uuid4())
    _request_id.set(rid)
    return rid
```

Audit log — gated, fail-open (Observability rule 11):

```python
def log_audit(actor: str, command: str) -> None:
    if not ENABLE_AUDIT_LOGGING:
        return
    try:
        from datetime import datetime
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} | {get_request_id()} | {actor} | {command}\n")
    except Exception:
        pass  # fail open — audit failure MUST NOT break the tool
```

### Python/FastMCP Implementation Notes

FastMCP stores tool internals differently across framework versions. The patterns in this document (MCPWrapper in Pattern 1, Mock MCP Fixture in Pattern 2, REST Bridge in Pattern 9) abstract over these differences. This section documents the underlying behavior so maintainers understand WHY the patterns exist.

#### Tool Storage Internals

FastMCP stores registered tools in internal structures that change between versions:
- Earlier versions: `mcp._tools` (dict mapping tool names to callables)
- Later versions: `mcp._tool_manager._tools` (wrapped as Tool objects)
- `mcp.tools` property MAY also be available in newer versions

The MCPWrapper pattern (Pattern 1) abstracts over these by probing multiple locations. When upgrading FastMCP, always check which internal structure is active and update wrappers accordingly.

#### call_tool API

Two distinct `call_tool` APIs exist and are NOT interchangeable:

| API | Signature | Blocking | Used In |
|-----|-----------|----------|---------|
| `FastMCP.call_tool` | `async call_tool(name: str, arguments: dict)` | Async | Integration tests, REST bridges |
| `Server.call_tool` | `call_tool(*, validate_input: bool)` | Sync | Internal framework use |

Integration tests and REST bridges MUST use `FastMCP.call_tool()`, never `Server.call_tool()`. Mixing them produces `TypeError` or wrong argument count errors.

#### Common Upgrade Issues

| FastMCP Version Change | Symptom | Mitigation |
|------------------------|---------|------------|
| Tool storage moved from `_tools` to `_tool_manager._tools` | MCPWrapper finds zero tools | `_discover_tools()` must probe multiple locations |
| Tool objects wrap callables instead of storing directly | `tools["name"]` is a Tool object, not a function | `_unwrap_tool()` must check `.fn`, `.func`, `._func` attributes |
| `call_tool` signature changes | `TypeError` on existing integration tests | Use MCPWrapper to isolate from framework changes |
| Lifespan context initialization delayed | REST bridge returns 503 on first request | Health endpoint is always available; tool calls wait for SSE |

#### Framework-Agnostic Practices

For maximum compatibility across MCP frameworks (including version upgrades):

1. **Abstract framework internals behind wrappers.** MCPWrapper (Pattern 1) and `_get_client()` (lifespan) isolate application code from framework changes.
2. **Never import framework internals in tool code.** Tools access the context through `mcp.get_context()`, never through framework-internal fields.
3. **Test the contract, not the implementation.** Smoke tests call the REST API. Unit tests mock `mcp.get_context()`. Integration tests use MCPWrapper. No test imports framework internals directly.
4. **Document framework version in `pyproject.toml`.** Pin the FastMCP version. CI validates against that version.

## INTERFACES

- INPUT: Tool implementation following internal function + wrapper pattern. Parameters follow design rules. MCP SSE endpoint configuration, timeout parameters, access control config. Test files following the four-level hierarchy (unit, integration, smoke, e2e).
- OUTPUT: Structured JSON responses with "success" boolean. Tool manifests. Security validation results, SSE lifecycle events, cancellation signals, blocked data responses, audit logs. Test results, coverage reports, CI exit codes.
- SIDE_EFFECTS: Tools annotated as [WRITE] or higher modify state. Blocked data sources log warnings. Smoke tests create and register tools; cleanup required.

## STATE

- Assumptions: Server implements the two-layer pattern (internal function + transport wrapper). All tools use `_success_response` and `_error_response` helpers. Logging targets stderr (not stdout). Environment variables are loaded before module imports. Pytest is configured with asyncio_mode="auto". MCP server uses SSE transport (not plain HTTP). Cancellation respects Go-style context propagation patterns.
- Constraints: Tool count is bounded by module registration limits. Server lifespan may create clients for unreachable backends — the server continues with available clients. Python 3.11 or newer is required. Tests for missing optional dependencies MUST be skipped, not fail. Concurrent request handling MUST NOT exceed configurable limits. File access is restricted to explicit allowlist paths. Secret injection bypasses environment variables when configured.
- Known_Limitations: L1 maturity supports unit tests only; L2+ requires integration tests. L3 maturity features (capability descriptors, full tool manifests) are optional and may be absent in smaller projects. SSE-level authentication is transport-specific; token validation is the application's responsibility. Not all blocked data patterns apply to all deployments. E2E tests require the full deployment stack.

## EDGE_CASES

- CASE: Optional dependency is not installed → EXPECTED: Tool returns structured error response ("<service> not installed"). Factory function returns None. Server continues operating normally.
- CASE: All backend connections fail at startup → EXPECTED: RuntimeError("No servers available") is raised. Server does not start without at least one working connection.
- CASE: Invalid server name passed to multi-server tool → EXPECTED: ValueError is raised by `_get_client()` resolver function. Wrapper catches it and returns structured error.
- CASE: Standalone deployment (no MCP client) → EXPECTED: Offline context snapshot generator creates Markdown summaries using read-only analyzers and deterministic formatters.

### Pitfalls

#### Design Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| **Tool raises instead of returning error** | A single unhandled `RuntimeError` crashes the entire MCP server | Every tool MUST have `try/except Exception` at the top level. |
| **Module-level imports bind early** | Changing `constants.VAR` after import does not propagate | Set environment variables BEFORE importing the module. Use `os.environ` for runtime overrides. |
| **JSON string response not parsed** | Agent receives raw string instead of structured data | Always `json.loads()` the tool response before processing. The contract guarantees JSON. |
| **Response wrapper inconsistency** | Some tools use `json.dumps()` directly, others use helpers — format drifts | All tools MUST use `_success_response` / `_error_response`. |

#### Configuration Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| **`.env` with placeholder credentials** | Tests execute with `your_api_key_here` and fail | Skip conditions MUST check for placeholder values. |
| **Hardcoded defaults in multiple files** | Two modules use different defaults for the same env var | SSOT: all defaults in `tools/constants.py`. |

#### Code Quality Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| **Orphaned dict literal** | Dict `{...}` created but never assigned — values silently discarded | `ruff check` catches unused expressions. CI MUST fail on unused values. |
| **Duplicated logic paths** | Same operation appears twice in one function; only one path tested | Extract shared logic. Coverage reveals unreachable branches. |

#### Testing Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| **`pytestmark` in `conftest.py`** | Tests run when they should skip, or fail instead of skipping | Place `pytestmark` in each test file directly. `conftest.py` markers do NOT apply to test functions. |
| **Fixtures in `__init__.py`** | Fixtures never discovered by pytest — silent dead code | Pytest auto-discovers fixtures ONLY from `conftest.py`. Never define fixtures in `__init__.py`. |
| **Fixtures with same name in sibling test files** | Pytest raises "duplicate fixture" | Put shared fixtures in `conftest.py`. Keep file-specific fixtures with unique names. |
| **`@mcp.tool` without parentheses in mock fixture** | Decorated function never added to `mock_mcp._tools` | Mock fixture MUST accept both `@mcp.tool` and `@mcp.tool()` forms. See Pattern 2. |
| **Coverage cache contamination** | Coverage report shows inflated numbers from cached data | Delete `.coverage*` between suite runs. Use clean state. |
| **Parameterized test arg unpacking** | `tool_fn(**dict)` instead of `tool_fn(*tuple)` | Use `*args` unpacking for positional parameters. |
| **Lifespan not initialized before REST bridge** | REST bridge returns 503 | Lifespan runs as part of SSE transport. Ensure SSE connection or mock the context before REST bridge handles tool calls. |
| **REST bridge `call_tool` result extraction** | Response body is raw `ContentBlock` sequence instead of parsed JSON | Iterate through blocks, extract `.text` from each, parse as JSON. |
| **`mcp.get_context()` returns None outside request** | "Context is not available outside of a request" in unit tests | Mock `mcp.get_context()` with a `MagicMock` whose `request_context.lifespan_context` contains test fixture data. |
| **Framework `call_tool` API mismatch** | `TypeError` or wrong argument count | Use the correct API for your framework. Never mix sync and async call_tool variants. |
| **YAML-only data source** | Tool searches static files but misses runtime-created entities | Tools reading config files MUST fall back to the API/states engine. UI-created entities exist only in the state engine. |
| **Coverage gap from wrong suite** | Chasing coverage that the current suite cannot produce | Smoke/E2E produce 0% coverage by design. Unit provides bulk; integration adds incremental. See Pattern 10. |

#### Security Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| **Public SSE without warning** | Server binds `0.0.0.0` silently, exposing tools to the network | Require explicit confirmation. Log CRITICAL when public. |
| **Credentials in logs** | API keys visible in stdout/stderr output | Filter sensitive fields before logging. Use `sanitize_log_line()`. |
| **No timeout on external calls** | Tool hangs indefinitely when backend is unreachable | Every HTTP/SSH/subprocess call MUST have timeout. |
| **Cache mutation without locking** | Concurrent tool invocations corrupt shared state | Use `asyncio.Lock` or `threading.Lock` for shared caches. |
| **Blocking I/O in async context** | Event loop stalls, all tools slow down | Use `run_in_executor` or `to_thread` for blocking operations. |
| **Resource leak on cancellation** | Temp files, connections accumulate after cancelled operations | Cleanup in `finally` blocks. Exception-safe. |
| **Missing cancellation check** | Agent disconnects but tool keeps running for minutes | Check cancellation signal periodically in long operations. |
| **`request_id` in a module global** | Concurrent invocations overwrite each other's id; log lines misattributed | Store `request_id` in `contextvars.ContextVar` (async) or `threading.local()` (sync). Observability rule 9. |
| **Shell command built from agent input** | Crafted input reaches the shell — command injection | Validate against an explicit `fullmatch` allowlist; deny by default; separate read/write allowlists. See Command Execution Allowlist. |
| **Destructive tool typed as `[WRITE]`** | Manifest says `retryable: true`; agent re-issues a reboot or skips confirmation | Use `_make_destructive_manifest()`. Verify against the Risk Consistency Matrix. |
| **Secrets sanitized in logs but not in payload** | Credential read from a backend is returned to the agent in `data` | Sanitize the response payload at the `_success_response()` boundary. Canonical Template 4b. |

## EXAMPLES

The implementation patterns below demonstrate key MCP server design patterns. Each pattern is a complete, copy-paste-ready implementation.

### Canonical Templates

**NOTE for AI Agents:** These are not loose examples. These are strict templates. You MUST copy them exactly and only change the variables.

#### Canonical Template 1 — Graceful Degradation for Optional Dependencies

[L1+] External libraries (`paho-mqtt`, `nmap`) are optional. When absent, the server MUST continue operating.

Implementation:

1. Create a factory function `_get_<service>_client()` per dependency.
2. Wrap the import in `try/except ImportError`. On failure, return `None`.
3. In every tool that uses the dependency, check: `if client is None: return _error_response("<service> not installed")`.
4. At startup, check for optional system binaries and log warnings. Do not abort.

#### Canonical Template 2 — Error Message Standards

[L1+] Error responses SHOULD include actionable information. See RESPONSE_CONTRACT for the extended error format.

At minimum: `"error"` string with what failed and why.

At L2+: `"code"`, `"retryable"`, `"suggestion"`, and `"available_*"` fields.

#### Canonical Template 3 — Environment Loading

[L1+] `tests/conftest.py` loads environment variables from multiple paths using `os.environ.setdefault()` to avoid overwriting already-set variables.

```python
env_paths = [Path("/app/.env"), Path(".env")]
for env_path in env_paths:
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
```

#### Canonical Template 4 — Response Wrapper Helpers

[L1+] All tools MUST use helper functions. See RESPONSE_HELPERS above.

#### Canonical Template 4a — Auto-Sanitizing Log Formatter

[L3+] Log sanitization enforced at the logging infrastructure level is stronger than manual `sanitize_log_line()` calls — it cannot be bypassed by a developer forgetting to call it.

Implementation — from tasmota-openbk-mcp `tools/constants.py:92-149`:

```python
class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = getattr(_request_id_context, "value", "-")
        return True

class SanitizingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return sanitize_log_line(super().format(record))

def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(SanitizingFormatter(
        "%(asctime)s [%(levelname)s] [%(request_id)s] %(name)s: %(message)s"
    ))
    handler.addFilter(RequestIdFilter())
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
```

#### Canonical Template 4b — Response Payload Sanitization

[L3+] `sanitize_log_line()` (Template 4a) protects log output only. The payload RETURNED to the agent is a separate trust boundary — a credential or IP read from a backend reaches the agent even when logging is clean. Apply recursive sanitization to the response `data` inside `_success_response()`.

Implementation — from mikrus-mcp `src/mikrus_mcp/sanitizer.py` and `tools/response.py`:

```python
def sanitize_response_data(data: object) -> object:
    """Recursively sanitize a response structure before returning it to the agent."""
    if isinstance(data, str):
        return sanitize_log_line(data)
    if isinstance(data, dict):
        return {k: sanitize_response_data(v) for k, v in data.items()}
    if isinstance(data, list):
        return [sanitize_response_data(item) for item in data]
    return data

def _success_response(data: Any, _meta: dict | None = None) -> str:
    response: dict[str, Any] = {"success": True, "data": sanitize_response_data(data)}
    if _meta is not None:
        response["_meta"] = _meta
    return json.dumps(response)
```

The sanitization MUST run at the wrapper boundary, not in each tool — a tool that forgets to call it is the failure mode this template eliminates.

#### Canonical Template 4c — Per-Tool Invocation Counter and `build_meta`

[L3+] The health endpoint exposes per-tool invocation counts (see Observability). The counter is shared mutable state and MUST be lock-protected. `build_meta()` centralizes `_meta` construction and records the invocation as a side effect.

```python
import threading, time
from collections import defaultdict

_invocation_counts: dict[str, int] = defaultdict(int)
_counter_lock = threading.Lock()

def record_invocation(tool_name: str) -> None:
    with _counter_lock:
        _invocation_counts[tool_name] += 1

def get_invocation_counts() -> dict[str, int]:
    with _counter_lock:
        return dict(_invocation_counts)

def build_meta(tool_name: str, start_time: float) -> dict:
    record_invocation(tool_name)
    return {
        "request_id": get_request_id(),   # the SAME id set at tool entry — see Observability
        "duration_ms": int((time.monotonic() - start_time) * 1000),
        "tool_version": TOOLS_VERSION,
    }
```

`build_meta()` MUST read the current `request_id` from the context (Observability rule 10), NOT generate a fresh UUID — a new UUID here would not match the id in the log lines for the same invocation.

#### Canonical Template 5 — Multi-Client Lifespan Architecture

[L2+] For MCP servers managing multiple backends, provide graceful degradation when some backends are unreachable.

```python
@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[dict]:
    config = load_config()
    clients: dict[str, ClientType] = {}
    failed: dict[str, str] = {}

    for srv_name, srv_cfg in config["servers"].items():
        try:
            client = create_client(srv_cfg)
            await client.open()
            clients[srv_name] = client
        except Exception as exc:
            failed[srv_name] = str(exc)

    if not clients:
        raise RuntimeError("No servers available")

    effective_default = config["default"]
    if effective_default not in clients:
        effective_default = next(iter(clients.keys()))

    lifespan_data = {"clients": clients, "failed": failed, "default": effective_default}
    yield lifespan_data

    for c in clients.values():
        await c.close()
```

#### Canonical Template 5a — Dynamic Risk Prefix Injection from Manifest

[L2+] Risk annotations (`[READ]`, `[WRITE]`, and others) MUST NOT be manually authored in docstrings when manifests exist. They MUST be dynamically injected from `TOOL_MANIFESTS`.

Implementation — from openwrt-mcp `src/openwrt_mcp/tools/registration.py:73-104`:

```python
KNOWN_PREFIXES = frozenset({"[READ]", "[WRITE]", "[DANGEROUS]", "[DESTRUCTIVE]", "[SENSITIVE]"})

def _inject_risk_prefixes(registered_tools: dict, manifest_map: dict) -> None:
    for name, fn in registered_tools.items():
        manifest = manifest_map.get(name, {})
        risk = manifest.get("risk", "READ")
        raw_fn = fn
        for attr in ("fn", "func", "_func", "function"):
            if hasattr(fn, attr):
                inner = getattr(fn, attr)
                if callable(inner):
                    raw_fn = inner
                    break
        doc = (raw_fn.__doc__ or "").strip()
        for prefix in KNOWN_PREFIXES:
            if doc.startswith(prefix):
                doc = doc[len(prefix):].lstrip()
                break
        new_doc = f"[{risk}] {doc}"
        raw_fn.__doc__ = new_doc
        if hasattr(fn, "description"):
            fn.description = new_doc.split("\n")[0].rstrip(".")
```

#### Canonical Template 5b — Write Operations Enable Guard

[L2+] Every write/destructive tool MUST call `check_write_enabled()` before any I/O.

Implementation — from openwrt-mcp `src/openwrt_mcp/tools/writer.py:113-118`:

```python
def check_write_enabled() -> None:
    if not ENABLE_WRITE_OPERATIONS:
        raise ValidationError(
            "Write operations are disabled. "
            "Set ENABLE_WRITE_OPERATIONS=1 to enable."
        )
```

#### Canonical Template 5c — Manifest Factory Functions

[L2+] Factory functions create manifests with sensible defaults, reducing boilerplate and preventing field omissions.

Implementation — from openwrt-mcp `src/openwrt_mcp/tools/registration.py:23-70`:

```python
def _make_manifest(name: str, timeout_ms: int = 15000, latency: str = "moderate") -> dict:
    return {
        "name": name, "version": TOOLS_VERSION, "risk": "READ",
        "side_effects": "read", "idempotent": True, "retryable": True,
        "concurrent_safe": False, "timeout_ms": timeout_ms,
        "requires_confirmation": False, "determinism": "env-dependent",
        "latency": latency, "cost": "cheap",
        "impact": "none", "privacy": "none", "reversible": True,
    }

def _make_write_manifest(name: str, timeout_ms: int = 15000, latency: str = "moderate") -> dict:
    return {
        "name": name, "version": TOOLS_VERSION, "risk": "WRITE",
        "side_effects": "write", "idempotent": True, "retryable": True,
        "concurrent_safe": False, "timeout_ms": timeout_ms,
        "requires_confirmation": True, "determinism": "env-dependent",
        "latency": latency, "cost": "moderate",
        "impact": "persistent", "privacy": "none", "reversible": True,
    }

def _make_destructive_manifest(name: str, timeout_ms: int = 30000, latency: str = "slow") -> dict:
    """Manifest for irreversible operations: reboot, factory reset, delete."""
    return {
        "name": name, "version": TOOLS_VERSION, "risk": "DESTRUCTIVE",
        "side_effects": "destructive", "idempotent": False, "retryable": False,
        "concurrent_safe": False, "timeout_ms": timeout_ms,
        "requires_confirmation": True, "determinism": "env-dependent",
        "latency": latency, "cost": "expensive",
        "impact": "service_outage", "privacy": "none", "reversible": False,
    }
```

[L3+] Three factories are REQUIRED, one per non-`SENSITIVE` risk class. Picking the factory IS the criticality decision — there MUST NOT be a fourth ad-hoc path. A tool whose effect is irreversible (reboot, reset, delete) MUST use `_make_destructive_manifest()`. Using `_make_write_manifest()` for such a tool is a defect: it advertises `retryable: true` and `reversible: true`, so an agent may safely re-issue a reboot or skip confirmation. Each factory's output MUST satisfy the Risk Consistency Matrix; a compliance test SHOULD verify this.

#### Canonical Template 6 — Centralized Input Validation

[L2+] All input validation lives in one module. No inline validation in tool handlers.

```python
class ValidationError(Exception):
    """Raised when input fails validation."""

def validate_path(path: str) -> str:
    if not path or ".." in path:
        raise ValidationError("Path traversal detected")
    return path

def validate_port(port: int | str) -> int:
    p = int(port)
    if not 1 <= p <= 65535:
        raise ValidationError("Port must be 1–65535")
    return p
```

#### Canonical Template 7 — Offline Context Snapshot Generation

[L3+] For AI systems without persistent MCP connections, generate offline Markdown summaries.

Architecture: **Analyzers** (one per domain, `collect()`/`analyze()`) → **Formatters** (deterministic `_write__section__()` output) → **Modes** (`offline`/`online`/`hybrid`).

Design rules: read-only, deterministic section order, shared registry for cross-referencing, typed data attributes.


**EXAMPLE 1 — Registration Wrapper Test:**
- INPUT: `mock_mcp` fixture, registration function `register_device_tools(mock_mcp)`.
- OUTPUT: Assert `"iot_get_device_info" in mock_mcp._tools`. Retrieve via `mock_mcp.get_tool("iot_get_device_info")`. Call with mocks. Assert `"success": true`.

**EXAMPLE 2 — Exception Handler Test:**
- INPUT: Registered tool `iot_set_power`, internal function patched with `side_effect=RuntimeError("boom")`.
- OUTPUT: Call `iot_set_power("192.168.1.100", "ON")`. Assert `"success": false` and `"boom"` in `"error"`.

**EXAMPLE 3 — Integration Test With MCP Instance:**
- INPUT: Session-scoped fixture creating the MCP instance, registering all tools, wrapping in `MCPWrapper`.
- OUTPUT: Test calls `mcp_client.call_tool("iot_list_devices")`, parses JSON, asserts `data["success"] is True`. No HTTP server.

**EXAMPLE 4 — Dynamic Skip for Smoke Tests:**
- INPUT: `_server_running()` using `socket.create_connection(("localhost", REST_API_PORT), timeout=1)`.
- OUTPUT: `pytestmark = pytest.mark.skipif(not _server_running(), reason="...")`. Server running → tests execute. Server stopped → tests skipped.

**EXAMPLE 5 — CI Docker Smoke Test:**
- INPUT: Docker image `myserver:test`, ports 9100 (health) and 9102 (REST).
- OUTPUT:
  ```yaml
  - name: Docker smoke test
    run: |
      docker run -d --rm --network host --name test-srv myserver:test
      sleep 5
      curl -fsS --retry 5 --retry-delay 2 http://localhost:9100/health || exit 1
      TOOLS=$(curl -s http://localhost:9102/api/tools | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])")
      [ "$TOOLS" = "13" ] || (echo "FAIL" && exit 1)
      docker stop test-srv
  ```

**EXAMPLE 6 — Parameterized Error Path Test:**
- INPUT: List of `(tool_fn, method_name, args)` tuples covering all tools.
- OUTPUT: Each tool's mock raises `RuntimeError("boom")`. Test patches context, calls `await tool_fn(*args)`, asserts `success: false` with `"boom"`.

#### Canonical Template 8 — MCPWrapper for Integration Tests

[L2+] FastMCP changes internal tool storage between versions. A reusable wrapper abstracts over these changes.

1. Define `MCPWrapper` with a `call_tool(tool_name, **kwargs)` method.
2. In `_discover_tools()`, probe multiple locations: `mcp._tools`, `mcp._tool_manager._tools`, `mcp.tools`.
3. In `_unwrap_tool()`, extract the callable by checking `fn`, `func`, `_func`, `function` attributes.
4. In `call_tool()`, detect `iscoroutinefunction` and run async tools with a shared event loop.
5. Create one session-scoped `mcp_client` fixture that builds the instance, registers all tools, and returns `MCPWrapper(mcp)`.
6. Tests call `mcp_client.call_tool("tool_name", param=value)` without any HTTP server.

#### Canonical Template 9 — Mock MCP Fixture for Unit Tests

[L1+] Unit tests that verify tool registration need a mock MCP instance with a working `tool()` decorator. The mock must accept both `@mcp.tool` (no parentheses) and `@mcp.tool()` (with parentheses) forms.

```python
@pytest.fixture
def mock_mcp():
    mcp = MagicMock()
    mcp._tools = {}

    def tool_decorator(*args, **kwargs):
        def wrapper(func):
            tool_name = kwargs.get("name", func.__name__)
            mcp._tools[tool_name] = func
            return func
        if len(args) == 1 and callable(args[0]) and not kwargs:
            mcp._tools[args[0].__name__] = args[0]
            return args[0]
        return wrapper

    mcp.tool = tool_decorator
    mcp.get_tool = lambda name: mcp._tools.get(name)
    return mcp
```

Without the `callable(args[0])` check, `@mcp.tool` fails silently.

#### Canonical Template 10 — The "Passed Unit, Fails in Prod" Risk

[L2+] 100% unit test coverage does not guarantee correct operation against real services. Unit tests mock external calls; integration tests validate the mocks match reality.

Minimum integration test per tool:
1. One test with valid arguments asserting `success` is present.
2. One test with invalid arguments asserting a controlled error response.

If a tool has zero integration tests, at least one smoke test MUST exist before merging.

**Dynamic Entity Lookup:** [L3+] Integration tests MUST NOT hardcode entity IDs. Look them up at runtime:

```python
list_result = mcp_client.call_tool("list_<resources>")
items = json.loads(list_result).get("items", [])
if items:
    identifier = items[0].get("id") or items[0].get("name")
    result = mcp_client.call_tool("get_<resource>", identifier=identifier)
    assert data["success"] is True
```

#### Canonical Template 11 — Session-Scoped Instance With Async Execution

[L2+] Integration tests reuse one MCP instance across all tests. Async tools require a shared event loop.

1. Create the MCP instance in a `scope="session"` fixture.
2. Register all tools once. Cache the wrapper.
3. For async tool execution, create one `asyncio.new_event_loop()` and reuse it.
4. Use `loop.run_until_complete(coro)` from sync test context.

#### Canonical Template 12 — Response Format Compliance Test

[L3+] A single compliance test verifies all registered tools return a `success` field. Run against the REST API at smoke-test time.

Implementation — adapted from tasmota-openbk-mcp `tests/smoke/test_critical_tools.py:95-140`:

```python
class TestResponseFormat:
    ALL_TOOLS = [
        "tool_one",
        "tool_two",
    ]
    _REQUIRES_PARAMS = frozenset({"tool_two"})

    def _call_safe(self, tool_name, **kwargs):
        try:
            resp = requests.post(
                f"{REST_API_URL}/api/tools/{tool_name}",
                json={"params": kwargs}, timeout=10
            )
            return resp.json() if resp.ok else None
        except Exception:
            return None

    def test_all_tools_return_success_field(self):
        call_map = {
            "tool_two": {"param1": "value1"},
        }
        for tool_name in self.ALL_TOOLS:
            data = self._call_safe(tool_name, **call_map.get(tool_name, {}))
            assert data is not None, f"{tool_name}: no response"
            assert data.get("success") is not None, f"{tool_name}: missing success field"
```

#### Canonical Template 13 — MCP Context Mocking for Tool Handler Tests

[L2+] When tool handlers use the lifespan context, unit tests must mock it.

```python
@pytest.fixture
def mcp_context(mock_client):
    ctx = MagicMock()
    ctx.request_context.lifespan_context = {
        "clients": {"default": mock_client},
        "default": "default",
        "failed": {},
    }
    return ctx

@pytest.mark.asyncio
async def test_tool(mcp_context, mock_client):
    mock_client.get_info.return_value = {"server_id": "test"}
    with patch.object(server_module.mcp, "get_context", return_value=mcp_context):
        result = await tool_fn()
    data = json.loads(result)
    assert data["success"] is True
```

#### Canonical Template 14 — Parameterized Error Path Testing

[L1+] Covers every tool's `except` branch with a single parameterized test.

```python
ERROR_TOOLS = [
    (get_server_info_tool, "get_server_info", ()),
    (list_servers_tool, "list_servers", ()),
    (restart_server_tool, "restart_server", ()),
    (read_file_tool, "read_file", ("/etc/hosts",)),
    (manage_service_tool, "manage_service", ("nginx", "status")),
]

@pytest.mark.asyncio
@pytest.mark.parametrize("tool_fn, method_name, args", ERROR_TOOLS)
async def test_tool_error(tool_fn, method_name, args, mcp_context, mock_client):
    getattr(mock_client, method_name).side_effect = RuntimeError("boom")
    with patch.object(mcp, "get_context", return_value=mcp_context):
        result = await tool_fn(*args)
    data = json.loads(result)
    assert data["success"] is False
    assert "boom" in data["error"]
```

Key: tuples use `*args` unpacking (positional). Tools with no args use `()`.

#### Canonical Template 15 — SSH / Async Library Mocking

[L2+] Async libraries (`asyncssh`, `aiohttp`, `aiofiles`) must be mocked at the module level via `sys.modules` replacement.

```python
@pytest.fixture
def mock_asyncssh() -> MagicMock:
    mock = MagicMock()
    mock.PIPE = -1
    mock.Error = Exception
    mock.read_known_hosts = MagicMock(return_value=())
    return mock

@pytest.mark.asyncio
async def test_execute_command_via_ssh(client, mock_asyncssh):
    result_mock = MagicMock()
    result_mock.stdout = "hello"
    result_mock.exit_status = 0
    conn_mock = MagicMock()
    conn_mock.run = AsyncMock(return_value=result_mock)
    mock_asyncssh.connect = AsyncMock(return_value=conn_mock)

    with patch.dict("sys.modules", {"asyncssh": mock_asyncssh}):
        await client.open()
        result = await client.execute_command("echo hello")
        await client.close()

    assert result["output"] == "hello"
```

Key: `sys.modules` is patched, not individual functions. `AsyncMock()` for async methods.

#### Canonical Template 16 — REST Bridge for Smoke/E2E Testing

[L3+] An optional internal REST bridge exposes MCP tools as HTTP endpoints.

```python
def create_rest_app(mcp):
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def call_tool(request):
        tool_name = request.path_params["name"]
        body = await request.json()
        params = body.get("params", {})

        lifespan = getattr(mcp, "_lifespan_data", None)
        if lifespan is None:
            return JSONResponse(
                {"success": False, "error": "Server lifespan not initialized"},
                status_code=503,
            )

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context = lifespan
        with patch.object(mcp, "get_context", return_value=mock_ctx):
            result = await mcp.call_tool(tool_name, params)

        for block in result:
            if hasattr(block, "text"):
                return JSONResponse(json.loads(block.text))
        return JSONResponse({"success": True, "data": str(result)})

    return Starlette(routes=[
        Route("/health", lambda r: JSONResponse({"status": "ok"}), methods=["GET"]),
        Route("/tools", list_tools, methods=["GET"]),
        Route("/tools/{name}", call_tool, methods=["POST"]),
    ])
```

Key: lifespan context stored at `mcp._lifespan_data` for REST bridge access. `call_tool()` returns `ContentBlock` sequence.

#### Canonical Template 17 — Test Suite Coverage Budget

[L3+] Each test suite has a defined coverage responsibility.

| Suite       | Expected Coverage Contribution | Purpose                                                |
|-------------|-------------------------------|--------------------------------------------------------|
| Unit        | 80–90%                        | Main coverage engine. Mocks enable exercising every branch. |
| Integration | +5–15% incremental            | Validates mocks match reality.                         |
| Smoke       | Format validation only        | Verifies `success` field on every tool. Not measured by coverage.py. |
| E2E         | Format validation only        | Verifies full pipeline integrity. Not measured by coverage.py. |

Coverage targets:
- [L3+] Unit tests MUST achieve ≥80% per module and ≥80% overall.
- [L3+] Combined coverage (unit + integration) SHOULD exceed 85%.
- [SHOULD] Coverage gaps in entrypoint modules and optional utilities are acceptable.

## NON_GOALS

- Does not cover MCP client implementation or client-side tool calling.
- Does not specify the MCP wire protocol or message format.
- Does not define deployment strategies, container orchestration, or production monitoring.
- Does not replace project-specific `AGENTS.md` files.
- Does not cover network-level firewall rules or physical security.
- Does not replace application-level authorization checks.
- Testing architecture is included in this document (see Testing Standards section).
- Security and operational safety is included in this document (see Security and Operational Safety section).
- Framework internals are documented in this file (see Python/FastMCP Implementation Notes). Other MCP frameworks (TypeScript, Go, Rust) are not covered.
