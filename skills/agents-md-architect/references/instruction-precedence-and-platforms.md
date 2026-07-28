---
description: Apply portable AGENTS.md rules across coding-agent platforms with different discovery and precedence behavior.
doc_id: reference.agents-md-platform-precedence
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Compare every platform statement with the linked official documentation and verify discovery in the exact product surface used by the repository.
---

# Instruction precedence and platforms

## Portable core

Keep one repository-owned `AGENTS.md` contract, but do not assume every coding agent discovers, combines, or prioritizes it identically. Before relying on nested files, record the exact product surface, instruction filenames it supports, discovery root, combination behavior, and a command or UI that proves which files were loaded.

Repository instructions remain behavioral context rather than a hard security boundary. Enforce prohibitions through permissions, hooks, policy engines, CI, or runtime controls when non-compliance would be unsafe.

## OpenAI Codex

Codex uses `AGENTS.md` as repository guidance. Treat a file as scoped to its containing directory and descendants, keep the root file concise, and place local differences in deeper files. Verify the active instruction chain in the Codex surface used by the team because product behavior may evolve.

Official reference: [Introducing Codex](https://openai.com/index/introducing-codex/).

## GitHub Copilot

Support differs by product surface. GitHub's support matrix must be checked before assuming `AGENTS.md` is active. In supported IDE and cloud-agent surfaces, the nearest `AGENTS.md` in the directory tree takes precedence. Copilot CLI discovers instructions from the repository root, current directory, intermediate directories, and relevant nested directories; it combines applicable instruction files and does not define a general precedence order between all instruction types. Avoid conflicts and use `/instructions` in Copilot CLI to inspect the loaded set.

Official references:

- [Custom-instruction support matrix](https://docs.github.com/en/copilot/reference/custom-instructions-support)
- [Repository instructions in IDEs](https://docs.github.com/en/copilot/how-tos/configure-custom-instructions-in-your-ide/add-repository-instructions-in-your-ide)
- [Copilot CLI custom instructions](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions)

## Gemini CLI

Gemini CLI natively uses hierarchical `GEMINI.md` context. A repository may configure `context.fileName` to include `AGENTS.md`; without that configuration, do not claim native `AGENTS.md` loading. Nested context is discovered when Gemini works in the relevant directory, so verify the configured filename list and loaded context before relying on local overrides.

Official reference: [Gemini CLI hierarchical memory](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/gemini-md.md).

## Claude Code

Claude Code natively loads `CLAUDE.md`, not `AGENTS.md`. Reuse the portable contract through a small `CLAUDE.md` containing `@AGENTS.md`, then add only Claude-specific differences. Claude concatenates applicable ancestor and local instruction files rather than treating them as a universal nearest-file replacement model. Do not use a symlink as the portable default because Windows may require elevated privileges; prefer the documented import.

Official reference: [How Claude remembers your project](https://code.claude.com/docs/en/memory).

## Platform adapters

Platform-specific files must be thin adapters. They may import or route to the portable core and state product-only mechanics, but they must not duplicate the full repository policy. Validate adapters for conflicts whenever the portable core or supported platform set changes.
