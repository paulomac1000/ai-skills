"""Regressions promoted from the third real kontomierz-mcp deployment cycle."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills/mcp-server-architect/tools"


def _load(path: Path, name: str) -> ModuleType:
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_project(root: Path, *, addopts: str, marker_note: str = "") -> None:
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


def test_external_default_exclusion_comes_from_structured_addopts_not_incidental_text(tmp_path: Path) -> None:
    inspector = _load(TOOLS / "inspect_existing_project.py", "cycle3_inspector_pytest")
    _write_project(tmp_path, addopts="-q", marker_note="not external")

    discovery = inspector.inspect_repository(tmp_path)

    assert discovery["facts"]["external_tests"] is True
    assert discovery["facts"]["external_tests_default_excluded"] is False
    assert any("not proven deselected" in item for item in discovery["unknowns"])


def test_external_default_exclusion_accepts_conservative_not_external_marker_expression(tmp_path: Path) -> None:
    inspector = _load(TOOLS / "inspect_existing_project.py", "cycle3_inspector_pytest_excluded")
    _write_project(tmp_path, addopts='-q -m "not external and not slow"')

    discovery = inspector.inspect_repository(tmp_path)

    assert discovery["facts"]["external_tests_default_excluded"] is True
    assert not any("not proven deselected" in item for item in discovery["unknowns"])


def test_external_default_exclusion_rejects_or_expression_that_can_select_external_tests(tmp_path: Path) -> None:
    inspector = _load(TOOLS / "inspect_existing_project.py", "cycle3_inspector_pytest_or")
    _write_project(tmp_path, addopts='-m "not external or smoke"')

    discovery = inspector.inspect_repository(tmp_path)

    assert discovery["facts"]["external_tests_default_excluded"] is False


def test_prebuilt_container_without_source_binding_is_an_explicit_adoption_gap(tmp_path: Path) -> None:
    inspector = _load(TOOLS / "inspect_existing_project.py", "cycle3_inspector_container")
    _write_project(tmp_path, addopts='-m "not external"')
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12-slim\n"
        "COPY dist/ /tmp/dist/\n"
        "RUN sha256sum --check /tmp/dist/SHA256SUMS\n",
        encoding="utf-8",
    )

    discovery = inspector.inspect_repository(tmp_path)

    assert discovery["facts"]["container_build"] == {
        "prebuilt_artifact_copy": True,
        "source_revision_binding_signal": False,
    }
    assert discovery["plan"]["container_artifact_binding"] == "needs-binding"
    assert any("stale local artifacts" in item for item in discovery["unknowns"])


def test_source_bound_prebuilt_container_clears_stale_artifact_gap(tmp_path: Path) -> None:
    inspector = _load(TOOLS / "inspect_existing_project.py", "cycle3_inspector_container_bound")
    _write_project(tmp_path, addopts='-m "not external"')
    (tmp_path / "Dockerfile").write_text(
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        "RUN test -n \"$EXPECTED_SOURCE_REVISION\" && test \"$(cat /tmp/dist/SOURCE_REVISION)\" = \"$EXPECTED_SOURCE_REVISION\" && sha256sum --check /tmp/dist/SHA256SUMS\n",
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
