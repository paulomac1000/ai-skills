"""Revision provenance must fail closed when RUN may mutate copied metadata."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
INSPECTOR = ROOT / "skills/mcp-server-architect/tools/inspect_existing_project.py"


def _inspector() -> ModuleType:
    spec = importlib.util.spec_from_file_location("container_source_revision_run_mutation", INSPECTOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _binding_run() -> str:
    return (
        'RUN test -n "$EXPECTED_SOURCE_REVISION" && '
        "read -r ACTUAL_SOURCE_REVISION < /tmp/dist/SOURCE_REVISION && "
        'test "$ACTUAL_SOURCE_REVISION" = "$EXPECTED_SOURCE_REVISION"\n'
    )


def test_sed_rewrite_of_copied_revision_metadata_cannot_bootstrap_binding() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'SHELL ["/bin/sh", "-c"]\n'
        'RUN sed -i "s/.*/$EXPECTED_SOURCE_REVISION/" /tmp/dist/SOURCE_REVISION\n'
        + _binding_run()
    )

    assert inspector._source_revision_binding_state(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    ) == (True, False)


def test_inline_revision_rewrite_before_equality_cannot_bootstrap_binding() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'SHELL ["/bin/sh", "-c"]\n'
        'RUN test -n "$EXPECTED_SOURCE_REVISION" && '
        'sed -i "s/.*/$EXPECTED_SOURCE_REVISION/" /tmp/dist/SOURCE_REVISION && '
        'read -r ACTUAL_SOURCE_REVISION < /tmp/dist/SOURCE_REVISION && '
        'test "$ACTUAL_SOURCE_REVISION" = "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert inspector._source_revision_binding_state(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    ) == (True, False)


def test_compound_revision_rewrite_cannot_be_skipped_before_invalidation() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'SHELL ["/bin/sh", "-c"]\n'
        'RUN sed -i "s/.*/$EXPECTED_SOURCE_REVISION/" /tmp/dist/SOURCE_REVISION; echo done\n'
        + _binding_run()
    )

    assert inspector._source_revision_binding_state(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    ) == (True, False)


def test_dynamic_revision_path_rewrite_cannot_bootstrap_binding() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'SHELL ["/bin/sh", "-c"]\n'
        'RUN p=/tmp/dist/SOURCE_ && p=${p}REVISION && '
        'sed -i "s/.*/$EXPECTED_SOURCE_REVISION/" "$p"\n'
        + _binding_run()
    )

    assert inspector._source_revision_binding_state(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    ) == (True, False)


def test_artifact_supplied_safe_basename_executable_taints_provenance() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'SHELL ["/bin/sh", "-c"]\n'
        "RUN /tmp/dist/cat\n"
        + _binding_run()
    )

    assert inspector._source_revision_binding_state(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    ) == (True, False)
