---
description: Runtime ownership, safe filesystem, artifact, background-task, browser-automation, and embedded-host boundaries for MCP servers.
doc_id: reference.mcp-runtime-boundaries-and-artifacts
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Run path-escape, symlink-swap, task-recovery, session-quota, request-body, browser-profile, UI-drift, peer-identity, redirect/retry, embedded-host, and artifact-retention scenarios against the packaged server.
---

# MCP runtime boundaries and artifacts

## Filesystem authorization

A path string is not a resource identity. Resolve an operator-configured root once, resolve the requested path without trusting lexical prefixes, and prove the result is inside the authorized root with a component-aware operation such as `Path.is_relative_to`. A check based on `str(path).startswith(str(root))` is invalid because sibling prefixes, case normalization, alternate separators, mount points, and symlinks can escape the intended boundary.

For reads, validate the resolved path, allowed file type, maximum size, and disclosure class before opening. For writes, uploads, extraction, or deletion, define the symlink and reparse-point policy and prevent time-of-check/time-of-use replacement by using directory handles, no-follow operations, atomic replace, or a platform-equivalent mechanism. Archive extraction rejects absolute paths, parent traversal, special files, links, and decompression bombs.

Generated files use a server-owned output root. An arbitrary client path is not accepted merely because the process account can access it. Every artifact records owner, operation ID, MIME type, byte size, checksum when useful, creation time, expiry, and deletion result.

## Artifact lifecycle

Screenshots, exports, audio, firmware, backups, reports, and downloaded configuration are persistent effects even when the source operation is logically read-only. Their manifest therefore declares confidentiality, storage impact, retention owner, maximum size, cleanup behavior, and whether the model receives bytes, a bounded preview, or an opaque artifact handle.

Artifact creation is atomic. Partial files are not advertised as complete. Download capabilities reauthorize the caller against the artifact owner and target, stream with a hard byte bound, use a safe filename and MIME type, and do not reveal host filesystem paths. Expiry and explicit deletion remove associated indexes and temporary files. Cleanup failure is observable and retryable only when deletion itself is idempotent.

## Background work and task registry

A daemon thread, untracked `asyncio.create_task`, or transport connection is not a durable operation record. Work that can outlive one request is owned by a bounded task registry or durable task store. Each task has an unpredictable identifier with at least 128 bits of entropy, principal, stable target, capability, creation time, deadline, state, progress, cancellation state, final result or error, and expiry.

The supported state machine distinguishes at least `accepted`, `running`, `verifying`, `succeeded`, `failed`, `cancelled`, `unknown_outcome`, and `expired`. Restart, OTA, network changes, browser generation, exports, and other expected-disconnect operations enter `verifying` rather than becoming generic retryable timeouts. Postcondition verification decides the terminal state.

The registry bounds active tasks, queued tasks, per-principal tasks, retained completed tasks, and result size. Shutdown stops admission, cancels or persists owned work according to the contract, waits within a bounded grace period, and reports unfinished durable work. Fire-and-forget work is prohibited.

## HTTP and session resource bounds

Every remote transport defines maximum request-body bytes, header bytes, JSON nesting, batch size when applicable, response bytes, concurrent requests, queued requests, sessions, idle lifetime, total lifetime, and per-principal or per-credential rate limits. The server rejects an oversized body before buffering it in full. Streaming uploads and downloads enforce cumulative limits while reading.

Session identifiers use a cryptographically secure generator with at least 128 bits of entropy. Session state is bound to the authenticated principal and cannot be transferred by presenting only the identifier. Session deletion, timeout, and transport closure release only session-owned handles, subscriptions, streams, leases, and rate-limit reservations. They detach session references to durable tasks but do not delete or cancel task records merely because the initiating session disconnected. Durable task records remain principal- and target-bound until terminal completion, explicit authorized cancellation, retention expiry, or recovery policy removes them. Process-owned clients and tenant-owned pools remain alive until their owner scope closes.

