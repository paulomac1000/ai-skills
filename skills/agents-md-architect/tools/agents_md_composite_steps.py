"""Composite-action step parsing: validated working directories, shells, nested uses."""

from __future__ import annotations

import posixpath

from agents_md_shell_evidence_impl import (
    _compose_yaml,
    _extract_powershell_invocations,
    _mapping_value,
)
from agents_md_shell_scoping import shell_invocations_with_scope
from yaml.nodes import MappingNode, ScalarNode, SequenceNode


def _static_working_directory(value: str | None) -> str | None:
    if value is None or not value.strip():
        return "."
    candidate = value.strip()
    dynamic = "${{" in candidate or "$" in candidate or "`" in candidate
    dynamic = dynamic or candidate.startswith(("~", "/"))
    if dynamic:
        return None
    normalized = posixpath.normpath(posixpath.join(".", candidate))
    if normalized == ".." or normalized.startswith("../") or normalized.startswith("/"):
        return None
    return normalized


def composite_action_invocations(
    text: str, relative: str
) -> tuple[list[tuple[str, str, str | None]], list[str], list[str]]:
    """Return (command, working_directory, pythonpath) triples with per-step env (review dHfz)."""
    scoped: list[tuple[str, str, str | None]] = []
    issues: list[str] = []
    references: list[str] = []
    root = _compose_yaml(text)
    if root is None:
        issues.append(f"composite action YAML is malformed at {relative}")
        return scoped, issues, references
    runs = _mapping_value(root, "runs")
    if runs is not None and not isinstance(runs, MappingNode):
        issues.append(f"composite action runs is malformed at {relative}")
        return scoped, issues, references
    steps = _mapping_value(runs, "steps") if runs is not None else None
    if steps is not None and not isinstance(steps, SequenceNode):
        issues.append(f"composite action steps is malformed at {relative}")
        return scoped, issues, references
    if steps is None:
        return scoped, issues, references
    for index, step in enumerate(steps.value):
        if not isinstance(step, MappingNode):
            continue
        scalars = {
            key.value: value.value
            for key, value in step.value
            if isinstance(key, ScalarNode) and isinstance(value, ScalarNode)
        }
        non_scalar_wd = any(
            key.value == "working-directory" and not isinstance(value, ScalarNode) for key, value in step.value
        )
        if non_scalar_wd:
            issues.append(f"composite step working-directory is unresolved at {relative} step {index}")
            continue
        env = _mapping_value(step, "env")
        if env is not None and not isinstance(env, MappingNode):
            issues.append(f"composite step env is malformed at {relative} step {index}")
            continue
        step_pythonpath: str | None = None
        if env is not None:
            for key, value in env.value:
                if key.value != "PYTHONPATH":
                    continue
                if not isinstance(value, ScalarNode):
                    issues.append(f"composite step PYTHONPATH is unresolved at {relative} step {index}")
                    continue
                candidate = value.value.strip()
                if candidate:
                    step_pythonpath = candidate
        nested_uses = scalars.get("uses")
        if isinstance(nested_uses, str) and nested_uses.startswith("./"):
            references.append(nested_uses)
        raw_working_directory = (scalars.get("working-directory") or ".").strip() or "."
        run_value = scalars.get("run")
        working_directory = _static_working_directory(raw_working_directory)
        if working_directory is None:
            issues.append(f"composite step working-directory is unresolved at {relative} step {index}")
            continue
        if not run_value:
            continue
        shell_kind = (scalars.get("shell") or "bash").strip().casefold()
        if shell_kind in {"pwsh", "powershell"}:
            for command in sorted(_extract_powershell_invocations(run_value)):
                scoped.append((command, working_directory, step_pythonpath))
            continue
        if shell_kind not in {"bash", "sh"}:
            issues.append(f"composite step shell is unsupported at {relative} step {index}: {shell_kind!r}")
            continue
        step_scoped, step_issues = shell_invocations_with_scope(
            run_value, working_directory, f"{relative} composite step {index}"
        )
        scoped.extend((command, cwd, step_pythonpath) for command, cwd in step_scoped)
        issues.extend(step_issues)
    return scoped, issues, references
