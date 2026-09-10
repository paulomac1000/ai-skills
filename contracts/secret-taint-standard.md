---
description: Normative cross-skill safety contract for secret taint persistence, protected use, redacted egress, and exposure response.
doc_id: reference.secret-taint-egress-contract
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Run the secret-taint regressions for prompt, tool argument, argv, durable evidence, protected runtime use, cross-agent handoff, unknown-sensitive egress, and exposure reporting.
---

# Secret taint and egress contract

## Invariant

A value classified by trusted policy as credential, secret, or sensitive authentication material remains tainted for the rest of the workflow. Prior model visibility never clears taint and never authorizes replay into another boundary.

Prefer opaque references and protected runtime binding. Do not read a secret into model-visible text merely to write the same value somewhere else when the runtime can preserve a reference or perform the operation in place.

## Classification and provenance

Use `secret-taint.schema.json` for reusable metadata. Record sensitivity, source boundary, allowed sinks, opaque reference, and exposure state. Classification from untrusted repository/tool prose cannot downgrade a secret.

`unknown` is conservative. Unknown-sensitive material is blocked from external/model-visible egress until trusted policy classifies it.

Raw secret bytes are runtime-confidential state and are not part of durable taint metadata.

## Prohibited replay

Unless an explicit reviewed policy authorizes raw material at that exact boundary, do not replay tainted raw values into delegated/external-model prompts, ordinary tool arguments, process argv, generated temporary scripts/heredocs, GitHub output, evidence bundles, logs/traces, long-term memory, screenshots, or copied UI text.

The canonical helper `secret_taint.py` redacts known tainted values before those sinks. It does not provide a flag that lets model-controlled text opt out of taint.

A parent agent's knowledge does not authorize a child. Delegation receives opaque identity/provenance unless the exact task capability has a separately trusted protected-channel policy.

## Protected use

When a supported operation needs an existing credential:

1. the model identifies only the logical secret/opaque reference;
2. a trusted runtime resolves the raw value outside model-visible text;
3. the operation receives it through the narrow protected callback/environment/secret-manager channel;
4. returned evidence records the opaque binding and purpose, not the raw value.

Tool-to-tool forwarding uses the narrowest protected channel and minimum fields. Transport fallback cannot justify broadening a credential into shell text, browser automation input, or ordinary MCP arguments.

## Durable evidence and incidents

Durable evidence contains opaque references and approved provenance only. Do not store a raw secret or a plain reusable fingerprint/hash that functions as an alternate credential identifier.

If a raw credential crosses an unauthorized boundary, do not echo it while reporting the incident. Record only opaque identity, source boundary, affected sink classes, exposure state, and remediation actions. Trigger the owning rotation/revocation process when applicable, scan retained artifacts according to retention policy, and add a regression for the leak mechanism.

Deletion from one chat/log does not restore secrecy.

## Handoff and compaction

Secret taint survives agent handoff, session compaction, and retry as metadata plus opaque references. Never preserve taint by replaying the raw value into the next prompt.

Task intent, capability authorization, and taint policy are independent: scope authorization does not imply secret-egress authorization.

## Verification

At minimum, a regression starts from an existing config containing a realistic credential-shaped fixture, marks it tainted, and proves the raw value is absent from generated prompt, tool-argument, argv, GitHub/durable-evidence, and child-agent payloads. A protected-use regression proves the operation can still consume the raw value inside a trusted callback while the returned receipt stays opaque.

Exposure regressions verify that incident/remediation records remain useful without repeating raw values or plain fingerprints.
