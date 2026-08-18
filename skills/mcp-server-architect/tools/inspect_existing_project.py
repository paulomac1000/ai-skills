#!/usr/bin/env python3
"""Inspect an existing repository without executing or modifying consumer code."""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import shlex
import stat
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.validate_live_backend_test_policy import validate_policy as validate_live_backend_policy  # noqa: E402
from contracts.validate_upstream_contract import validate_contract as validate_upstream_contract  # noqa: E402

MAX_FILES = 600
MAX_FILE_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 12 * 1024 * 1024
IGNORED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "bin",
    "obj",
    "__pycache__",
    ".pytest_cache",
}
TEXT_SUFFIXES = {".py", ".toml", ".txt", ".ini", ".yaml", ".yml", ".md", ".json"}
HTTP_DEPENDENCIES = {"requests", "httpx", "aiohttp", "urllib3"}
_PREBUILT_CONTAINER_DIRS = frozenset({"dist", "build", "out", "publish", "artifacts"})
_COPY_INSTRUCTION = re.compile(r"^(?:COPY|ADD)\b\s*(.*)$", re.IGNORECASE)
_FROM_INSTRUCTION = re.compile(r"^FROM\b", re.IGNORECASE)
_ARG_INSTRUCTION = re.compile(
    r"^ARG\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s*=\s*(.*))?$",
    re.IGNORECASE,
)
_ENV_INSTRUCTION = re.compile(r"^ENV\b\s*(.*)$", re.IGNORECASE)
_SOURCE_REVISION_ARG = re.compile(
    r"^\s*ARG\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE | re.MULTILINE,
)
_SOURCE_REVISION_FILE = re.compile(r"\bSOURCE[_-](?:REVISION|SHA)\b", re.IGNORECASE)
_SOURCE_REVISION_WRITE = re.compile(
    r"(?:>{1,2}\s*[^\s;&|]*SOURCE[_-](?:REVISION|SHA)\b|"
    r"\b(?:touch|tee|cp|mv)\b[^;&|]*\bSOURCE[_-](?:REVISION|SHA)\b)",
    re.IGNORECASE,
)
_WORKDIR_INSTRUCTION = re.compile(r"^WORKDIR\b\s*(.*)$", re.IGNORECASE)
_SHELL_INSTRUCTION = re.compile(r"^SHELL\b\s*(.*)$", re.IGNORECASE)
_RUN_INSTRUCTION = re.compile(r"^RUN\b\s*(.*)$", re.IGNORECASE)
_REVISION_METADATA_NAMES = ("SOURCE_REVISION", "SOURCE_SHA")
_SHELL_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$", re.DOTALL)
_SHELL_VARIABLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_OPAQUE_SHELL_EFFECT = re.compile(r"(?:`|\$\(|[<>])")
_REVISION_PROVENANCE_SAFE_BUILTINS = frozenset({":", "[", "[[", "echo", "false", "pwd", "test", "true"})
_TRUSTED_DOCKER_SHELLS = frozenset({("/bin/sh", "-c"), ("/bin/bash", "-c")})


def _regular_text(path: Path) -> str | None:
    try:
        metadata = path.lstat()
    except OSError:
        return None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        return None
    if metadata.st_size > MAX_FILE_BYTES:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _source_corpus(root: Path) -> tuple[str, int, int]:
    chunks: list[str] = []
    total = 0
    files = 0
    candidates = 0
    for directory, names, filenames in os.walk(root, topdown=True, followlinks=False):
        names[:] = sorted(name for name in names if name not in IGNORED_PARTS)
        base = Path(directory)
        for filename in sorted(filenames):
            candidates += 1
            if candidates > MAX_FILES * 20 or files >= MAX_FILES or total >= MAX_TOTAL_BYTES:
                return "\n".join(chunks).casefold(), files, total
            path = base / filename
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            text = _regular_text(path)
            if text is None:
                continue
            encoded_size = len(text.encode("utf-8"))
            if total + encoded_size > MAX_TOTAL_BYTES:
                return "\n".join(chunks).casefold(), files, total
            chunks.append(text)
            total += encoded_size
            files += 1
    return "\n".join(chunks).casefold(), files, total


