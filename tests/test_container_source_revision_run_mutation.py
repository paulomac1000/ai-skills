"""Revision provenance must fail closed when RUN explicitly touches copied metadata."""

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


def test_sed_rewrite_of_copied_revision_metadata_cannot_bootstrap_binding() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'RUN sed -i "s/.*/$EXPECTED_SOURCE_REVISION/" /tmp/dist/SOURCE_REVISION\n'
        'RUN test "$(cat /tmp/dist/SOURCE_REVISION)" = "$EXPECTED_SOURCE_REVISION"\n'
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
        'RUN sed -i "s/.*/$EXPECTED_SOURCE_REVISION/" /tmp/dist/SOURCE_REVISION && '
        'test "$(cat /tmp/dist/SOURCE_REVISION)" = "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert inspector._source_revision_binding_state(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    ) == (True, False)
