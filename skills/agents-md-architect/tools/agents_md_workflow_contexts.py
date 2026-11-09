"""Ordered, job-scoped GitHub workflow command and checkout evidence."""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

from agents_md_checkout_sources import classify_checkout, normalize_checkout_working_directory
from agents_md_shell_evidence_impl import (
    _compose_yaml,
    _extract_powershell_invocations,
    _extract_shell_invocations,
    _github_condition_is_statically_false,
    _github_run_defaults,
    _github_runner_default_shell,
    _github_shell_kind,
    _mapping_value,
    _scalar_value,
    _shell_override,
    _working_directory_override,
    _yaml_syntax_error,
)
from agents_md_shell_scoping import shell_invocations_with_scope
from agents_md_source_types import (
    COMMAND_PATH_REFERENCE,
    CheckoutContext,
    CommandSource,
    ExternalCheckout,
    WorkflowCommandScan,
)
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

GITHUB_PYTHON_LAUNCHER = re.compile(
    r"""\$\{\{\s*runner\.os\s*==\s*['\"]Windows['\"]\s*&&\s*['\"](?:\./)?\.venv/Scripts/python\.exe['\"]\s*\|\|\s*['\"]python['\"]\s*\}\}"""
)
GITHUB_PYTHON_TAIL = re.compile(r"^python\s+['\"]\}\}['\"]\s+(?P<argv>.+)$")
GITHUB_ENV_REFERENCE = re.compile(r"^\$\{\{\s*env\.([A-Za-z_][A-Za-z0-9_]*)\s*\}\}$")


def _resolve_environment_reference(value: str | None, scopes: tuple[Node | None, ...]) -> str | None:
    if value is None:
        return None
    match = GITHUB_ENV_REFERENCE.fullmatch(value.strip())
    if match is None:
        return value

    name = match.group(1)
    resolved = value
    found = False
    for scope in scopes:
        if not isinstance(scope, MappingNode):
            continue
        for key_node, value_node in scope.value:
            if isinstance(key_node, ScalarNode) and key_node.value == name:
                if not isinstance(value_node, ScalarNode) or not value_node.value.strip():
                    return value
                resolved = value_node.value.strip()
                found = True
                break
    return resolved if found else value


def _workflow_environment_value(name: str, scopes: tuple[Node | None, ...]) -> str | None:
    value: str | None = None
    found = False
    for scope in scopes:
        if not isinstance(scope, MappingNode):
            continue
        for key_node, value_node in scope.value:
            if isinstance(key_node, ScalarNode) and key_node.value == name:
                if not isinstance(value_node, ScalarNode):
                    return f"${{{{ unresolved env.{name} }}}}"
                value = _resolve_environment_reference(value_node.value, scopes)
                found = True
                break
    return value if found else None


def _static_working_directory(value: str | None) -> str | None:
    if value is None or not value.strip():
        return "."
    candidate = value.strip()
    if "${{" in candidate or "$" in candidate or "`" in candidate or candidate.startswith(("~", "/", "..")):
        return None
    return posixpath.normpath(candidate)


def composite_action_invocations(text: str, relative: str) -> tuple[list[tuple[str, str]], list[str], list[str]]:
    scoped: list[tuple[str, str]] = []
    issues: list[str] = []
    references: list[str] = []
    steps = _mapping_value(_mapping_value(_compose_yaml(text), "runs"), "steps")
    if not isinstance(steps, SequenceNode):
        return scoped, issues, references
    for index, step in enumerate(steps.value):
        if not isinstance(step, MappingNode):
            continue
        scalars = {
            key.value: value.value
            for key, value in step.value
            if isinstance(key, ScalarNode) and isinstance(value, ScalarNode)
        }
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
        step_scoped, step_issues = shell_invocations_with_scope(
            run_value, working_directory, f"{relative} composite step {index}"
        )
        scoped.extend(step_scoped)
        issues.extend(step_issues)
    return scoped, issues, references


