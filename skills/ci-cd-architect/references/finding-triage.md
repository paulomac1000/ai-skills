---
afds_schema_version: 2
description: Evidence-based triage protocol for scanner, linter, reviewer-bot, dependency, and security findings before code changes or acceptance claims.
doc_id: reference.finding-triage
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification:
  kind: ci-job
  value: Validate triage records and run a regression that distinguishes reproduced defects, standard violations, compatibility findings, accepted risks, and tool false positives.
---

# Finding triage

## Purpose

A scanner, linter, reviewer bot, dependency service, or AI reviewer produces a finding, not an authoritative patch. Suggestions are evaluated against the exact framework, version, call path, threat model, and repository policy before code changes.

Mechanical adoption of an incompatible suggestion can introduce defects while creating a false record that the original issue was fixed. For example, a helper from one web framework is not a valid replacement inside an unrelated standard-library HTTP handler merely because both return JSON.

## Required triage record

Every blocking finding that changes code or is dismissed records:

```yaml
finding_id: stable-tool-or-review-id
source:
  kind: sast | linter | dependency | reviewer-bot | human-review | runtime
  tool: exact-name
  version: exact-version-or-revision
  rule: exact-rule-id
location:
  path: repository-relative/path
  symbol: exact-call-path-or-symbol
runtime_context:
  framework: exact-framework-or-standard-library
  package_versions: {}
  entrypoint: exact-runtime-entrypoint
  reachable: true | false
reproduction:
  command: exact-command
  result: reproduced | not-reproduced | not-applicable
  evidence_path: repository-relative-machine-result
classification: standard-violation | implementation-defect | compatibility-issue | accepted-risk | tool-false-positive
decision:
  action: fix | suppress-locally | configure-tool | accept-with-waiver
  rationale: concrete-reason
regression:
  selector: exact-test-file::test-name
  fails_before_fix: true | false
  passes_after_fix: true | false
waiver_id: null | owned-waiver-id
```

A broad badge, green job, screenshot, prose-only comment, or the tool's proposed patch is not sufficient evidence.

## Triage procedure

### 1. Identify the actual runtime

Confirm:

- exact source file and symbol;
- production entrypoint and whether the path is reachable;
- framework or standard-library implementation;
- dependency and runtime versions;
- generated, vendored, test-only, compatibility, or production ownership;
- trust boundary and attacker-controlled inputs.

Do not infer a framework from method names, response shapes, decorators, or file extensions.

### 2. Reproduce the behavior

Prefer the smallest executable reproducer that traverses the real call path. It must distinguish:

- unsafe behavior;
- controlled rejection;
- unreachable dead code;
- scanner parse limitation;
- version-specific behavior;
- a violated repository standard without an immediately exploitable runtime defect.

For security findings, include a negative assertion that protected I/O, process creation, network dispatch, secret access, or publication did not occur.

### 3. Classify precisely

Use one classification:

- `standard-violation`: the repository violates a normative contract even when the generic tool described the mechanism poorly;
- `implementation-defect`: executable behavior is wrong or unsafe for the actual call path;
- `compatibility-issue`: behavior is valid in one supported version/profile but not another;
- `accepted-risk`: the issue is real, time-bounded, owned, and protected by compensating controls;
- `tool-false-positive`: the reported behavior is impossible or already safely controlled in the exact context.

Do not call a finding false positive merely because the proposed patch is wrong. A bad remediation can accompany a real defect.

### 4. Choose the narrowest valid remediation

A valid remediation may be:

- application code change;
- framework-specific configuration;
- dependency upgrade or pin;
- policy or manifest correction;
- local suppression bound to exact path/rule with rationale;
- scanner configuration correction;
- owned waiver with expiry and compensating controls.

Never disable a rule repository-wide to silence one context-specific result unless the rule is proven invalid for every covered path.

### 5. Add a regression before closure

A fixed defect or compatibility issue requires an executable regression that:

- traverses the affected call path;
- fails on the vulnerable or incompatible behavior;
- passes after the remediation;
- verifies the security or functional postcondition, not merely a source token;
- has an exact test-case identity in evidence.

A false positive requires a reproducer or structural proof that demonstrates why the claimed path cannot occur. Retain it when future refactors could make the finding real.

## Security scanner guidance

For shell, subprocess, SSH, filesystem, URL, deserialization, authentication, and workflow findings, include adversarial inputs relevant to the actual parser and platform. Do not translate one ecosystem's remediation idiom into another without proving equivalent semantics.

For dependency findings, distinguish:

- installed and reachable vulnerable code;
- installed but unreachable feature;
- build-only or test-only package;
- transitive package constrained by the platform;
- fixed release that changes public behavior;
- advisory affecting another major or transport profile.

Reachability can affect priority and compensating controls, but a repository policy may still require removing the vulnerable package.

## Reviewer-bot feedback

Review every bot comment independently. Agreement with one comment does not validate adjacent comments. When rejecting a suggestion, record the exact framework/call-path reason and, when useful, add a regression preventing the suggested incompatible pattern.

Do not optimize for clearing comment count. Optimize for correct code, explicit residual risk, and evidence that the selected behavior is intentional.

## Acceptance

A finding is closed only when one of these is true:

- the exact regression passes on the fixed revision;
- an exact local suppression/configuration change is validated and justified;
- an owned, expiring waiver is accepted by the required authority;
- a false-positive reproducer or proof is attached to the exact finding.

Commit messages and PR replies summarize the outcome but do not replace machine evidence.