Host, Origin, forwarded-header, proxy-trust, TLS, authentication, and authorization policies are evaluated before session creation. Missing Origin may be acceptable for a local non-browser client, but it never substitutes for authentication on a remote privileged server. Wildcard CORS does not coexist with credentialed privileged access.

## Browser automation and interactive authentication

A persistent browser profile contains credentials, cookies, local storage, history, and account identity. Treat it as a credential store: use a per-account directory with restrictive permissions, prohibit accidental packaging or backup, define encryption or OS credential-store integration when required, and provide explicit preview and cleanup. Account names are normalized and cannot select an arbitrary path.

Only one process owns a writable profile unless the browser framework documents safe sharing. Use a profile lock with stale-owner recovery. Shared browser contexts, visibility mode changes, reauthentication, cleanup, and profile rotation are serialized. A request cannot close or replace a shared context used by another request without an explicit coordinated transition.

Interactive authentication is an explicit state machine such as `not_configured`, `awaiting_user`, `authenticated`, `expired`, and `failed`. The server returns a bounded action for the human and never asks an agent to submit a password. Public HTTP exposure of interactive auth or a credential-bearing browser requires authenticated, account-scoped authorization.

External UI automation is an upstream contract, not a stable internal API. Centralize selectors and semantic expectations, version fixtures, detect login and consent interstitials, run a low-cost canary, capture sanitized diagnostics, and classify selector drift separately from authentication, rate limits, and upstream unavailability. Do not retry a state-changing browser action after an ambiguous timeout without reconciliation.

Content returned by an external AI or webpage preserves provenance and is marked as untrusted input. Citations, hidden text, page instructions, and generated answers cannot grant tool authority or reduce risk.

## Server instructions and progressive discovery

Use server-level instructions for cross-tool workflows, stable ID flow, required ordering, async polling chains, profile limitations, and confirmation rules. Do not duplicate the same workflow prose in every tool description. Instructions are advisory for agent usability and never replace runtime policy.

Tool profiles and disabled-tool settings affect the active capability catalog, schemas, manifests, resources, prompts, health, and tests consistently. A hidden or unavailable capability is not left active through another transport. Discovery returns stable identifiers needed by follow-up tools and explains how to poll or reconcile long-running work without exposing secrets.

## Multi-backend and embedded hosts

Multi-backend servers preserve the configured target. A failed default never changes to the first healthy backend. Before authentication, code may only parse and normalize a locally declared target selector without network I/O. The server then authenticates the principal and authorizes the capability and selector namespace before any network-backed discovery. It resolves the stable target within that authorized namespace, authorizes the resolved resource, and revalidates mutable address-to-identity mappings immediately before connection setup. For connection-oriented backends, it verifies the authenticated peer or service identity after connecting and before sending protected application data. Redirects and retries do not inherit the previous connection's authority: the server repeats selector-namespace authorization, target resolution, mutable address-to-identity revalidation, connection establishment, post-connect peer identity verification, and authorization of the resolved resource before continuing. Capability health identifies unavailable targets and backend kinds. Gateways preserve originating server, target, manifest provenance, and namespace so equal tool names cannot collide or transfer authority.

An MCP server embedded in another application does not own the host process, global event loop, logging configuration, dependency container, or unrelated network listeners. It receives host-owned services through an explicit adapter, closes only resources it owns, participates in host startup and shutdown, avoids port and route collisions, and cannot call process exit from a tool or transport callback.

## Verification

Package-level verification proves path containment under symlink races, artifact size and expiry, task admission and recovery, durable-task survival across session disconnect, session entropy and principal binding, bounded HTTP bodies, browser profile isolation and locking, selector-drift diagnostics, active-profile parity, multi-backend target preservation, post-connect peer/service identity verification, redirect/retry reauthorization, and embedded-host cleanup. Skipped applicable scenarios mean the affected capability or transport is not production-ready.