def _pyproject(root: Path) -> dict[str, Any]:
    path = root / "pyproject.toml"
    text = _regular_text(path)
    if text is None:
        return {}
    try:
        value = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _dependency_names(project: dict[str, Any], root: Path) -> set[str]:
    names: set[str] = set()
    raw_project = project.get("project")
    if isinstance(raw_project, dict):
        dependencies = raw_project.get("dependencies")
        if isinstance(dependencies, list):
            for raw in dependencies:
                if not isinstance(raw, str):
                    continue
                token = raw.strip().split("[", 1)[0]
                for separator in ("==", ">=", "<=", "~=", "!=", ">", "<", ";", " "):
                    token = token.split(separator, 1)[0]
                if token:
                    names.add(token.casefold().replace("_", "-"))
    for candidate in sorted(root.glob("requirements*.txt")) + sorted(root.glob("requirements*.in")):
        text = _regular_text(candidate)
        if text is None:
            continue
        for line in text.splitlines():
            value = line.strip()
            if not value or value.startswith(("#", "-")):
                continue
            token = value
            for separator in ("==", ">=", "<=", "~=", "!=", ">", "<", ";", " "):
                token = token.split(separator, 1)[0]
            if token:
                names.add(token.casefold().replace("_", "-"))
    return names


def _project_version(project: dict[str, Any]) -> str | None:
    raw_project = project.get("project")
    if not isinstance(raw_project, dict):
        return None
    value = raw_project.get("version")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _pytest_addopts(project: dict[str, Any]) -> list[str]:
    """Return parsed pytest addopts from the structured pyproject configuration only."""
    tool = project.get("tool")
    pytest = tool.get("pytest") if isinstance(tool, dict) else None
    ini_options = pytest.get("ini_options") if isinstance(pytest, dict) else None
    raw = ini_options.get("addopts") if isinstance(ini_options, dict) else None
    fragments: list[str]
    if isinstance(raw, str):
        fragments = [raw]
    elif isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        fragments = list(raw)
    else:
        return []
    tokens: list[str] = []
    try:
        for fragment in fragments:
            tokens.extend(shlex.split(fragment))
    except ValueError:
        return []
    return tokens


def _marker_expression_excludes_external(expression: str) -> bool:
    """Conservatively prove that a pytest marker expression excludes every external test."""
    normalized = " ".join(expression.casefold().split())
    if re.search(r"\bor\b", normalized):
        return False
    return re.search(r"\bnot\s+external\b", normalized) is not None


def _external_tests_default_excluded(project: dict[str, Any]) -> bool:
    tokens = _pytest_addopts(project)
    for index, token in enumerate(tokens):
        if token == "-m" and index + 1 < len(tokens):
            if _marker_expression_excludes_external(tokens[index + 1]):
                return True
        elif token.startswith("-m=") and _marker_expression_excludes_external(token[3:]):
            return True
    return False


def _docker_instructions(text: str) -> list[str]:
    """Return bounded logical Dockerfile instructions with continuations joined."""
    instructions: list[str] = []
    current: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or (not current and stripped.startswith("#")):
            continue
        continued = stripped.endswith("\\")
        current.append(stripped[:-1].rstrip() if continued else stripped)
        if continued:
            continue
        instructions.append(" ".join(current))
        current = []
    if current:
        instructions.append(" ".join(current))
    return instructions


def _docker_stages(text: str) -> list[list[str]]:
    """Split logical Dockerfile instructions into build stages without sharing stage-local state."""
    instructions = _docker_instructions(text)
    stages: list[list[str]] = []
    current: list[str] | None = None
    for instruction in instructions:
        if _FROM_INSTRUCTION.match(instruction):
            if current is not None:
                stages.append(current)
            current = []
            continue
        if current is not None:
            current.append(instruction)
    if current is not None:
        stages.append(current)
    if not stages and instructions:
        return [instructions]
    return stages


def _container_path(value: str) -> str | None:
    """Normalize one static absolute container path, rejecting dynamic destinations."""
    if not value.startswith("/") or "$" in value:
        return None
    return posixpath.normpath(value)


