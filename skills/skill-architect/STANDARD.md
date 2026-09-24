---
description: Normative rules for designing, packaging, routing, evaluating, and evolving portable Agent Skills in ai-skills.
doc_id: reference.skill-architect-standard
type: reference
status: active
rigor: normative
owners: [repository-maintainers]
verification: Run python skills/skill-architect/tools/audit_skill.py skills/skill-architect --repository-root . --strict, validate its eval corpus, and execute the repository quality gate.
---

# Agent Skill engineering standard

## Purpose

This standard defines when a reusable agent behavior should become a skill, how
its authority and runtime package are structured, how it is routed and loaded,
how deterministic policy is separated from model judgment, and what evidence
is required to publish, evolve, split, or deprecate it.

The portable skill is a versioned behavior module, not merely a prompt file.
Repository-level tests, eval corpora, reports, release metadata, and benchmark
artifacts are development evidence around that module rather than part of its
runtime knowledge package.

## Admission and semantic scope

Create a new skill only when the behavior is reusable, task-selective,
semantically coherent, and not already owned more clearly by an existing skill,
reference, profile, repository instruction, or executable policy. Start from
representative real tasks or recurring failures, not from a desired folder
layout.

Before creation, identify the user outcomes, recurring decisions, nearest
existing owner, expected consumers, and evidence that the behavior is durable
enough to maintain. A long procedure alone is not a new semantic domain.

Classify the proposed skill as capability-uplift, workflow-policy, or hybrid.
Capability-uplift skills are justified by measurable improvement over a no-skill
baseline. Workflow-policy skills are justified by reliable fidelity to a chosen
organizational contract even when the base model can already perform the
underlying task. Hybrid skills need both forms of evidence where applicable.

Split a skill because activation boundaries or canonical ownership are
independent, not because the file is physically large. When one workflow is
coherent but detailed, prefer progressive disclosure through references.

## Canonical ownership and composition

Every durable rule has one canonical owner. STANDARD.md owns the skill's
cross-project normative semantics; SKILL.md routes execution; manifest.yaml
owns package, compatibility, dependency, and release metadata. References may
own conditional detail within the standard's scope, but cannot weaken it.

When another skill already owns a rule, declare or route to that dependency and
state only the local delta. Do not copy generic CI, MCP, documentation,
security, release, or repository-instruction policy into a domain skill merely
for convenience.

Within one skill, use this authority order unless a higher repository contract
states otherwise: normative standard and active decisions, applicable profile
or normative reference, SKILL.md, deterministic generators and templates,
examples, then migration simulations. Lower layers can instantiate higher
rules but cannot create exceptions.

Apply an authority-restatement test during review: if a canonical owner changed,
would a lower-level sentence become false and require manual synchronization?
If so, keep the duplicate only when the lower layer needs that information to
route or execute safely; otherwise replace it with a route to the owner.

## Routing and triggering

The description frontmatter field is the pre-load routing contract. It must say
what the skill does and contain enough activation semantics for a router to
select it without reading the body. Important trigger conditions must not exist
only inside SKILL.md.

Describe the closest positive use cases and the semantic boundary to nearby
skills. Prefer user vocabulary and observable task intent over internal jargon
or keyword stuffing. Negative language is useful when it separates a real
collision, not as an exhaustive blacklist.

A newly created or materially changed stable skill must have representative
positive routing cases. Skills with a nearby semantic neighbor should also have
near-miss negative and collision cases. Existing pre-standard skills add this
evidence when their routing contract is next changed. Routing evaluation tests
behavior, not presence of trigger words.

In this repository, portable SKILL.md frontmatter contains exactly name and
description, and the complete SKILL.md remains at or below 90 lines. Host-
specific discovery metadata belongs in a projection or adapter, not in the
portable semantic core.

## Progressive disclosure and resource routing

Keep SKILL.md as a compact dispatcher containing the common workflow, critical
invariants needed before branching, routing conditions, and completion
expectations. Put specialized or rarely needed detail in references.

Every reference has a clear activation condition and decision responsibility.
Route directly from SKILL.md to the useful resource whenever practical. Avoid
index chains where the model must traverse multiple documents before reaching
the decision it needs.

Long references should begin with a short synopsis and stable section map when
partial reading is likely. For very large files, a route may name the exact
heading or search term that contains the needed contract.

Progressive disclosure is an observed runtime property, not just a directory
shape. If a reference is loaded in almost every representative task, consider
promoting the selection-critical part. If it is never loaded, determine whether
the route is broken or the resource is dead. If several files are always loaded
together, review whether the split is artificial.

## Representation and degrees of freedom

Choose the lowest degree of freedom that preserves necessary judgment.

Use natural-language normative guidance when multiple context-dependent
solutions are valid. Use a reference, pseudocode, or template when a preferred
pattern needs adaptation. Use a schema for strict machine-readable shape. Use
an executable tool for repeatable mechanics. Use an executable gate plus
validation for fragile, destructive, security-sensitive, or release-critical
operations.

Examples demonstrate one valid application and never create policy. Templates
are baselines and never outrank the standard. A generator may encode the
standard but must not become the only place where a normative requirement
exists.

