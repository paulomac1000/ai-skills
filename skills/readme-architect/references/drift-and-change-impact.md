---
afds_schema_version: 2
description: Classifies README fact volatility and defines source changes that require README impact review without creating manual synchronization chains.
doc_id: reference.readme-drift-and-change-impact
type: reference
status: active
rigor: informative
owners: [repository-maintainers]
---

# README drift and change impact

README drift is usually caused by copying facts whose canonical owner changes
more frequently than prose review.

## High-volatility facts

Treat these as high volatility unless the project proves otherwise:
- exact tool/API counts;
- exact test counts;
- coverage percentages;
- current version on a moving default branch;
- dependency versions;
- current release status;
- supported model/provider inventory;
- generated command catalog;
- full environment-variable inventory;
- current benchmark numbers;
- compatibility lists driven by CI;
- deployment image digests.

Prefer live badges, generated references, runtime introspection, or links.

## Medium-volatility facts

Review when related code changes:
- runtime version range;
- ports and transports;
- default bind address;
- required configuration;
- install/start commands;
- major capability groups;
- supported backends;
- default security mode;
- health endpoints;
- package/container names.

These can appear inline when they are important to onboarding, but they need
clear ownership and review triggers.

## Low-volatility facts

Usually safe inline:
- project purpose;
- stable conceptual architecture;
- license family;
- contribution/security-reporting route;
- enduring safety philosophy.

Even low-volatility facts still need evidence.

## Change triggers

README impact MUST be assessed when a diff touches a source that may change the
public onboarding or operational contract.

Common triggers:

| Changed source | README questions |
|---|---|
| package manifest / runtime config | install command, runtime support, executable name? |
| CLI parser / console scripts | usage, flags, examples? |
| MCP/API registry | capability summary, client example, public contract? |
| config schema / `.env.example` | required setup, defaults, security gates? |
| transport/server wiring | ports, paths, bind scope, auth, health? |
| policy/authorization code | read/write/destructive/security claims? |
| Dockerfile/compose | image/run command, ports, volumes, user, networking? |
| CI matrix | supported/tested versions? |
| publish/release workflow | normal installation artifact? |
| public response/schema | examples, compatibility, migration? |
| dependency/backend support | requirements, feature claims? |
| license/security policy | footer/routing? |
| architecture entrypoints | mental model/deep docs links? |

## No-update outcome

“README reviewed; no change needed” is valid.

Do not create meaningless README churn for internal refactors that leave the
public/user contract unchanged.

## What not to synchronize manually

Do not create a rule that says “remember to update these five copies”.

Instead:
1. choose one canonical owner;
2. generate secondary representations where possible;
3. link from README;
4. add a deterministic drift check for repeated stable subsets that must remain
   visible.

## Existing README migration

When modernizing an old README:
1. inventory every factual claim;
2. mark each claim verified / stale / redundant / unknown;
3. identify duplicate owners;
4. preserve valuable user journeys and wording;
5. delete historical or duplicated data that has a better owner;
6. add missing verification and security boundaries;
7. reorganize only after truth has been reconciled.

Do not treat formatting cleanup as factual migration.