def _resolved_copy_destination(value: str, workdir: str | None) -> str | None:
    """Resolve a static COPY/ADD destination without guessing an inherited base-image WORKDIR."""
    if "$" in value:
        return None
    if value.startswith("/"):
        return posixpath.normpath(value)
    if workdir is None:
        return None
    return posixpath.normpath(posixpath.join(workdir, value))


def _resolved_container_directory(value: str, current: str | None) -> str | None:
    """Resolve one simple static WORKDIR/cd path without guessing inherited or dynamic state."""
    if not value or "$" in value or any(character.isspace() for character in value):
        return None
    if value.startswith("/"):
        return posixpath.normpath(value)
    if current is None:
        return None
    return posixpath.normpath(posixpath.join(current, value))


def _parse_copy_instruction(instruction: str) -> tuple[list[str], str, bool] | None:
    """Parse one static COPY/ADD and retain all sources plus stage-copy provenance."""
    match = _COPY_INSTRUCTION.match(instruction)
    if match is None:
        return None
    payload = match.group(1).strip()
    if not payload:
        return None
    from_stage = False
    while payload.startswith("--"):
        flag, separator, remainder = payload.partition(" ")
        if not separator:
            return None
        folded = flag.casefold()
        payload = remainder.lstrip()
        if folded == "--from":
            _stage, separator, payload = payload.partition(" ")
            if not separator:
                return None
            from_stage = True
            payload = payload.lstrip()
        elif folded.startswith("--from="):
            from_stage = True
    if payload.startswith("["):
        try:
            values = json.loads(payload)
        except json.JSONDecodeError:
            return None
        if not isinstance(values, list) or len(values) < 2 or not all(isinstance(item, str) for item in values):
            return None
        return values[:-1], values[-1], from_stage
    try:
        tokens = shlex.split(payload)
    except ValueError:
        return None
    if len(tokens) < 2:
        return None
    return tokens[:-1], tokens[-1], from_stage


def _normalized_copy_source(source: str) -> str | None:
    """Return a confined lexical build-context source path suitable only for conservative provenance matching."""
    if "$" in source:
        return None
    value = source.replace("\\", "/").strip()
    while value.startswith("./"):
        value = value[2:]
    normalized = posixpath.normpath(value).lstrip("/")
    if normalized in {"", ".", ".."} or normalized.startswith("../") or "/../" in normalized:
        return None
    return normalized


def _prebuilt_source_root(source: str) -> str | None:
    """Return the case-preserving lexical build-context root that owns one copied prebuilt artifact path."""
    normalized = _normalized_copy_source(source)
    if normalized is None:
        return None
    parts = normalized.split("/")
    for index, part in enumerate(parts):
        if part.casefold() in _PREBUILT_CONTAINER_DIRS:
            return "/".join(parts[: index + 1])
    return None


def _artifact_destination(source: str, destination: str, source_root: str, workdir: str | None) -> str | None:
    """Return the container directory whose copied artifact bytes share one revision marker."""
    normalized_destination = _resolved_copy_destination(destination, workdir)
    normalized_source = _normalized_copy_source(source)
    if normalized_destination is None or normalized_source is None:
        return None
    if normalized_source == source_root or destination.endswith("/") or destination in {".", "./"}:
        return normalized_destination
    return posixpath.dirname(normalized_destination) or "/"


def _copy_target(source: str, destination: str, workdir: str | None) -> str | None:
    """Return the exact target of a simple file COPY when statically provable."""
    normalized_destination = _resolved_copy_destination(destination, workdir)
    normalized_source = _normalized_copy_source(source)
    if normalized_destination is None or normalized_source is None:
        return None
    if destination.endswith("/") or destination in {".", "./"}:
        return posixpath.join(normalized_destination, posixpath.basename(normalized_source))
    return normalized_destination


def _path_at_or_below(path: str, root: str) -> bool:
    """Return whether an absolute path is the root itself or a lexical descendant."""
    if root == "/":
        return path.startswith("/")
    return path == root or path.startswith(root.rstrip("/") + "/")


@dataclass
class _PrebuiltArtifactBinding:
    source_root: str
    destination: str
    bound: bool = False
    tainted: bool = False


def _expected_revision_paths(artifact: _PrebuiltArtifactBinding) -> set[str]:
    return {posixpath.join(artifact.destination, name) for name in _REVISION_METADATA_NAMES}


