"""Continuation-aware wrapper for structural shell command evidence."""

from __future__ import annotations

from pathlib import Path

import agents_md_shell_evidence_impl as _impl

INVALID_YAML_MESSAGE = _impl.INVALID_YAML_MESSAGE
_normalize_invocation = _impl._normalize_invocation
_command_path_tokens = _impl._command_path_tokens
_yaml_syntax_error = _impl._yaml_syntax_error
_extract_shell_invocations = _impl._extract_shell_invocations
_extract_yaml_invocations = _impl._extract_yaml_invocations
_extract_powershell_invocations = _impl._extract_powershell_invocations
_extract_jenkins_invocations = _impl._extract_jenkins_invocations
_shell_line_continues = _impl._shell_line_continues
_logical_shell_lines = _impl._logical_shell_lines


def _extract_recipe_invocations(text: str, *, makefile: bool) -> set[str]:
    """Extract recipes while preserving Make backslash-newline continuations."""
    if not makefile:
        return _impl._extract_recipe_invocations(text, makefile=False)

    invocations: set[str] = set()
    pending: list[str] = []

    def flush() -> None:
        if pending:
            invocations.update(_impl._extract_shell_invocations("\n".join(pending)))
            pending.clear()

    for raw_line in text.splitlines():
        if not raw_line.startswith("\t"):
            flush()
            continue
        recipe_line = raw_line[1:]
        if not pending:
            recipe_line = recipe_line.lstrip("@-+")
        pending.append(recipe_line)
        if not _impl._shell_line_continues(recipe_line):
            flush()
    flush()
    return invocations


def _extract_gate_invocations(relative: str, text: str) -> set[str]:
    if Path(relative).name.casefold() == "makefile":
        return _extract_recipe_invocations(text, makefile=True)
    return _impl._extract_gate_invocations(relative, text)
