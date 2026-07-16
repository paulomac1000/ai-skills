# AFDS document type profiles

Choose the type from the question the reader must answer.

## Workflow

Use for a task with an observable finish.

Required sequence: outcome, prerequisites, safety, steps, validation, failure recovery, rollback or safe stop.

## Reference

Use for lookup of rules, options, fields, commands, or compatibility.

Required sequence: scope, definitions, normative facts or lookup tables, constraints, examples, non-goals.

## System

Use for a running component and its operational behavior.

Required sequence: current responsibility, boundaries, architecture, interfaces, state and invariants, failure modes, observability, testing, troubleshooting.

## Guide

Use for learning or explanation.

Required sequence: audience and outcome, context, walkthrough or conceptual model, rationale, trade-offs, pitfalls, related canonical references.

## Decision

Use when alternatives were genuinely available and the chosen option constrains future work.

Required sequence: status, context, decision, alternatives, consequences, validation or review trigger.

## Contract

Use for externally observable behavior between components or teams.

Required sequence: scope, inputs, outputs, errors, compatibility, security, examples, versioning and deprecation.

## Split test

Split a document when both are true:

- two sections answer different primary search intents, and
- either section can evolve without forcing the other to change.

Do not split solely to make files short.
