---
description: Diagnostic matrix mapping common MCP server failures to corrective architecture and independently failing evidence.
doc_id: reference.mcp-problem-solution-matrix
type: reference
status: active
rigor: informative
owners: [repository-maintainers]
---

# MCP problem-solution matrix

| Symptom | Likely cause | Corrective control | Evidence |
| --- | --- | --- | --- |
| server connected but unusable | readiness conflated with process liveness or tool count | separate startup, readiness, liveness, capability health | dependency-failure and readiness-transition tests |
| one optional integration prevents startup | composition has hard global dependency | isolate registration and degrade capability | startup with dependency absent |
| configured target failure affects another target | implicit fallback selects first healthy backend | explicit target selection; no silent fallback | failed-default and mutation-target tests |
| operation reaches wrong device after discovery | mutable address treated as identity | bind and revalidate stable identity before I/O | DHCP or address-reuse test |
| REST call bypasses auth or sanitization | adapter invokes raw callable | one invocation kernel for every adapter | MCP versus REST policy-parity test |
| manual MCP endpoint lists dummy schemas | partial JSON-RPC implementation bypasses SDK | maintained SDK transport with conformance suite | real-client schema and handshake tests |
| client receives prose-only errors | wrapper lacks stable error contract | typed error category, message, retry, outcome, correlation | schema and client tests |
| every API failure looks not-found | adapter collapses status to null or false | preserve safe upstream error categories | upstream status matrix |
| duplicate mutation after timeout | retry without idempotency proof | durable idempotency key, dedupe, or no automatic retry | commit-then-timeout replay test |
| mutation may have completed but is labeled retryable | ambiguous outcome collapsed to generic failure | unknown-outcome state and reconciliation | ambiguous-completion test |
| conflict loop | retry without refreshed state | re-read version or precondition | optimistic concurrency test |
| expected restart appears as timeout | disconnecting operation lacks state machine | accepted/in-progress plus reconnect verification | expected-disconnect workflow |
| non-empty final page loops forever | pagination infers `has_more` from data presence | stable ordering and explicit termination | full-final and empty-page tests |
| financial value changes meaning | free-form amount, locale date, or float | decimal or minor units, currency, ISO 8601 | boundary and locale tests |
| cancellation does not stop work | token swallowed or blocking call unbounded | propagate cancellation and bound executor/downstream timeout | async and blocking in-flight cancellation |
| event loop already running error | sync compatibility helper creates or runs a loop | one owning loop and async public API | request from active-loop test |
| request IDs cross-contaminate | global or thread-local context in async server | `contextvars` with token reset | concurrent same-thread invocation |
| rate limit exceeded under concurrency | shared timestamp not serialized or wrong quota key | lock-safe token bucket scoped to credential/target | overlapping quota test |
| retries ignore upstream timing | fixed sleep without `Retry-After` or deadline | bounded jittered backoff within remaining deadline | retry-hint and deadline tests |
| sensitive read is treated safe | side-effect label used as complete risk model | separate confidentiality, cost, impact, and side effects | confidential-read policy test |
| credential result persists unexpectedly | generic cache includes sensitive endpoint | explicit confidentiality-aware cache policy | secret-cache prohibition test |
| API key appears in telemetry | credential passed in query URL and raw URL logged | URL/query redaction at log and trace source | captured log, trace, and proxy test |
| one global write switch enables raw admin | operator gate lacks capability and target scope | scoped policy and isolated privileged profiles | least-privilege profile test |
| public bind exposes privileged tools | acknowledgement flag mistaken for security | TLS, authentication, authorization, host and network policy | unauthenticated remote rejection |
| host changed without detection | SSH or device identity verification disabled | pinned identity or enrollment workflow | mismatch and rotation tests |
| shell allowlist still injectable | model values enter a shell template | fixed executable and arguments or closed fuzzed template | property-based injection tests |
| async server stalls | sync HTTP, filesystem, SSH, or subprocess runs on event loop | true async client or bounded executor | event-loop responsiveness and saturation |
| executor memory grows | unbounded `to_thread` submissions | bounded queue and rejection policy | saturation and shutdown tests |
| logs corrupt stdio | diagnostics written to stdout | reserve stdout for protocol, use stderr | protocol capture test |
| tool list consumes excessive context | eager full-schema discovery | supported versus active profiles and on-demand detail | token and discovery tests |
| registered tool lacks policy | manifest created automatically as read | fail registration on missing manifest | omitted-manifest test |
| schema changes after wrapping | callable mutated after SDK registration | install signature-preserving wrappers before registration | schema identity regression |
| configuration file appears ignored | modules read environment before loader runs | load typed settings before dependency imports | fresh-process config-order test |
| process says healthy with bad credentials | health payload is static or registry-only | dependency-aware readiness | invalid-credential readiness test |
| full tests slow or hang startup | repository suite used as runtime self-test | CI/artifact gates plus bounded diagnostics | production start without dev dependencies |
| context export leaks or fills disk | bulk read lacks minimization, limit, destination, retention | governed task/export contract | size, path, redaction, cancel, cleanup tests |
| target-wide operation crosses callers | process-global principal or target | request/session context plus target authorization | concurrent principals and targets |
| SDK upgrade silently changes behavior | private fields and broad version range | explicit package identity, compatibility adapter, stable/candidate lanes | version matrix and fail-closed probe |
| tests pass but client fails | only domain layer tested | public registration and real-client workflow | inspector or official client test |
| source tests pass but container fails | deployment artifact not tested | build once and smoke-test artifact | packaged artifact smoke |
| memory grows after disconnects | orphaned tasks, sessions, clients, or output buffers | bounded state and deterministic cleanup | disconnect and cancellation soak |
| multi-server tool semantics conflict | common name hides backend differences | backend capability matrix or split capabilities | cross-backend contract test |