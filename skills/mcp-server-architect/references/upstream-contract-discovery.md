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

## Public boundary

The MCP public contract remains canonical even when the upstream dialect is not. Test the full boundary `public input -> canonical domain value -> upstream adapter -> upstream dialect`, and add a negative test proving backend-only date, money, identifier, enum, or field-name formats are rejected at the public MCP input when they are not intentionally public.

## Safe live probes

Real-system probes are separate from ordinary tests. Live mutations are excluded by default, require at least two independent opt-ins, delay credential access until after those opt-ins, use a unique test namespace, capture created identities, reconcile after partially successful creates, and report every resource whose cleanup cannot be confirmed. Use the live-backend policy template and validator as a machine-readable floor; project tests must still prove the policy is actually enforced.