def _invalidate_revision_provenance(
    artifacts: list[_PrebuiltArtifactBinding],
    revision_provenance: dict[str, str],
) -> None:
    """Fail closed when an instruction may have changed artifact or revision provenance."""
    revision_provenance.clear()
    for artifact in artifacts:
        artifact.bound = False
        artifact.tainted = True


def _resolved_revision_read(path: str, cwd: str | None) -> str | None:
    if path.startswith("/"):
        return posixpath.normpath(path)
    if cwd is not None:
        return posixpath.normpath(posixpath.join(cwd, path))
    return None


def _source_revision_builtin_read(
    tokens: list[str],
    *,
    cwd: str | None,
    trusted_revision_paths: set[str],
) -> tuple[str, str] | None:
    """Bind one shell variable to trusted revision metadata without invoking a PATH-resolved executable."""
    if len(tokens) != 5 or tokens[0] != "read" or tokens[1] != "-r" or tokens[3] != "<":
        return None
    variable = tokens[2]
    if _SHELL_VARIABLE_NAME.fullmatch(variable) is None:
        return None
    resolved = _resolved_revision_read(tokens[4], cwd)
    if resolved not in trusted_revision_paths:
        return None
    return variable, resolved


def _shell_variable_reference(token: str) -> str | None:
    if token.startswith("${") and token.endswith("}"):
        name = token[2:-1]
    elif token.startswith("$"):
        name = token[1:]
    else:
        return None
    return name if _SHELL_VARIABLE_NAME.fullmatch(name) is not None else None


def _source_revision_variable_equality(
    tokens: list[str],
    source_arg: str,
    revision_variables: dict[str, str],
) -> str | None:
    """Return a trusted revision path when a captured shell variable equals the active source argument."""
    if not _is_simple_equality_check(tokens):
        return None
    left = tokens[1]
    right = tokens[3]
    source_references = {f"${source_arg}", f"${{{source_arg}}}"}
    for variable_token, argument_token in ((left, right), (right, left)):
        variable = _shell_variable_reference(variable_token)
        if variable is not None and argument_token in source_references:
            return revision_variables.get(variable)
    return None


def _is_simple_equality_check(tokens: list[str]) -> bool:
    """Accept only one unnegated equality predicate with no compound test operators."""
    if len(tokens) == 4 and tokens[0] == "test":
        return tokens[2] in {"=", "=="}
    if len(tokens) != 5:
        return False
    opener, _left, operator, _right, closer = tokens
    expected_closer = {"[": "]", "[[": "]]"}.get(opener)
    return expected_closer is not None and closer == expected_closer and operator in {"=", "=="}


def _source_argument_nonempty_check(tokens: list[str], eligible_args: set[str]) -> str | None:
    """Return a source argument proved non-empty by one simple build-gating predicate."""
    variable_token: str | None = None
    if len(tokens) == 3 and tokens[:2] == ["test", "-n"]:
        variable_token = tokens[2]
    elif len(tokens) == 4 and tokens[0] in {"[", "[["} and tokens[1] == "-n":
        closer = "]" if tokens[0] == "[" else "]]"
        if tokens[3] == closer:
            variable_token = tokens[2]
    if variable_token is None:
        return None
    variable = _shell_variable_reference(variable_token)
    return variable if variable in eligible_args else None


def _trusted_shell_instruction(instruction: str) -> bool:
    """Accept only an explicit stage-local POSIX shell identity with fixed invocation semantics."""
    match = _SHELL_INSTRUCTION.match(instruction)
    if match is None:
        return False
    try:
        value = json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        return False
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return False
    return tuple(value) in _TRUSTED_DOCKER_SHELLS


def _environment_assignment_names(payload: str) -> set[str] | None:
    """Return statically assigned ENV names, or None when the instruction is ambiguous."""
    try:
        tokens = shlex.split(payload)
    except ValueError:
        return None
    if not tokens:
        return None
    if "=" not in tokens[0]:
        name = tokens[0]
        return {name} if _SHELL_VARIABLE_NAME.fullmatch(name) is not None and len(tokens) >= 2 else None
    names: set[str] = set()
    for token in tokens:
        name, separator, _value = token.partition("=")
        if not separator or _SHELL_VARIABLE_NAME.fullmatch(name) is None:
            return None
        names.add(name)
    return names


