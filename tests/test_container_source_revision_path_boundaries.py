"""Container source-revision provenance stays fail-closed across ambiguous path boundaries."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
INSPECTOR = ROOT / "skills/mcp-server-architect/tools/inspect_existing_project.py"


def _inspector() -> ModuleType:
    spec = importlib.util.spec_from_file_location("container_source_revision_path_boundaries", INSPECTOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _binding_run() -> str:
    return (
        'SHELL ["/bin/sh", "-c"]\n'
        'RUN test -n "$EXPECTED_SOURCE_REVISION" && '
        "read -r ACTUAL_SOURCE_REVISION < /tmp/dist/SOURCE_REVISION && "
        'test "$ACTUAL_SOURCE_REVISION" = "$EXPECTED_SOURCE_REVISION"\n'
    )


def test_distinct_case_sensitive_source_roots_do_not_share_revision_provenance() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY Dist/server.whl /tmp/dist/\n"
        "COPY dist/SOURCE_REVISION /tmp/dist/SOURCE_REVISION\n"
        + _binding_run()
    )

    assert inspector._source_revision_binding_state(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    ) == (True, False)


def test_dynamic_prebuilt_destination_is_detected_but_cannot_be_claimed_bound() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG APP_HOME=/app\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ $APP_HOME/\n"
    )

    assert inspector._source_revision_binding_state(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    ) == (True, False)


def test_json_multi_source_copy_keeps_same_root_revision_binding() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        'COPY ["dist/server.whl", "dist/SOURCE_REVISION", "/tmp/dist/"]\n'
        + _binding_run()
    )

    assert inspector._source_revision_binding_state(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    ) == (True, True)


def test_destination_name_alone_does_not_make_source_prebuilt() -> None:
    inspector = _inspector()
    dockerfile = "FROM python:3.12-slim\nCOPY src/ /app/dist/\n"

    assert inspector._source_revision_binding_state(dockerfile, []) == (False, False)
