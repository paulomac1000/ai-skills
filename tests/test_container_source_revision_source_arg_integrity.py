"""Source-revision binding must preserve the externally supplied build argument."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
INSPECTOR = ROOT / "skills/mcp-server-architect/tools/inspect_existing_project.py"


def _inspector() -> ModuleType:
    spec = importlib.util.spec_from_file_location("container_source_revision_source_arg_integrity", INSPECTOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_revision_marker_read_cannot_replace_source_argument_before_nonempty_guard() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'SHELL ["/bin/sh", "-c"]\n'
        "RUN read -r EXPECTED_SOURCE_REVISION < /tmp/dist/SOURCE_REVISION && "
        'test -n "$EXPECTED_SOURCE_REVISION" && '
        "read -r ACTUAL_SOURCE_REVISION < /tmp/dist/SOURCE_REVISION && "
        'test "$ACTUAL_SOURCE_REVISION" = "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert not inspector._source_revision_binding_signal(dockerfile, ["EXPECTED_SOURCE_REVISION"])


def test_revision_marker_read_cannot_replace_source_argument_after_nonempty_guard() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'SHELL ["/bin/sh", "-c"]\n'
        'RUN test -n "$EXPECTED_SOURCE_REVISION" && '
        "read -r EXPECTED_SOURCE_REVISION < /tmp/dist/SOURCE_REVISION && "
        "read -r ACTUAL_SOURCE_REVISION < /tmp/dist/SOURCE_REVISION && "
        'test "$ACTUAL_SOURCE_REVISION" = "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert not inspector._source_revision_binding_signal(dockerfile, ["EXPECTED_SOURCE_REVISION"])