def github_workflow_command_scan(
    relative: str, text: str, *, default_working_directory: str = "."
) -> WorkflowCommandScan:
    """Extract each command with the checkout snapshot valid at its job step."""
    if not relative.startswith(".github/workflows/") or Path(relative).suffix.casefold() not in {".yml", ".yaml"}:
        return WorkflowCommandScan((), ())
    root = _compose_yaml(text)
    if root is None:
        issue = _yaml_syntax_error(text)
        return WorkflowCommandScan(
            (), (f"cannot establish workflow checkout scope at {relative}: {issue}",) if issue else ()
        )

    workflow_cwd_node, workflow_shell_node = _github_run_defaults(root)
    workflow_cwd = _working_directory_override(workflow_cwd_node, default_working_directory)
    jobs = _mapping_value(root, "jobs")
    if not isinstance(jobs, MappingNode):
        return WorkflowCommandScan((), ())
    if workflow_cwd is None:
        return WorkflowCommandScan((), (f"workflow working directory is unresolved at {relative}",))

    commands: list[CommandSource] = []
    issues: list[str] = []
    local_action_references: list[str] = []
    has_python_launcher = GITHUB_PYTHON_LAUNCHER.search(text) is not None
    for job_index, (job_key, job) in enumerate(jobs.value):
        if not isinstance(job, MappingNode) or _github_condition_is_statically_false(job):
            continue
        has_runner, runner_shell = _github_runner_default_shell(job)
        if not has_runner:
            continue
        job_id = _scalar_value(job_key) or f"job-{job_index}"
        job_cwd_node, job_shell_node = _github_run_defaults(job)
        job_cwd = _working_directory_override(job_cwd_node, workflow_cwd)
        job_shell = _shell_override(job_shell_node, _shell_override(workflow_shell_node, runner_shell))
        steps = _mapping_value(job, "steps")
        if not isinstance(steps, SequenceNode):
            continue

        checkouts: dict[str, ExternalCheckout | None] = {}
        unresolved_aliases: set[str] = set()
        for step_index, step in enumerate(steps.value):
            if not isinstance(step, MappingNode) or _github_condition_is_statically_false(step):
                continue
            environment_scopes = (
                _mapping_value(root, "env"),
                _mapping_value(job, "env"),
                _mapping_value(step, "env"),
            )
            uses = _scalar_value(_mapping_value(step, "uses"))
            if isinstance(uses, str) and uses.startswith("./"):
                local_action_references.append(uses)
            if isinstance(uses, str) and uses.split("@", 1)[0] == "actions/checkout":
                options = _mapping_value(step, "with")
                alias, external, issue = classify_checkout(
                    relative,
                    _scalar_value(_mapping_value(options, "repository")),
                    _resolve_environment_reference(
                        _scalar_value(_mapping_value(options, "ref")),
                        environment_scopes,
                    ),
                    _scalar_value(_mapping_value(options, "path")),
                )
                condition = _scalar_value(_mapping_value(step, "if"))
                conditional = condition is not None and "".join(condition.split()).casefold() not in {
                    "true",
                    "${{true}}",
                }
                if alias is None:
                    if issue is not None:
                        issues.append(f"{issue} in job {job_id!r} step {step_index}")
                    continue
                if issue is not None or conditional:
                    checkouts.pop(alias, None)
                    unresolved_aliases.add(alias)
                    if issue is not None:
                        issues.append(f"{issue} in job {job_id!r} step {step_index}")
                    else:
                        issues.append(
                            f"conditional checkout ownership is unresolved in {relative} "
                            f"job {job_id!r} step {step_index} for alias {alias!r}"
                        )
                    continue
                checkouts[alias] = external
                unresolved_aliases.discard(alias)

            run_node = _mapping_value(step, "run")
            run = _scalar_value(run_node)
            if run is None:
                continue
            working_directory = _working_directory_override(_mapping_value(step, "working-directory"), job_cwd)
            shell = _shell_override(_mapping_value(step, "shell"), job_shell)
            if working_directory is None:
                issues.append(f"workflow command scope is unresolved at {relative} job {job_id!r} step {step_index}")
                continue
            shell_kind = _github_shell_kind(shell) if shell is not None else None
            scoped_entries: list[tuple[str, str]] | None = None
            if shell_kind is None:
                shell_invocations = _extract_shell_invocations(run)
                powershell_invocations = _extract_powershell_invocations(run)
                if shell is not None:
                    if shell_invocations or powershell_invocations or COMMAND_PATH_REFERENCE.search(run) is not None:
                        issues.append(f"workflow shell is unsupported at {relative} job {job_id!r} step {step_index}")
                    continue
                invocations = shell_invocations & powershell_invocations
                if not invocations and (
                    shell_invocations or powershell_invocations or COMMAND_PATH_REFERENCE.search(run) is not None
                ):
                    issues.append(f"workflow shell is unresolved at {relative} job {job_id!r} step {step_index}")
                    continue
            else:
                if shell_kind == "powershell":
                    invocations = _extract_powershell_invocations(run)
                else:
                    scoped_entries, cd_issues = shell_invocations_with_scope(
                        run, working_directory, f"{relative} job {job_id!r} step {step_index}"
                    )
                    issues.extend(cd_issues)
                    invocations = {command for command, _cwd in scoped_entries}
            if not invocations:
                continue

            local_aliases = tuple(alias for alias, owner in checkouts.items() if owner is None and alias != ".")
            pythonpath = _workflow_environment_value("PYTHONPATH", environment_scopes)
            line = run_node.start_mark.line + 1 if isinstance(run_node, ScalarNode) else 0
            origin = f"{relative}:{line}" if line else relative
            if scoped_entries is not None:
                command_entries: list[tuple[str, str]] = list(dict.fromkeys(scoped_entries))
            else:
                command_entries = [(command, working_directory) for command in sorted(invocations)]
            for command, command_directory in command_entries:
                normalized = GITHUB_PYTHON_LAUNCHER.sub("python", command)
                if has_python_launcher:
                    normalized = GITHUB_PYTHON_TAIL.sub(r"python \g<argv>", normalized)
                command_working_directory = normalize_checkout_working_directory(command_directory, local_aliases)
                checkout_context = CheckoutContext(
                    job_id,
                    step_index,
                    tuple(sorted(checkouts.items())),
                    tuple(sorted(unresolved_aliases)),
                    command_directory,
                )
                commands.append(
                    CommandSource(relative, command_working_directory, normalized, origin, checkout_context, pythonpath)
                )

    return WorkflowCommandScan(tuple(commands), tuple(sorted(set(issues))), tuple(local_action_references))
