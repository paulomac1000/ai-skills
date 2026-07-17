---
description: Layered MCP server testing strategy covering domain, registration, transport, real clients, upstreams, and deployment artifacts.
doc_id: reference.mcp-server-testing-strategy
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Demonstrate one independently failing test at each applicable layer and run a real-client smoke test against the built artifact.
---

# MCP server testing strategy

## Layer responsibilities

### Domain unit

Call typed internal operations directly. Cover validation, success, failure, cancellation, concurrency, and no-I/O branches. Do not import an MCP server merely to test business logic.

### Schema and serialization

Validate input schemas, optional fields, enum behavior, structured outputs, content blocks, empty success, and stable error codes. Test both producer serialization and consumer-visible representation.

### Policy

Exercise authentication, per-tool authorization, resource scope, dangerous-operation confirmation, idempotency, conflict preconditions, blocked data, and secret redaction.

### Registration

Start the public server composition and inspect capabilities through a supported public client API. Assert names, schemas, descriptions, and count only when count is a deliberate contract. Never depend on private fields such as `_tools` or `_tool_manager._tools`.

### Transport integration

Use the real stdio or HTTP transport in a test host. Verify handshake, initialization, tool listing, invocation, deadlines, cancellation, malformed messages, and shutdown. Stdio tests additionally assert stdout contains protocol only.

### Real-client workflow

Use an official client, inspector, or protocol-conformant client to execute representative discover-select-invoke-verify flows. Include one read, one authorized mutation when applicable, and one controlled error.

### Upstream contract

Use fakes, mock HTTP handlers, recorded fixtures, or test containers according to the integration. Verify timeout and mapping behavior rather than merely mocking the final return value.

### Deployment artifact

Build the container or package, start the exact artifact, verify readiness and representative capability behavior, then terminate it and confirm cleanup.

## Coverage

Coverage is interpreted by layer. High unit coverage does not prove registration or transport correctness. A skipped integration suite is visible in CI and has an explicit prerequisite; it is not silently collected from `__init__.py` fixtures or global marks.

## Test doubles

Mock stable interfaces owned by the application. Avoid patching SDK internals or `sys.modules`. Decorator mocks must return the original function when used as `@tool()`; a mock that returns `None` corrupts import-time registration.

## Verification

Break one public registration, one schema, one cancellation path, and one deployment startup path in a disposable branch and confirm the intended layer fails with actionable evidence.