def _command_preserves_revision_provenance(command: str, tokens: list[str]) -> bool:
    """Conservatively recognize shell builtins that cannot mutate copied artifact bytes or captured variables."""
    if not tokens or _OPAQUE_SHELL_EFFECT.search(command) is not None:
        return False
    command_index = 0
    while command_index < len(tokens) and _SHELL_ASSIGNMENT.fullmatch(tokens[command_index]) is not None:
        command_index += 1
    if command_index == len(tokens):
        return True
    executable = tokens[command_index]
    return "/" not in executable and executable in _REVISION_PROVENANCE_SAFE_BUILTINS


def _stage_source_revision_binding_state(
    instructions: list[str],
    revision_args: list[str],
) -> tuple[bool, bool]:
    """Evaluate prebuilt-artifact revision binding within exactly one Docker build stage."""
    candidate_args = {
        name
        for name in revision_args
        if "source" in name.casefold() and ("revision" in name.casefold() or "sha" in name.casefold())
    }
    active_args: set[str] = set()
    artifacts: list[_PrebuiltArtifactBinding] = []
    revision_provenance: dict[str, str] = {}
    prebuilt_copy = False
    workdir: str | None = None
    # A base image can carry an arbitrary Config.Shell. Static Dockerfile inspection
    # therefore accepts RUN evidence only after this stage explicitly selects a fixed shell.
    run_shell_trusted = False

    for instruction in instructions:
        argument = _ARG_INSTRUCTION.match(instruction)
        if argument is not None:
            name, default = argument.group(1), argument.group(2)
            if name in candidate_args:
                if default is None:
                    active_args.add(name)
                else:
                    active_args.discard(name)
            continue

        environment_instruction = _ENV_INSTRUCTION.match(instruction)
        if environment_instruction is not None:
            assigned = _environment_assignment_names(environment_instruction.group(1).strip())
            if assigned is None:
                active_args.clear()
            else:
                active_args.difference_update(assigned)
            continue

        workdir_instruction = _WORKDIR_INSTRUCTION.match(instruction)
        if workdir_instruction is not None:
            workdir = _resolved_container_directory(workdir_instruction.group(1).strip(), workdir)
            continue

        if _SHELL_INSTRUCTION.match(instruction) is not None:
            run_shell_trusted = _trusted_shell_instruction(instruction)
            continue

        parsed_copy = _parse_copy_instruction(instruction)
        if parsed_copy is not None:
            sources, destination, from_stage = parsed_copy
            for source in sources:
                normalized_source = _normalized_copy_source(source)
                normalized_destination = _resolved_copy_destination(destination, workdir)
                source_root = None if from_stage else _prebuilt_source_root(source)
                source_name = (
                    posixpath.basename(normalized_source).replace("-", "_").upper()
                    if normalized_source is not None
                    else ""
                )
                source_is_revision_metadata = source_name in _REVISION_METADATA_NAMES
                target = _copy_target(source, destination, workdir)
                target_name = posixpath.basename(target).replace("-", "_").upper() if target is not None else ""
                target_is_revision_metadata = target_name in _REVISION_METADATA_NAMES
                impact_path = target or normalized_destination

                if impact_path is not None:
                    for existing_artifact in artifacts:
                        if (
                            _path_at_or_below(impact_path, existing_artifact.destination)
                            and source_root != existing_artifact.source_root
                        ):
                            existing_artifact.bound = False
                            existing_artifact.tainted = True
                            for path in _expected_revision_paths(existing_artifact):
                                revision_provenance.pop(path, None)

                if target_is_revision_metadata and target is not None:
                    for existing_artifact in artifacts:
                        if target in _expected_revision_paths(existing_artifact):
                            existing_artifact.bound = False
                    if source_root is not None and source_is_revision_metadata:
                        revision_provenance[target] = source_root
                    else:
                        revision_provenance.pop(target, None)

                if source_root is None:
                    continue
                if source_is_revision_metadata:
                    continue
                prebuilt_copy = True
                artifact_destination = _artifact_destination(source, destination, source_root, workdir)
                if artifact_destination is None:
                    continue
                for existing_artifact in artifacts:
                    if (
                        existing_artifact.destination == artifact_destination
                        and existing_artifact.source_root != source_root
                    ):
                        existing_artifact.bound = False
                        existing_artifact.tainted = True
                        for path in _expected_revision_paths(existing_artifact):
                            revision_provenance.pop(path, None)
                matching_artifact = next(
                    (
                        item
                        for item in artifacts
                        if item.source_root == source_root and item.destination == artifact_destination
                    ),
                    None,
                )
                if matching_artifact is None:
                    matching_artifact = _PrebuiltArtifactBinding(
                        source_root=source_root,
                        destination=artifact_destination,
                    )
                    artifacts.append(matching_artifact)
                matching_artifact.bound = False
                if normalized_source is not None and normalized_source == source_root:
                    for name in _REVISION_METADATA_NAMES:
                        revision_provenance[posixpath.join(artifact_destination, name)] = source_root
            continue

        run = _RUN_INSTRUCTION.match(instruction)
        if run is None:
            continue
        if not run_shell_trusted:
            if artifacts:
                _invalidate_revision_provenance(artifacts, revision_provenance)
            continue
        body = run.group(1).strip()
        if _SOURCE_REVISION_WRITE.search(body) is not None:
            _invalidate_revision_provenance(artifacts, revision_provenance)
            continue
        unsafe_control_flow = bool(
            body
            and ("||" in body or ";" in body or re.search(r"(?<!\|)\|(?!\|)", body) or re.search(r"(?<!&)&(?!&)", body))
        )
        if not body or unsafe_control_flow:
            if unsafe_control_flow and artifacts:
                _invalidate_revision_provenance(artifacts, revision_provenance)
            continue
        cwd = workdir
        revision_variables: dict[str, str] = {}
        nonempty_args: set[str] = set()
        shadowed_args: set[str] = set()
        for command in re.split(r"\s*&&\s*", body):
            command = command.strip()
            if not command or command.startswith("!"):
                if command.startswith("!") and artifacts:
                    _invalidate_revision_provenance(artifacts, revision_provenance)
                    break
                continue
            try:
                tokens = shlex.split(command)
            except ValueError:
                if artifacts:
                    _invalidate_revision_provenance(artifacts, revision_provenance)
                    break
                continue

            assignment_names: list[str] = []
            for token in tokens:
                if _SHELL_ASSIGNMENT.fullmatch(token) is None:
                    break
                assignment_names.append(token.split("=", 1)[0])
            for name in assignment_names:
                revision_variables.pop(name, None)
                nonempty_args.discard(name)
                if name in active_args:
                    shadowed_args.add(name)

            simple_equality = _is_simple_equality_check(tokens)
            if revision_variables and not simple_equality:
                # A captured marker is single-use. Any intervening command may
                # rewrite shell state, including builtins such as `printf -v`.
                revision_variables.clear()

            eligible_args = active_args - shadowed_args
            nonempty = _source_argument_nonempty_check(tokens, eligible_args)
            if nonempty is not None:
                nonempty_args.add(nonempty)
                continue

            if len(tokens) == 2 and tokens[0] == "cd" and _OPAQUE_SHELL_EFFECT.search(command) is None:
                cwd = _resolved_container_directory(tokens[1], cwd)
                continue
            trusted_revision_paths = set(revision_provenance)
            captured_revision = _source_revision_builtin_read(
                tokens,
                cwd=cwd,
                trusted_revision_paths=trusted_revision_paths,
            )
            if captured_revision is not None:
                variable, captured_path = captured_revision
                revision_variables[variable] = captured_path
                continue
            if _SOURCE_REVISION_FILE.search(command) is not None and not simple_equality:
                _invalidate_revision_provenance(artifacts, revision_provenance)
                break
            bound_by_command = False
            if simple_equality:
                for name in sorted(candidate_args.intersection(eligible_args).intersection(nonempty_args)):
                    matched_path = _source_revision_variable_equality(tokens, name, revision_variables)
                    if matched_path is None:
                        continue
                    provenance = revision_provenance.get(matched_path)
                    for artifact in artifacts:
                        if (
                            not artifact.tainted
                            and provenance == artifact.source_root
                            and matched_path in _expected_revision_paths(artifact)
                        ):
                            artifact.bound = True
                            bound_by_command = True
                revision_variables.clear()
            if bound_by_command:
                continue
            if artifacts and not _command_preserves_revision_provenance(command, tokens):
                _invalidate_revision_provenance(artifacts, revision_provenance)
                break

    return prebuilt_copy, prebuilt_copy and bool(artifacts) and all(
        artifact.bound and not artifact.tainted for artifact in artifacts
    )


