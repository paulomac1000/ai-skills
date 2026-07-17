---
description: Python and FastMCP implementation profile with tested patterns and known SDK failure modes.
doc_id: reference.python-fastmcp-profile
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Run unit, registration, transport, cancellation, and content-shape regressions against the supported FastMCP version range.
---

# Python and FastMCP profile

## Composition

Keep domain services and typed models independent from FastMCP. A composition root creates dependencies, constructs the server, registers tools through public decorators or registration APIs, and starts the selected transport. Decorated functions remain thin adapters.

## Registration stability

FastMCP versions have exposed tools through different private locations such as `_tools` and `_tool_manager._tools`. Private traversal is not a compatibility strategy. Verify registration through the supported server or client API and pin the supported SDK range with contract tests.

## Tool invocation tests

`call_tool` signatures and returned content representations can vary by SDK generation. Tests normalize only protocol-defined content and assert structured content separately from text blocks. Do not assume a returned value is raw JSON when the SDK exposes `ContentBlock` objects.

## Context and lifespan

Request context exists only inside a live invocation. Code that calls a global `get_context()` outside a request becomes difficult to test and may fail at startup. Pass an application-owned request abstraction or keep context use in the transport adapter. Lifespan resources are created once, exposed through typed state, and closed on shutdown.

## Decorator mocking

A fake decorator used in unit imports must preserve the decorated callable:

```python
def tool(*_args, **_kwargs):
    def decorate(function):
        return function
    return decorate
```

Returning a mock object or `None` changes module semantics and can hide registration defects.

## Fixtures and collection

Pytest fixtures placed in package `__init__.py` are not a reliable discovery mechanism. Use `conftest.py` or explicit plugins. Apply `pytestmark` in collected test modules, not helper packages whose marker is never inherited.

## Async correctness

Use asynchronous client and filesystem APIs in async tools. Do not call blocking I/O directly on the event loop. Every upstream operation receives a timeout. Cancellation is re-raised after bounded cleanup; broad `except Exception` blocks must not convert cancellation into a generic internal error.

Use `contextvars` only for request-scoped correlation that must flow through async calls. Reset tokens in `finally`; never store a global request ID shared by concurrent invocations.

## Security

Construct subprocess calls as executable plus argument list. Validate each argument against an allowlist and enforce timeout, output size, working directory, and environment. Never concatenate agent-controlled text into a shell command.

## Mocking upstreams

Patch application-owned interfaces, HTTP transports, or async clients. Avoid patching `sys.modules`. For REST bridges, run the actual app in a test client or ephemeral server so routing, serialization, and exception mapping are exercised.

## Regression checklist

- public tool registration works across the supported SDK range;
- decorator imports preserve callables;
- context is not accessed outside request scope;
- lifespan cleanup runs on normal shutdown and cancellation;
- content blocks and structured content are both tested;
- async paths contain no sync-over-async or blocking calls;
- stdout remains protocol-only on stdio;
- test suite reports unit, integration, smoke, and e2e layers separately.

## Verification

Run the profile regressions against the minimum and preferred FastMCP versions, then invoke representative tools through a real client over the chosen transport.
