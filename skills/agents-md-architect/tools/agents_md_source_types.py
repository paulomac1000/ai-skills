"""Bounded data types and limits for static AGENTS.md gate-source discovery."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Classification = Literal["ci_entrypoint", "task_entrypoint", "helper", "library", "generated", "excluded"]
ExternalCheckoutKind = Literal["pinned_revision", "trusted_lock", "candidate_input", "workflow_authority"]

GATE_SOURCE_POLICY_REVISION = "agents-md-gate-sources-5"
MAX_CLASSIFIER_FILE_BYTES = 2 * 1024 * 1024
MAX_WRAPPER_DEPTH = 4
MAX_IMPORT_DEPTH = 4
MAX_RELATED_SOURCE_FILES = 256

MAIN_GUARD = re.compile(r"""(?m)^\s*if\s+__name__\s*==\s*['"]__main__['"]\s*:""")
COMMAND_PATH_REFERENCE = re.compile(
    r"""(?:(?:python(?:3)?|bash|sh|pwsh|powershell)\s+|(?:\./)?\.venv/(?:Scripts/python\.exe|bin/python)\s+|\./)"""
    r"""(?P<path>(?:[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+|/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+|[A-Za-z0-9_.-]+\.(?:py|sh|ps1|rb)))"""
)

WELL_KNOWN_TASK_RUNNERS = {
    "Makefile",
    "makefile",
    "Justfile",
    "justfile",
    "Taskfile.yml",
    "Taskfile.yaml",
    "build.sh",
    "build.ps1",
}


@dataclass(frozen=True)
class GateSource:
    path: str
    classification: Classification
    counted: bool
    reason: str
    origins: tuple[str, ...] = ()


@dataclass(frozen=True)
class GateSourceInventory:
    policy_revision: str
    limit: int
    count: int
    headroom: int
    sources: tuple[GateSource, ...]
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModuleInvocation:
    path: str
    module: str
    import_roots: tuple[str, ...]
    origin: str


@dataclass(frozen=True)
class ExternalCheckout:
    repository: str
    revision: str
    kind: ExternalCheckoutKind


@dataclass(frozen=True)
class CheckoutContext:
    job_id: str
    step_index: int
    aliases: tuple[tuple[str, ExternalCheckout | None], ...]
    unresolved_aliases: tuple[str, ...]


@dataclass(frozen=True)
class CommandSource:
    path: str
    working_directory: str
    command: str
    origin: str
    checkout_context: CheckoutContext | None = None


@dataclass(frozen=True)
class WorkflowCommandScan:
    commands: tuple[CommandSource, ...]
    issues: tuple[str, ...]


@dataclass(frozen=True)
class TaskSourceScan:
    references: dict[str, tuple[str, ...]]
    module_invocations: dict[str, tuple[ModuleInvocation, ...]]
    direct_python: dict[str, tuple[ModuleInvocation, ...]]
    package_initializers: dict[str, tuple[ModuleInvocation, ...]]
    external_sources: dict[str, tuple[str, ...]]
    issues: tuple[str, ...]