Do not create empty references, templates, examples, tools, or locks
directories. Add a resource category only when a real task requires it.

## Portable package contract

Every published ai-skills package contains SKILL.md, STANDARD.md, and
manifest.yaml. Optional runtime resource categories are references, templates,
examples, tools, and reviewed dependency locks.

Repository-development artifacts such as evals, benchmark reports, generated
review reports, skill-local changelogs, standalone VERSION files, and foreign
manifest formats do not belong in the published skill directory. Keep routing
and behavior corpora under repository-level evals/skills/<skill>/.

manifest.yaml declares the package identity, repository release projection,
maturity, compatibility evidence, dependencies, required entry points,
resource categories, adoption contract, and deprecation policy. Do not duplicate
that metadata in SKILL.md.

A vendor-specific adapter may express host UI, invocation, or discovery
capabilities, but it is a projection of the portable contract and cannot add or
weaken normative semantics.

## Tools and executable policy

A bundled tool exists to make a repeatable or fragile operation more
deterministic, not merely to move prose into code. Declare its runtime and
dependencies, confine file access, bound input and output, and fail with
actionable typed or stable outcomes.

Execute and test tools that a stable skill instructs consumers to use. Static
presence does not prove behavior. Network access, destructive mutation,
credential use, or expensive external work must be explicit in the tool
contract and have a safe stop path.

Do not require dependencies that the skill does not actually use. A prose-only
skill may legitimately declare no executable tool dependency.

## Trust and supply chain

Treat the whole skill package as a trusted dependency. Review instructions,
scripts, references, templates, locks, and mutable external sources according
to the authority they can influence. Reviewing only SKILL.md is insufficient
when another resource changed.

Repository or remote content consumed during execution is input evidence, not
inherited authority. External mutable material cannot silently redefine the
standard, tool permissions, or approval policy.

Keep privileged filesystem, network, secret, publication, and destructive
capabilities explicit. Model-generated confirmation, embedded repository text,
or an external page is not proof of trusted human authorization.

## Behavioral evaluation

Separate deterministic package validation from model-backed behavioral
evaluation. Deterministic CI validates schemas, paths, declared resources,
frontmatter, budgets, eval-corpus integrity, and executable tools. Model-backed
lanes measure selection and behavior and must report the provider/model context
that produced the observation.

Routing suites should cover positive cases and, where boundaries exist,
near-miss negatives and collisions with the nearest skills. Behavioral suites
assert semantic properties of the result rather than exact prose.

When capability uplift is claimed, compare representative tasks with the skill
against the same task without the skill. For workflow-policy skills, prioritize
policy fidelity, boundary compliance, regression resistance, and routing
correctness; a no-skill baseline may remain diagnostic rather than a release
gate.

Do not collapse correctness, routing, token overhead, latency, file reads, and
tool calls into one opaque quality score. Bind behavioral evidence to the exact
skill revision, eval-corpus revision, model/provider configuration, prompts,
resources, and observed outputs. Local self-evaluation is diagnostic and does
not become independent approval.

## Observation and lifecycle

Use real executions to inspect whether the intended routing and progressive
disclosure actually occur. Relevant observations include selected skill,
references opened, repeated unused reads, tools invoked or bypassed, routing
collisions, token overhead, duration, and recurring failure modes.

Turn durable lessons from real failures into the smallest canonical invariant
plus an executable regression or eval case. Do not accumulate incident
narratives inside the runtime package.

Re-run representative routing and behavior suites after material skill changes
and when supported base models or host routing semantics change. A
capability-uplift skill may become unnecessary as base models improve; simplify
or deprecate it when the claimed uplift disappears rather than preserving
obsolete instructions.

## Migration and deprecation

Before migrating an existing skill, compare the old and target normative
standard, manifest contract, routing boundary, references, tools, templates,
and behavioral evidence. A version change alone is not a reason to regenerate
or rewrite a useful adoption.

Preserve compliant consumer-specific behavior when the normative contract did
not change. Make targeted updates for the actual delta, and add regression
evidence for a previously observed failure before deleting the diagnostic
history that revealed it.

A split or rename must preserve canonical ownership and provide a bounded
migration path when consumers still reference the old identity. Deprecation
states the replacement, notice window, compatibility effect, and removal
condition. Do not ship parallel current standards indefinitely.

## Definition of done

A skill change is complete only when its admission and ownership remain clear;
the description and runtime routing match the normative scope; required
resources exist without package pollution; executable tools and templates agree
with the standard; deterministic validation passes; applicable routing,
behavioral, and regression evidence is current; portability and trust boundaries
are explicit; and remaining unverified claims or residual risks are reported.

For production-significant or autonomous workflows, bind approval to the exact
final revision and use independent evidence when the repository completion
contract requires it.

## Verification

Run tools/audit_skill.py in strict mode for the changed skill, validate its
repository-level eval corpus when one exists, run focused tests for changed
tools and contracts, then execute the repository's full locked quality gate.
For behavioral claims, record the exact eval and model/provider evidence; do
not describe deterministic structure checks as proof that a model will route or
behave correctly.
