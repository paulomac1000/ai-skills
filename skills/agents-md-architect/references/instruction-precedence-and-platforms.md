---
description: Apply portable AGENTS.md rules across coding-agent platforms with different discovery, precedence, and context-budget behavior.
doc_id: reference.agents-md-platform-precedence
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Compare every platform statement with the linked official documentation and verify discovery in the exact product surface used by the repository.
---

# Instruction precedence and platforms

## Portable core

Keep one repository-owned `AGENTS.md` contract, but do not assume every coding agent discovers, combines, prioritizes, or truncates it identically. Before relying on nested files, record the exact product surface, supported filenames, discovery root, combination behavior, context limit, and a command or UI that proves which files were loaded.

Repository instructions remain behavioral context rather than a hard security boundary. Enforce prohibitions through permissions, hooks, policy engines, CI, or runtime controls when non-compliance would be unsafe.

## OpenAI Codex

Codex builds project guidance from the project root to the current working directory. In each directory it selects the first available file in this order:

1. `AGENTS.override.md`;
2. `AGENTS.md`;
3. each configured `project_doc_fallback_filenames` entry in configuration order.

The selected files are concatenated from root to leaf and bounded by `project_doc_max_bytes`. The default aggregate budget is 32 KiB (`32768` bytes). A valid root file and valid nested file can therefore each satisfy this skill's per-document review budget while their effective Codex chain exceeds the product budget.

Use the platform validator whenever Codex is an intended consumer:

```bash
python skills/agents-md-architect/tools/validate_agents_md.py \
  --platform codex \
  --project-doc-max-bytes 32768 \
  --repository-root . \
  AGENTS.md
```

Repeat `--project-doc-fallback-filename` in the same order as the Codex configuration. The validator applies same-directory override precedence, computes each effective root-to-leaf chain, rejects unsafe symlink candidates, and fails when a chain exceeds the configured budget. Generic validation deliberately does not impose the Codex limit.

Official references:

- [Codex configuration reference](https://developers.openai.com/codex/config-reference/)
- [Unrolling the Codex agent loop](https://openai.com/index/unrolling-the-codex-agent-loop/)

## GitHub Copilot

Support differs by product surface. Code review, coding agent, IDE chat, and Copilot CLI do not expose one universal `AGENTS.md` loading or byte-budget contract. Check GitHub's support matrix for the exact surface before claiming that a file is active.

In supported IDE and cloud-agent surfaces, the nearest applicable repository instruction file may take precedence. Copilot CLI discovers instructions from the repository root, current directory, intermediate directories, and relevant nested directories; it combines applicable instruction files and does not define a universal precedence order across every instruction type. Avoid conflicts and use `/instructions` in Copilot CLI to inspect the loaded set. Do not reuse the Codex 32 KiB limit for Copilot unless GitHub documents that limit for the selected surface.

Official references:

- [Custom-instruction support matrix](https://docs.github.com/en/copilot/reference/custom-instructions-support)
- [Repository instructions in IDEs](https://docs.github.com/en/copilot/how-tos/configure-custom-instructions-in-your-ide/add-repository-instructions-in-your-ide)
- [Copilot CLI custom instructions](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions)

## Gemini CLI

Gemini CLI natively uses hierarchical `GEMINI.md` context. A repository may configure `context.fileName` to include `AGENTS.md`; without that configuration, do not claim native `AGENTS.md` loading. Context is loaded hierarchically for the relevant working directory. Verify the configured filename list and the loaded context before relying on local rules. Do not invent a Codex-equivalent aggregate byte limit where Gemini documentation does not define one.

Official reference: [Gemini CLI hierarchical memory](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/gemini-md.md).

## Claude Code

Claude Code natively loads `CLAUDE.md`, not `AGENTS.md`. Reuse the portable contract through a small `CLAUDE.md` containing `@AGENTS.md`, then add only Claude-specific differences. Claude combines applicable ancestor and local instruction files rather than following a universal nearest-file replacement model. Do not assign the Codex context budget to Claude without an independently documented Claude limit. Prefer documented imports over symlinks because Windows may require elevated privileges.

Official reference: [How Claude remembers your project](https://code.claude.com/docs/en/memory).

## Platform adapters

Platform-specific files must be thin adapters. They may import or route to the portable core and state product-only mechanics, but they must not duplicate the full repository policy. Validate adapters for conflicts whenever the portable core, platform configuration, or supported product surface changes.