def _source_revision_binding_state(text: str, revision_args: list[str]) -> tuple[bool, bool]:
    """Require every Docker stage with build-context prebuilt artifacts to bind its own revision metadata."""
    states = [_stage_source_revision_binding_state(stage, revision_args) for stage in _docker_stages(text)]
    prebuilt_copy = any(prebuilt for prebuilt, _bound in states)
    source_binding = prebuilt_copy and all(not prebuilt or bound for prebuilt, bound in states)
    return prebuilt_copy, source_binding


def _source_revision_binding_signal(text: str, revision_args: list[str]) -> bool:
    """Require stage-local, provenance-bound, fail-closed revision equality for all prebuilt artifact copies."""
    return _source_revision_binding_state(text, revision_args)[1]


def _container_build_facts(root: Path) -> dict[str, bool]:
    """Require every root build definition that copies prebuilt artifacts to bind them to source."""
    texts = [text for name in ("Dockerfile", "Containerfile") if (text := _regular_text(root / name)) is not None]
    if not texts:
        return {"prebuilt_artifact_copy": False, "source_revision_binding_signal": False}
    per_definition: list[tuple[bool, bool]] = []
    for text in texts:
        revision_args = _SOURCE_REVISION_ARG.findall(text)
        prebuilt, bound = _source_revision_binding_state(text, revision_args)
        per_definition.append((prebuilt, bound))
    prebuilt_copy = any(prebuilt for prebuilt, _ in per_definition)
    source_binding = prebuilt_copy and all(not prebuilt or bound for prebuilt, bound in per_definition)
    return {
        "prebuilt_artifact_copy": prebuilt_copy,
        "source_revision_binding_signal": source_binding,
    }


