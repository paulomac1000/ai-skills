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


def _binding_run(
    path: str = "/tmp/dist/SOURCE_REVISION",
    predicate: str = 'test "$ACTUAL_SOURCE_REVISION" = "$EXPECTED_SOURCE_REVISION"',
    suffix: str = "",
) -> str:
    return (
        'SHELL ["/bin/sh", "-c"]\n'
        'RUN test -n "$EXPECTED_SOURCE_REVISION" && '
        f"read -r ACTUAL_SOURCE_REVISION < {path} && {predicate}{suffix}\n"
    )


def test_existence_and_nonempty_checks_in_one_command_do_not_bind_revision() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'SHELL ["/bin/sh", "-c"]\n'
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
        + _binding_run()
    )

    assert inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_inherited_base_shell_cannot_establish_source_binding() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'RUN test -n "$EXPECTED_SOURCE_REVISION" && '
        "read -r ACTUAL_SOURCE_REVISION < /tmp/dist/SOURCE_REVISION && "
        'test "$ACTUAL_SOURCE_REVISION" = "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert not inspector._source_revision_binding_signal(dockerfile, ["EXPECTED_SOURCE_REVISION"])


def test_revision_file_can_be_read_relative_to_copied_artifact_directory() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'SHELL ["/bin/sh", "-c"]\n'
        'RUN test -n "$EXPECTED_SOURCE_REVISION" && cd /tmp/dist && '
        "read -r ACTUAL_SOURCE_REVISION < SOURCE_REVISION && "
        'test "$ACTUAL_SOURCE_REVISION" = "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_revision_file_can_be_read_relative_to_stage_workdir() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        "WORKDIR /tmp/dist\n"
        + _binding_run("SOURCE_REVISION")
    )

    assert inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_dynamic_stage_workdir_does_not_guess_revision_location() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "ARG ARTIFACT_DIR\n"
        "COPY dist/ /tmp/dist/\n"
        "WORKDIR $ARTIFACT_DIR\n"
        + _binding_run("SOURCE_REVISION")
    )

    assert not inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_inequality_does_not_count_as_source_binding() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        + _binding_run(predicate='test "$ACTUAL_SOURCE_REVISION" != "$EXPECTED_SOURCE_REVISION"')
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
        + _binding_run("/tmp/SOURCE_REVISION")
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
        + _binding_run()
    )

    assert not inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_unrelated_copy_cannot_supply_artifact_revision_metadata() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/server.whl /tmp/dist/\n"
        "COPY metadata/SOURCE_REVISION /tmp/dist/SOURCE_REVISION\n"
        + _binding_run()
    )

    assert not inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_renamed_unrelated_file_cannot_supply_artifact_revision_metadata() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        "COPY metadata/revision.txt /tmp/dist/SOURCE_REVISION\n"
        + _binding_run()
    )

    assert not inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_renamed_file_from_same_prebuilt_root_is_not_revision_metadata() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/server.whl /tmp/dist/\n"
        "COPY dist/revision.txt /tmp/dist/SOURCE_REVISION\n"
        + _binding_run()
    )

    assert not inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_unrelated_copy_over_artifact_bytes_taints_source_binding() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        "COPY metadata/server.whl /tmp/dist/server.whl\n"
        + _binding_run()
    )

    assert not inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_matching_prebuilt_copy_can_supply_artifact_revision_metadata() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/server.whl /tmp/dist/\n"
        "COPY dist/SOURCE_REVISION /tmp/dist/SOURCE_REVISION\n"
        + _binding_run()
    )

    assert inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_multiple_copy_sources_are_all_inspected_for_prebuilt_binding() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/server.whl dist/SOURCE_REVISION /tmp/dist/\n"
        + _binding_run()
    )

    assert inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_bound_earlier_stage_does_not_bind_later_prebuilt_copy() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim AS verified\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        + _binding_run()
        + "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY build/ /app/\n"
    )

    assert not inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_stage_copy_does_not_create_a_second_build_context_prebuilt_requirement() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim AS verified\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        + _binding_run()
        + "FROM python:3.12-slim\n"
        "COPY --from=verified /tmp/dist/ /app/\n"
    )

    assert inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_revision_argument_must_be_declared_in_the_prebuilt_stage() -> None:
    inspector = _inspector()
    dockerfile = (
        "ARG EXPECTED_SOURCE_REVISION\n"
        "FROM python:3.12-slim\n"
        "COPY dist/ /tmp/dist/\n"
        + _binding_run()
    )

    assert not inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_defaulted_revision_argument_cannot_establish_external_binding() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION=stale\n"
        "COPY dist/ /tmp/dist/\n"
        + _binding_run()
    )

    assert not inspector._source_revision_binding_signal(dockerfile, ["EXPECTED_SOURCE_REVISION"])


