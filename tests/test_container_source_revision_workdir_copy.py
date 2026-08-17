"""Container provenance resolves relative COPY targets only from explicit stage WORKDIR."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
INSPECTOR = ROOT / "skills/mcp-server-architect/tools/inspect_existing_project.py"


def _inspector() -> ModuleType:
    spec = importlib.util.spec_from_file_location("container_source_revision_workdir_copy", INSPECTOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_relative_directory_copy_uses_explicit_stage_workdir() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "WORKDIR /app\n"
        "COPY dist/ .\n"
        'RUN test "$(cat SOURCE_REVISION)" = "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert inspector._source_revision_binding_signal(dockerfile, ["EXPECTED_SOURCE_REVISION"])


def test_relative_file_copies_use_explicit_stage_workdir() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "WORKDIR /app\n"
        "COPY dist/server.whl .\n"
        "COPY dist/SOURCE_REVISION .\n"
        'RUN test "$(cat SOURCE_REVISION)" = "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert inspector._source_revision_binding_signal(dockerfile, ["EXPECTED_SOURCE_REVISION"])


def test_relative_copy_without_explicit_workdir_remains_unresolved() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ .\n"
        'RUN test "$(cat SOURCE_REVISION)" = "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert not inspector._source_revision_binding_signal(dockerfile, ["EXPECTED_SOURCE_REVISION"])
