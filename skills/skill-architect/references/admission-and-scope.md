---
description: Decide whether reusable behavior deserves a new skill and define one coherent semantic boundary before authoring.
doc_id: reference.skill-architect-admission
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Record representative tasks, the nearest existing owner, and the reason a new or changed skill is the smallest durable abstraction.
---

# Skill admission and scope

Read this reference before scaffolding a new skill or splitting an existing one.

## Admission questions

A new skill candidate should answer all of these:

1. What recurring user outcome or failure is being addressed?
2. Which real prompts or tasks demonstrate the need?
3. Why is project-local guidance, an existing skill, a profile, a reference, or an executable tool insufficient?
4. What single semantic responsibility will this skill own?
5. What are the nearest tasks that must route somewhere else?
6. Is the value capability uplift, workflow-policy fidelity, or both?
7. What evidence would demonstrate that the skill is useful after publication?

Reject a new skill when the answer is mainly "the current document is long" or
"this topic deserves its own folder".

## Placement decision

Use project or repository instructions for behavior needed in most tasks within
one repository. Use a reference when a conditional procedure belongs to an
existing skill. Use a template or tool when the behavior is primarily
structural or mechanical. Use a new skill only when selection itself is a
meaningful reusable decision.

## Split decision

Prefer references when one trigger leads to one coherent workflow with optional
depth. Split into multiple skills when there are independent activation
conditions, independent canonical owners, or consumers routinely need one half
without the other.

Size can reveal a context problem but does not prove a semantic split.
