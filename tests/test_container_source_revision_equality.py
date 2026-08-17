"""Prebuilt container source binding requires a fail-closed artifact-bound equality comparison."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
INSPECTOR = ROOT / "skills/mcp-server-architect/tools/inspect_existing_project.py"


def _inspector() -> ModuleType:
    spec = importlib.util.spec_from_file_location("container_source_revision_equality", INSPECTOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_existence_and_nonempty_checks_in_one_command_do_not_bind_revision() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'RUN test -f /tmp/dist/SOURCE_REVISION -a -n "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert not inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_revision_file_contents_must_equal_expected_build_argument() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'RUN test "$(cat /tmp/dist/SOURCE_REVISION)" = "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_revision_file_can_be_read_relative_to_copied_artifact_directory() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'RUN cd /tmp/dist && sha256sum --check SHA256SUMS && test "$(cat SOURCE_REVISION)" = "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_inequality_does_not_count_as_source_binding() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'RUN test "$(cat /tmp/dist/SOURCE_REVISION)" != "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert not inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_unrelated_revision_file_does_not_bind_copied_artifact() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /app/artifact/\n"
        'RUN echo "$EXPECTED_SOURCE_REVISION" > /tmp/SOURCE_REVISION\n'
        'RUN test "$(cat /tmp/SOURCE_REVISION)" = "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert not inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_overwriting_copied_revision_file_does_not_count_as_binding() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'RUN echo "$EXPECTED_SOURCE_REVISION" > /tmp/dist/SOURCE_REVISION\n'
        'RUN test "$(cat /tmp/dist/SOURCE_REVISION)" = "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert not inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_neutralized_revision_comparison_does_not_gate_build() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'RUN test "$(cat /tmp/dist/SOURCE_REVISION)" = "$EXPECTED_SOURCE_REVISION" || true\n'
    )

    assert not inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_semicolon_after_revision_comparison_does_not_gate_build() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'RUN test "$(cat /tmp/dist/SOURCE_REVISION)" = "$EXPECTED_SOURCE_REVISION"; echo done\n'
    )

    assert not inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_negated_equality_does_not_count_as_source_binding() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'RUN test ! "$(cat /tmp/dist/SOURCE_REVISION)" = "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert not inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_compound_or_predicate_does_not_count_as_source_binding() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'RUN test "$(cat /tmp/dist/SOURCE_REVISION)" = "$EXPECTED_SOURCE_REVISION" -o 1 = 1\n'
    )

    assert not inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_bracket_negation_does_not_count_as_source_binding() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'RUN [ ! "$(cat /tmp/dist/SOURCE_REVISION)" = "$EXPECTED_SOURCE_REVISION" ]\n'
    )

    assert not inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_and_chain_after_revision_comparison_remains_fail_closed() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'RUN test "$(cat /tmp/dist/SOURCE_REVISION)" = "$EXPECTED_SOURCE_REVISION" && echo done\n'
    )

    assert inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )
