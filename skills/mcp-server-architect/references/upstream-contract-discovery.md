---
description: Discovery-first workflow for legacy, external, or poorly documented upstream integrations.
doc_id: reference.mcp-upstream-contract-discovery
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Run the read-only repository inspector, record controlled upstream observations, validate upstream-contract.yaml, and prove public canonical inputs do not leak the upstream dialect.
---

# Upstream contract discovery

## Entry gate

For an existing adapter, discover the real upstream contract before restructuring MCP architecture whenever the backend is external, legacy, poorly documented, or contradicted by existing tests. Do not infer body encoding, date dialect, pagination, success payload shape, returned identity, retry safety, or credential placement from client code alone.

Start with `python skills/mcp-server-architect/tools/inspect_existing_project.py <repository>`. If the plan reports `upstream_contract: required`, create `upstream-contract.yaml` from the template and validate it with `python contracts/validate_upstream_contract.py upstream-contract.yaml --require-observed` before changing the adapter contract.

## Observed facts

Record observations, not desired architecture. Each operation binds method, endpoint, request encoding, required fields, success statuses, response-body shape, credential placement, and evidence. Add date dialect, pagination termination, create identity, delete semantics, and retry hints when they apply. Secrets and protected payloads never belong in this document.

`confidence: inferred` is useful during discovery but cannot satisfy observed-contract acceptance. Promote a claim only after a controlled probe, recording, test container, emulator, or authoritative provider document demonstrates it.

For every observed mutation, model completion, identity, and representation separately. `completion: unknown` means the operation's effect is not established and requires reconciliation. `completion: confirmed-success` remains confirmed success when the upstream omits an identifier or response representation; record `identity: unavailable` or `representation: unavailable` rather than degrading the result to a generic ambiguous outcome. Identity uncertainty and completion uncertainty are independent dimensions. Never invent a resource identifier merely to make a confirmed success look complete.

A confirmed successful create whose identity is unavailable SHOULD expose a bounded public result such as `created: true` with `reconciliation_required: true` when later reconciliation is required. A timeout or disconnect after transmitting a state-changing request remains completion-unknown until an independent postcondition establishes the result. Retrying such a request is forbidden unless the upstream contract proves the retry is safe or reconciliation has established that the first attempt did not apply.

## Public boundary

The MCP public contract remains canonical even when the upstream dialect is not. Test the full boundary `public input -> canonical domain value -> upstream adapter -> upstream dialect`, and add a negative test proving backend-only date, money, identifier, enum, or field-name formats are rejected at the public MCP input when they are not intentionally public.

## Safe live probes

Real-system probes are separate from ordinary tests. Live mutations are excluded by default and require at least two independent operator opt-ins before credential access. Opt-in proves operator intent; it does not prove that the selected account, tenant, backend, or namespace is safe to mutate.

Before the first cleanup or mutation, independently verify that the resolved target is the intended exclusive disposable environment. The proof MUST bind a concrete target identity, such as a known sandbox account, provider environment identifier, or known fixture resource. If target verification cannot be completed, the probe stops before pre-clean, create, update, or delete. A test prefix or apparently empty resource list is not target-identity proof.

Cleanup uses an explicit resource-appropriate strategy:

- `captured-id`: record identities returned by successful creates and delete only those identities;
- `unique-namespace`: use a collision-resistant test namespace and reconcile only resources proven to belong to it;
- `verified-baseline-difference`: for resources without a safe namespace, capture a verified pre-mutation baseline and reconcile only the bounded difference attributable to the test.

Pre-clean is permitted only after target verification succeeds. Capture created identities whenever the backend returns them, reconcile partially successful creates, and report every resource whose cleanup cannot be confirmed. Two opt-ins never authorize broad deletion by prefix or guessed identity.

Use the live-backend policy template and the default strict validator as a machine-readable floor. `--structural-only` is discovery tooling and cannot satisfy live-execution acceptance. Project tests must still prove target verification, mutation gating, and the selected cleanup strategies are actually enforced.
