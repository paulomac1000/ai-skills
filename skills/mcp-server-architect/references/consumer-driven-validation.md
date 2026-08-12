---
description: Consumer-driven validation model that turns real downstream migrations into permanent ai-skills regression canaries.
doc_id: reference.mcp-consumer-driven-validation
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Run the consumer-canary CI job against every immutable revision in contracts/consumer-canaries.yaml and review drift before changing normative migration guidance.
---

# Consumer-driven validation

## Why canaries exist

Synthetic generators prove a baseline, but they do not prove that an existing repository can be discovered and migrated without false assumptions. Reusable findings from real migrations therefore become one of three artifacts: a standard invariant, an executable validator, or an immutable external consumer canary. New prose without one of those enforcement paths is incomplete remediation.

## Cheap source canary

`check_consumer_canaries.py` fetches exact public commit SHAs, never executes consumer code, and runs the bounded read-only inspector. The catalog records only facts that the inspector must continue to discover correctly. This lane is safe for every pull request and catches regressions in SDK routing, upstream discovery, packaging, external-test discovery, and progressive planning.

The canary catalog is intentionally the only repository file allowed to contain the concrete consumer repository names. Those names are regression evidence, not normative examples or domain-specific guidance.

## Full consumer exercise

A heavier consumer exercise may run on a reviewed immutable consumer revision when it executes without protected credentials. It should build the consumer artifact, prove imports come from the installed artifact, use the public MCP composition and official client, and validate generated assessment/evidence records. Live backend prerequisites remain `external prerequisite unavailable / not executed`; absence of credentials is never converted into a pass.

Never give assessed consumer code provider credentials used to approve its own evidence. Provider correlation and acceptance remain separate trusted steps.

## Promotion rule

A consumer incident is generalized only after reproducing the actual failure. The preferred loop is `consumer failure -> minimal fact discovery -> generic invariant -> executable check -> consumer canary -> exact-head repository gate`. A bot suggestion or theoretical edge case without a reproduced contract violation does not outrank this loop.