def inspect_repository(repository_root: Path) -> dict[str, Any]:
    """Return bounded source-derived facts and a progressive adoption plan."""
    root = repository_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("repository root must be a directory")
    project = _pyproject(root)
    dependencies = _dependency_names(project, root)
    corpus, scanned_files, scanned_bytes = _source_corpus(root)

    if "fastmcp" in dependencies or "fastmcp-slim" in dependencies:
        sdk_profile = "python-fastmcp-package"
    elif "mcp" in dependencies:
        sdk_profile = "python-official-mcp"
    else:
        sdk_profile = "unknown"

    has_external_upstream = bool(HTTP_DEPENDENCIES.intersection(dependencies)) or any(
        marker in corpus for marker in ("requests.get(", "requests.post(", "httpx.", "aiohttp.")
    )
    has_external_tests = (root / "tests/external").is_dir() or any(
        marker in corpus for marker in ("pytest.mark.external", '"external:"', "'external:'")
    )
    external_default_excluded = _external_tests_default_excluded(project)
    upstream_contract_path = root / "upstream-contract.yaml"
    live_policy_path = root / "live-backend-test-policy.yaml"
    upstream_contract = upstream_contract_path.is_file()
    live_policy = live_policy_path.is_file()
    upstream_contract_findings = (
        validate_upstream_contract(upstream_contract_path, require_observed=True) if upstream_contract else []
    )
    live_policy_findings = validate_live_backend_policy(live_policy_path) if live_policy else []
    upstream_contract_valid = upstream_contract and not upstream_contract_findings
    live_policy_valid = live_policy and not live_policy_findings
    has_stdio = "stdio" in corpus
    has_streamable_http = any(marker in corpus for marker in ("streamable_http", "streamable-http"))
    has_legacy_sse = any(marker in corpus for marker in ("/sse", "legacy sse", "http+sse"))
    destructive_signal = any(
        marker in corpus
        for marker in (
            "operation_kind: destructive",
            'operation_kind="destructive"',
            'operation_kind = "destructive"',
            "delete_",
            "remove_",
        )
    )
    write_signal = destructive_signal or any(
        marker in corpus
        for marker in (
            "operation_kind: write",
            'operation_kind="write"',
            'operation_kind = "write"',
            "create_",
            "update_",
            "put_",
        )
    )
    containerized = any((root / name).is_file() for name in ("Dockerfile", "Containerfile"))
    container_build = _container_build_facts(root)

    facts: dict[str, Any] = {
        "language": "python" if project else "unknown",
        "sdk_profile": sdk_profile,
        "project_version": _project_version(project),
        "packaged": bool(project),
        "containerized": containerized,
        "container_build": container_build,
        "github_actions": (root / ".github/workflows").is_dir(),
        "external_upstream": has_external_upstream,
        "external_tests": has_external_tests,
        "external_tests_default_excluded": external_default_excluded,
        "upstream_contract_present": upstream_contract,
        "upstream_contract_valid": upstream_contract_valid,
        "live_backend_policy_present": live_policy,
        "live_backend_policy_valid": live_policy_valid,
        "transports": {
            "stdio": has_stdio,
            "streamable_http": has_streamable_http,
            "legacy_http_sse_signal": has_legacy_sse,
        },
        "capabilities": {
            "write_signal": write_signal,
            "destructive_signal": destructive_signal,
        },
    }

    upstream_status = "not-applicable"
    if has_external_upstream:
        if not upstream_contract:
            upstream_status = "required"
        elif upstream_contract_valid:
            upstream_status = "verified"
        else:
            upstream_status = "invalid"
    live_status = "not-applicable"
    if has_external_tests:
        if not live_policy:
            live_status = "needs-policy"
        elif live_policy_valid:
            live_status = "declared"
        else:
            live_status = "invalid"
    artifact_binding_status = "not-applicable"
    if containerized and container_build["prebuilt_artifact_copy"]:
        artifact_binding_status = "declared" if container_build["source_revision_binding_signal"] else "needs-binding"

    unknowns: list[str] = []
    if sdk_profile == "unknown":
        unknowns.append("MCP SDK package identity was not resolved from package metadata")
    if has_external_upstream and not upstream_contract:
        unknowns.append("external upstream contract is unobserved; probe the real boundary before adapter refactoring")
    elif has_external_upstream and upstream_contract_findings:
        unknowns.append(
            f"upstream contract failed trusted observed-contract validation ({len(upstream_contract_findings)} finding(s))"
        )
    if has_external_tests and not external_default_excluded:
        unknowns.append("external tests are not proven deselected by the structured default pytest addopts")
    if has_external_tests and not live_policy:
        unknowns.append("live-backend safety policy is missing")
    elif has_external_tests and live_policy_findings:
        unknowns.append(
            f"live-backend safety policy failed trusted validation ({len(live_policy_findings)} finding(s))"
        )
    if artifact_binding_status == "needs-binding":
        unknowns.append(
            "container build copies prebuilt artifacts without a source-revision binding signal; stale local artifacts may be packaged"
        )

    routes = ["STANDARD.md", "references/testing-strategy.md"]
    if sdk_profile == "python-fastmcp-package":
        routes.append("references/python-fastmcp-package.md")
    elif sdk_profile == "python-official-mcp":
        routes.append("references/python-official-mcp-sdk.md")
    if has_external_upstream:
        routes.append("references/upstream-contract-discovery.md")

    return {
        "format": "ai-skills-adoption-discovery",
        "schema_version": 1,
        "facts": facts,
        "plan": {
            "discovery": "complete",
            "upstream_contract": upstream_status,
            "live_backend_safety": live_status,
            "container_artifact_binding": artifact_binding_status,
            "implementation": "not-evaluated",
            "local_verification": "not-evaluated",
            "provider_verification": "not-evaluated",
            "acceptance": "not-evaluated",
        },
        "required_read_set": routes,
        "unknowns": unknowns,
        "scan": {"files": scanned_files, "bytes": scanned_bytes},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    document = inspect_repository(args.repository)
    serialized = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(serialized, end="")
    else:
        if os.path.lexists(args.output):
            parser.error("output already exists; refusing to overwrite")
        args.output.write_text(serialized, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
