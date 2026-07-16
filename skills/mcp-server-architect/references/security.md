# MCP security profile

Classify capabilities across independent dimensions instead of one overloaded risk enum:

- access: public, authenticated, scoped, privileged,
- effect: read, write, destructive,
- data: ordinary, sensitive, prohibited-to-model,
- reach: closed-world target, open-world external action, raw command,
- retry: idempotent, conditionally idempotent, non-idempotent.

Policy evaluation returns allow, deny, or require interaction and records a reason code. Tool annotations mirror selected dimensions for discovery but never grant access.

For remote HTTP, verify token issuer, audience, expiry, scopes, and target authorization. Avoid token passthrough. Limit hosts, origins, request size, concurrency, and operation duration.

For local device and shell integrations, use typed operations or strict allowlists, canonicalize paths and hosts, reject metacharacters before execution, and keep destructive functions in a separate policy path.
