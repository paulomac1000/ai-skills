---
name: mcp-gateway-release-verifier
description: Compose exact-artifact identity, schema, real-transport, execution-integrity, health, lifecycle, and cleanup evidence into one bounded MCP release verdict.
---

# MCP Gateway Release Verifier

Use this skill when a candidate MCP gateway or server needs release acceptance against the exact built artifact.

Read `STANDARD.md`, then collect phase evidence from the owning contracts instead of reimplementing them. Use `tools/compose_release_verdict.py` to build the bounded receipt.

The verifier composes candidate identity (#49), exact-candidate schema acceptance (#60), real-transport dogfood (#66), execution integrity (#67), bootstrap, isolation, and cleanup evidence. A missing or failed required phase is never release confidence.

Feature-specific checks may be appended as bounded extension phases; they do not replace the baseline phases.
