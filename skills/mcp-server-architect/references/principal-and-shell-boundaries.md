---
afds_schema_version: 2
description: Defines process-derived local principals, mandatory remote authentication, confirmation enforcement, and adversarial shell-boundary testing.
doc_id: reference.mcp.principal-and-shell-boundaries
type: reference
status: active
rigor: normative
owners: [MCP maintainers, Security maintainers]
verification:
  kind: command
  value: Run `python -m pytest tests/test_mcp_generator.py tests/test_generator_platform_contracts.py` and retain boundary-specific adversarial evidence for every generated or assessed shell/subprocess capability.
---
# Principal and shell boundaries

## Local stdio principal

An L1 server exposed only through local stdio MAY derive its principal from the operating-system process boundary. The derived principal MUST be explicit in request context and audit records and MUST identify the effective user, service account, sandbox, or host policy that launched the process.

A process-derived principal is allowed only when all of the following hold:

- the transport is local stdio;
- no untrusted remote client can attach to the process boundary;
- authorization does not depend on model-supplied identity fields;
- the server does not reuse a process-global mutable principal across unrelated callers;
- the deployment records that OS isolation is the authentication boundary.

This profile does not authorize public or remote use.

## Remote principal

Every remote HTTP request MUST authenticate before target resolution, backend selection, artifact lookup, task lookup, browser-profile access, or network I/O. The authenticated principal MUST be request-scoped. Authorization MUST bind the principal to the exact capability, target, tenant, resource, and operational policy used by the invocation.

Missing, malformed, oversized, ambiguous, or non-ASCII credentials MUST fail within bounded work. A model argument, client-provided display name, target name, or confirmation boolean cannot establish identity.

## Confirmation enforcement

`requires_confirmation: true` is a server-enforced contract, not display metadata. Registration MUST fail unless the capability declares an approval-record policy. Invocation MUST fail unless a valid approval record:

- was issued by a trusted approval authority;
- binds the authenticated principal, capability ID, target identity, and digest of normalized arguments;
- is unexpired and single-use or replay-bounded;
- was not supplied or synthesized by model-controlled input;
- is consumed or invalidated according to the declared policy.

Changing any bound field invalidates the approval. A UI prompt without a server-verifiable approval record does not satisfy this rule.

## Shell and subprocess boundary

Prefer structured library calls and argument arrays with `shell=False`. When an operation reaches SSH, a subprocess, or a shell boundary, each agent-controlled value MUST pass an operation-specific parser and allowlist before process creation. Validation MUST happen before option parsing can reinterpret a value as a flag.

The implementation MUST NOT create a command by concatenating or interpolating untrusted text. A remote command string requires a dedicated quoting or protocol encoder and a documented remote-shell assumption; local argument-array safety alone does not prove remote-shell safety.

## Required adversarial cases

Every shell-bound capability MUST have executable tests covering at least:

```text
;
&&
$()
`backticks`
newline and carriage return
leading - and -- option injection
Unicode whitespace and confusable separators
NUL or control characters where the host language can represent them
empty values
oversized input
multiple encoding forms of the same forbidden token
```

Tests MUST assert both rejection and absence of process creation or network dispatch. A test that only inspects the produced command string is insufficient. For accepted values, tests MUST assert the exact argv or encoded remote request observed by the boundary adapter.