def test_env_shadowed_revision_argument_cannot_establish_binding() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "ENV EXPECTED_SOURCE_REVISION=stale\n"
        "COPY dist/ /tmp/dist/\n"
        + _binding_run()
    )

    assert not inspector._source_revision_binding_signal(dockerfile, ["EXPECTED_SOURCE_REVISION"])


def test_run_shadowed_revision_argument_cannot_establish_binding() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'SHELL ["/bin/sh", "-c"]\n'
        'RUN EXPECTED_SOURCE_REVISION=stale && test -n "$EXPECTED_SOURCE_REVISION" && '
        "read -r ACTUAL_SOURCE_REVISION < /tmp/dist/SOURCE_REVISION && "
        'test "$ACTUAL_SOURCE_REVISION" = "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert not inspector._source_revision_binding_signal(dockerfile, ["EXPECTED_SOURCE_REVISION"])


def test_revision_comparison_requires_explicit_nonempty_argument_guard() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'SHELL ["/bin/sh", "-c"]\n'
        "RUN read -r ACTUAL_SOURCE_REVISION < /tmp/dist/SOURCE_REVISION && "
        'test "$ACTUAL_SOURCE_REVISION" = "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert not inspector._source_revision_binding_signal(dockerfile, ["EXPECTED_SOURCE_REVISION"])


def test_neutralized_revision_comparison_does_not_gate_build() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        + _binding_run(suffix=" || true")
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
        + _binding_run(suffix="; echo done")
    )

    assert not inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_backgrounded_revision_comparison_does_not_gate_build() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        + _binding_run(suffix=" & echo done")
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
        + _binding_run(predicate='test ! "$ACTUAL_SOURCE_REVISION" = "$EXPECTED_SOURCE_REVISION"')
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
        + _binding_run(predicate='test "$ACTUAL_SOURCE_REVISION" = "$EXPECTED_SOURCE_REVISION" -o 1 = 1')
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
        + _binding_run(predicate='[ ! "$ACTUAL_SOURCE_REVISION" = "$EXPECTED_SOURCE_REVISION" ]')
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
        + _binding_run(suffix=" && echo done")
    )

    assert inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_path_resolved_cat_cannot_bootstrap_source_binding() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        "ENV PATH=/tmp/dist:$PATH\n"
        'SHELL ["/bin/sh", "-c"]\n'
        'RUN test -n "$EXPECTED_SOURCE_REVISION" && '
        'test "$(cat /tmp/dist/SOURCE_REVISION)" = "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert not inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_captured_revision_variable_cannot_be_overwritten_before_comparison() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'SHELL ["/bin/sh", "-c"]\n'
        'RUN test -n "$EXPECTED_SOURCE_REVISION" && '
        "read -r ACTUAL_SOURCE_REVISION < /tmp/dist/SOURCE_REVISION && "
        'ACTUAL_SOURCE_REVISION="$EXPECTED_SOURCE_REVISION" && '
        'test "$ACTUAL_SOURCE_REVISION" = "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert not inspector._source_revision_binding_signal(
        dockerfile,
        ["EXPECTED_SOURCE_REVISION"],
    )


def test_captured_revision_variable_is_single_use_across_intervening_builtins() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'SHELL ["/bin/sh", "-c"]\n'
        'RUN test -n "$EXPECTED_SOURCE_REVISION" && '
        "read -r ACTUAL_SOURCE_REVISION < /tmp/dist/SOURCE_REVISION && "
        'printf -v ACTUAL_SOURCE_REVISION "%s" "$EXPECTED_SOURCE_REVISION" && '
        'test "$ACTUAL_SOURCE_REVISION" = "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert not inspector._source_revision_binding_signal(dockerfile, ["EXPECTED_SOURCE_REVISION"])
