"""Regressions promoted from a third real MCP deployment cycle."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
TOOLS = ROOT / "skills/mcp-server-architect/tools"


def _load(path: Path, name: str) -> ModuleType:
    for search_root in (CONTRACTS, path.parent):
        if str(search_root) not in sys.path:
            sys.path.insert(0, str(search_root))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_project(root: Path, *, addopts: str | None = None) -> None:
    pytest_block = ""
    if addopts is not None:
        escaped = addopts.replace('"', '\\"')
        pytest_block = f'\n[tool.pytest.ini_options]\naddopts = "{escaped}"\n'
    (root / "pyproject.toml").write_text(
        '[project]\nname = "consumer"\nversion = "0.1.0"\ndependencies = ["mcp==2.0.0", "requests==2.34.2"]\n'
        + pytest_block,
        encoding="utf-8",
    )
    package = root / "src/consumer"
    package.mkdir(parents=True)
    (package / "server.py").write_text(
        "import requests\n\ndef fetch():\n    return requests.get('https://upstream.invalid')\n",
        encoding="utf-8",
    )


def _write_marker_project(root: Path, *, addopts: str, marker_note: str = "") -> None:
    (root / "tests/external").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        "[project]\n"
        "name = \"consumer\"\n"
        "version = \"1.0.0\"\n"
        "dependencies = [\"mcp==2.0.0\"]\n\n"
        "[tool.pytest.ini_options]\n"
        f"addopts = {addopts!r}\n"
        "markers = [\"external: live backend tests; not external means safe synthetic tests\"]\n"
        f"# {marker_note}\n",
        encoding="utf-8",
    )


def _upstream_contract(*, confidence: str = "observed") -> dict[str, object]:
    return {
        "schema_version": 1,
        "upstream": {"name": "fixture-upstream", "classification": "documented"},
        "observations": [
            {
                "operation": "fetch",
                "method": "GET",
                "endpoint": "/items",
                "request_encoding": "none",
                "required_fields": [],
                "success_statuses": [200],
                "response_body": "json",
                "credential_placement": "header",
                "confidence": confidence,
                "evidence": ["fixture-live-probe"],
            }
        ],
    }


def _write_observed_contract(root: Path) -> None:
    (root / "upstream-contract.yaml").write_text(
        yaml.safe_dump(_upstream_contract(), sort_keys=False),
        encoding="utf-8",
    )


def _live_policy() -> dict[str, object]:
    return {
        "schema_version": 1,
        "default_execution": "excluded",
        "mutations": {
            "enabled_by_default": False,
            "independent_opt_ins": 2,
            "credential_access": "after-opt-in",
            "unique_namespace": True,
            "target_identity": {
                "verified_before_mutation": True,
                "exclusive_disposable_environment": True,
                "proof": "known disposable sandbox identity",
            },
            "cleanup": {
                "capture_created_ids": True,
                "reconcile_by_marker": True,
                "report_unreconciled": True,
                "preclean_after_target_verification": True,
                "strategies": ["captured-id", "unique-namespace"],
            },
        },
    }


def _write_live_policy(root: Path) -> None:
    (root / "live-backend-test-policy.yaml").write_text(
        yaml.safe_dump(_live_policy(), sort_keys=False),
        encoding="utf-8",
    )


def test_discovery_requires_observed_upstream_contract(tmp_path: Path) -> None:
    inspector = _load(TOOLS / "inspect_existing_project.py", "cycle3_inspector_contract")
    _write_project(tmp_path, addopts='-m "not external"')
    (tmp_path / "upstream-contract.yaml").write_text(
        yaml.safe_dump(_upstream_contract(confidence="inferred"), sort_keys=False),
        encoding="utf-8",
    )

    discovery = inspector.inspect_repository(tmp_path)

    assert discovery["facts"]["upstream_contract_present"] is True
    assert discovery["facts"]["upstream_contract_valid"] is False
    assert discovery["plan"]["upstream_contract"] == "invalid"
    assert any("observed-contract validation" in item for item in discovery["unknowns"])


def test_discovery_validates_live_backend_policy_before_declaring_it(tmp_path: Path) -> None:
    inspector = _load(TOOLS / "inspect_existing_project.py", "cycle3_inspector_live_policy")
    _write_project(tmp_path, addopts='-m "not external"')
    external = tmp_path / "tests/external"
    external.mkdir(parents=True)
    (external / "test_live.py").write_text("def test_live(): pass\n", encoding="utf-8")
    _write_observed_contract(tmp_path)
    unsafe = _live_policy()
    unsafe["default_execution"] = "included"
    (tmp_path / "live-backend-test-policy.yaml").write_text(
        yaml.safe_dump(unsafe, sort_keys=False),
        encoding="utf-8",
    )

    discovery = inspector.inspect_repository(tmp_path)

    assert discovery["facts"]["live_backend_policy_present"] is True
    assert discovery["facts"]["live_backend_policy_valid"] is False
    assert discovery["plan"]["live_backend_safety"] == "invalid"
    assert any("live-backend safety policy failed" in item for item in discovery["unknowns"])


def test_prebuilt_container_without_source_binding_is_reported(tmp_path: Path) -> None:
    inspector = _load(TOOLS / "inspect_existing_project.py", "cycle3_inspector_container_reported")
    _write_project(tmp_path, addopts='-m "not external"')
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12-slim\nCOPY dist/ /tmp/dist/\nRUN pip install /tmp/dist/*.whl\n",
        encoding="utf-8",
    )

    discovery = inspector.inspect_repository(tmp_path)

    assert discovery["facts"]["container_build"] == {
        "prebuilt_artifact_copy": True,
        "source_revision_binding_signal": False,
    }
    assert discovery["plan"]["container_artifact_binding"] == "needs-binding"


def test_source_bound_prebuilt_container_clears_stale_artifact_gap(tmp_path: Path) -> None:
    inspector = _load(TOOLS / "inspect_existing_project.py", "cycle3_inspector_container_bound")
    _write_project(tmp_path, addopts='-m "not external"')
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'SHELL ["/bin/sh", "-c"]\n'
        "RUN test -n \"$EXPECTED_SOURCE_REVISION\" && "
        "read -r ACTUAL_SOURCE_REVISION < /tmp/dist/SOURCE_REVISION && "
        "test \"$ACTUAL_SOURCE_REVISION\" = \"$EXPECTED_SOURCE_REVISION\"\n",
        encoding="utf-8",
    )

    discovery = inspector.inspect_repository(tmp_path)

    assert discovery["facts"]["container_build"]["source_revision_binding_signal"] is True
    assert discovery["plan"]["container_artifact_binding"] == "declared"
    assert not any("stale local artifacts" in item for item in discovery["unknowns"])


def test_adoption_plan_surfaces_prebuilt_container_source_binding_action(tmp_path: Path) -> None:
    _write_project(tmp_path, addopts='-m "not external"')
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12-slim\nCOPY dist/ /tmp/dist/\nRUN sha256sum --check /tmp/dist/SHA256SUMS\n",
        encoding="utf-8",
    )
    planner = _load(TOOLS / "plan_existing_project.py", "cycle3_planner")

    plan = planner.build_plan(tmp_path)

    assert any("fail closed when local artifacts are stale" in item for item in plan["next_actions"])


def test_hardened_discovery_accepts_observed_contract_and_valid_live_policy(tmp_path: Path) -> None:
    inspector = _load(TOOLS / "inspect_existing_project.py", "cycle3_inspector_happy")
    _write_project(tmp_path, addopts='-m "not external"')
    external = tmp_path / "tests/external"
    external.mkdir(parents=True)
    (external / "test_live.py").write_text("import pytest\npytestmark = pytest.mark.external\n", encoding="utf-8")
    _write_observed_contract(tmp_path)
    _write_live_policy(tmp_path)

    discovery = inspector.inspect_repository(tmp_path)

    assert discovery["plan"]["upstream_contract"] == "verified"
    assert discovery["plan"]["live_backend_safety"] == "declared"
    assert discovery["facts"]["external_tests_default_excluded"] is True


def test_malformed_pytest_addopts_does_not_crash_discovery(tmp_path: Path) -> None:
    inspector = _load(TOOLS / "inspect_existing_project.py", "cycle3_inspector_bad_addopts")
    _write_project(tmp_path, addopts='-m "not external')

    discovery = inspector.inspect_repository(tmp_path)

    assert discovery["facts"]["external_tests_default_excluded"] is False


@pytest.mark.parametrize(
    "expression",
    ["not external", "smoke and not external", "not external and smoke"],
)
def test_marker_parser_accepts_conjunctive_external_exclusion(expression: str) -> None:
    inspector = _load(TOOLS / "inspect_existing_project.py", f"cycle3_marker_{expression}")

    assert inspector._marker_expression_excludes_external(expression) is True


@pytest.mark.parametrize(
    "expression",
    ["not external or smoke", "smoke or not external", "external or smoke"],
)
def test_marker_parser_rejects_disjunctive_marker_expressions(expression: str) -> None:
    inspector = _load(TOOLS / "inspect_existing_project.py", f"cycle3_marker_reject_{expression}")

    assert inspector._marker_expression_excludes_external(expression) is False


def test_external_default_exclusion_comes_from_structured_addopts_not_incidental_text(tmp_path: Path) -> None:
    inspector = _load(TOOLS / "inspect_existing_project.py", "cycle3_inspector_pytest")
    _write_marker_project(tmp_path, addopts="-q", marker_note="not external")

    discovery = inspector.inspect_repository(tmp_path)

    assert discovery["facts"]["external_tests"] is True
    assert discovery["facts"]["external_tests_default_excluded"] is False
    assert any("not proven deselected" in item for item in discovery["unknowns"])


def test_external_default_exclusion_accepts_conservative_not_external_marker_expression(tmp_path: Path) -> None:
    inspector = _load(TOOLS / "inspect_existing_project.py", "cycle3_inspector_pytest_excluded")
    _write_marker_project(tmp_path, addopts='-q -m "not external and not slow"')

    discovery = inspector.inspect_repository(tmp_path)

    assert discovery["facts"]["external_tests_default_excluded"] is True
    assert not any("not proven deselected" in item for item in discovery["unknowns"])


def test_external_default_exclusion_rejects_or_expression_that_can_select_external_tests(tmp_path: Path) -> None:
    inspector = _load(TOOLS / "inspect_existing_project.py", "cycle3_inspector_pytest_or")
    _write_marker_project(tmp_path, addopts='-m "not external or smoke"')

    discovery = inspector.inspect_repository(tmp_path)

    assert discovery["facts"]["external_tests_default_excluded"] is False


def test_prebuilt_container_without_source_binding_is_an_explicit_adoption_gap(tmp_path: Path) -> None:
    inspector = _load(TOOLS / "inspect_existing_project.py", "cycle3_inspector_container")
    _write_marker_project(tmp_path, addopts='-m "not external"')
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12-slim\nCOPY dist/ /tmp/dist/\nRUN sha256sum --check /tmp/dist/SHA256SUMS\n",
        encoding="utf-8",
    )

    discovery = inspector.inspect_repository(tmp_path)

    assert discovery["facts"]["container_build"] == {
        "prebuilt_artifact_copy": True,
        "source_revision_binding_signal": False,
    }
    assert discovery["plan"]["container_artifact_binding"] == "needs-binding"
    assert any("stale local artifacts" in item for item in discovery["unknowns"])


def test_unrelated_source_revision_checks_do_not_fake_container_binding(tmp_path: Path) -> None:
    inspector = _load(TOOLS / "inspect_existing_project.py", "cycle3_inspector_container_decoupled")
    _write_marker_project(tmp_path, addopts='-m "not external"')
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        "RUN test -f /tmp/dist/SOURCE_REVISION\n"
        "RUN test -n \"$EXPECTED_SOURCE_REVISION\"\n"
        "RUN sha256sum --check /tmp/dist/SHA256SUMS\n",
        encoding="utf-8",
    )

    discovery = inspector.inspect_repository(tmp_path)

    assert discovery["facts"]["container_build"] == {
        "prebuilt_artifact_copy": True,
        "source_revision_binding_signal": False,
    }
    assert discovery["plan"]["container_artifact_binding"] == "needs-binding"


def test_source_binding_does_not_transfer_between_container_definitions(tmp_path: Path) -> None:
    inspector = _load(TOOLS / "inspect_existing_project.py", "cycle3_inspector_container_split")
    _write_marker_project(tmp_path, addopts='-m "not external"')
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12-slim\nCOPY dist/ /tmp/dist/\nRUN sha256sum --check /tmp/dist/SHA256SUMS\n",
        encoding="utf-8",
    )
    (tmp_path / "Containerfile").write_text(
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY src/ /tmp/src/\n"
        "RUN test \"$(cat /tmp/src/SOURCE_REVISION)\" = \"$EXPECTED_SOURCE_REVISION\"\n",
        encoding="utf-8",
    )

    discovery = inspector.inspect_repository(tmp_path)

    assert discovery["facts"]["container_build"] == {
        "prebuilt_artifact_copy": True,
        "source_revision_binding_signal": False,
    }
    assert discovery["plan"]["container_artifact_binding"] == "needs-binding"


def test_invalid_upstream_contract_is_not_marked_verified(tmp_path: Path) -> None:
    inspector = _load(TOOLS / "inspect_existing_project.py", "cycle3_inspector_upstream_contract")
    _write_marker_project(tmp_path, addopts='-m "not external"')
    (tmp_path / "client.py").write_text("result = httpx.get(url)\n", encoding="utf-8")
    (tmp_path / "upstream-contract.yaml").write_text("not: [valid", encoding="utf-8")

    discovery = inspector.inspect_repository(tmp_path)
    planner = _load(TOOLS / "plan_existing_project.py", "cycle3_planner_upstream_contract")
    plan = planner.build_plan(tmp_path)

    assert discovery["facts"]["external_upstream"] is True
    assert discovery["facts"]["upstream_contract_present"] is True
    assert discovery["facts"]["upstream_contract_valid"] is False
    assert discovery["plan"]["upstream_contract"] == "invalid"
    assert any("failed trusted observed-contract validation" in item for item in discovery["unknowns"])
    assert any("repair upstream-contract.yaml" in item for item in plan["next_actions"])


def test_invalid_live_policy_is_not_marked_declared(tmp_path: Path) -> None:
    inspector = _load(TOOLS / "inspect_existing_project.py", "cycle3_inspector_live_policy_invalid_yaml")
    _write_marker_project(tmp_path, addopts='-m "not external"')
    (tmp_path / "live-backend-test-policy.yaml").write_text("not: [valid", encoding="utf-8")

    discovery = inspector.inspect_repository(tmp_path)
    planner = _load(TOOLS / "plan_existing_project.py", "cycle3_planner_live_policy")
    plan = planner.build_plan(tmp_path)

    assert discovery["facts"]["external_tests"] is True
    assert discovery["facts"]["live_backend_policy_present"] is True
    assert discovery["facts"]["live_backend_policy_valid"] is False
    assert discovery["plan"]["live_backend_safety"] == "invalid"
    assert any("failed trusted validation" in item for item in discovery["unknowns"])
    assert any("repair live-backend-test-policy.yaml" in item for item in plan["next_actions"])
