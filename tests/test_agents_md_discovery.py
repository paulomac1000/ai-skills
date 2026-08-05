"""Behavior and safety contracts for static repository discovery."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills/agents-md-architect/tools"
sys.path.insert(0, str(TOOLS))

import discover_repository as discovery  # noqa: E402


def test_discovers_python_ci_tasks_and_nested_instructions_deterministically(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='example'\n", encoding="utf-8")
    (tmp_path / "Makefile").write_text("test:\n\tpython -m pytest\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("# AGENTS.md\n", encoding="utf-8")
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/ci.yml").write_text("name: CI\n", encoding="utf-8")
    (tmp_path / "packages/api").mkdir(parents=True)
    (tmp_path / "packages/api/AGENTS.md").write_text("# Local instructions\n", encoding="utf-8")
    (tmp_path / "packages/api/service.py").write_text("VALUE = 1\n", encoding="utf-8")

    first = discovery.discover(tmp_path)
    second = discovery.discover(tmp_path)

    assert first == second
    assert first.ecosystems == ("python",)
    assert first.manifests == ("pyproject.toml",)
    assert first.ci_files == (".github/workflows/ci.yml",)
    assert first.task_runners == ("Makefile",)
    assert first.agent_files == ("AGENTS.md", "packages/api/AGENTS.md")
    assert "nested-agent-instructions" in first.monorepo_signals


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({"Example.sln": "", "src/App/App.csproj": "<Project />"}, "dotnet"),
        ({"package.json": "{}", "src/index.ts": "export {};"}, "node"),
        ({"go.mod": "module example", "main.go": "package main"}, "go"),
        ({"Cargo.toml": "[package]", "src/main.rs": "fn main() {}"}, "rust"),
    ],
)
def test_detects_supported_ecosystems(tmp_path: Path, files: dict[str, str], expected: str) -> None:
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    assert expected in discovery.discover(tmp_path).ecosystems


def test_empty_and_documentation_only_repositories_are_safe(tmp_path: Path) -> None:
    assert discovery.discover(tmp_path).empty is True
    (tmp_path / "README.md").write_text("# Historical example\n", encoding="utf-8")
    result = discovery.discover(tmp_path)
    assert result.empty is False
    assert result.ecosystems == ("documentation",)
    assert result.documentation == ("README.md",)


def test_ignored_directories_do_not_pollute_discovery(tmp_path: Path) -> None:
    (tmp_path / ".venv/lib").mkdir(parents=True)
    (tmp_path / ".venv/lib/hidden.py").write_text("raise RuntimeError\n", encoding="utf-8")
    (tmp_path / "node_modules/example").mkdir(parents=True)
    (tmp_path / "node_modules/example/package.json").write_text("{}", encoding="utf-8")
    result = discovery.discover(tmp_path)
    assert result.files == ()
    assert result.ecosystems == ()


@pytest.mark.skipif(os.name == "nt", reason="symlink creation may require elevated privileges on Windows")
def test_symlinked_directories_and_files_are_recorded_but_never_followed(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "package.json").write_text("{}", encoding="utf-8")
    (outside / "AGENTS.md").write_text("# Outside\n", encoding="utf-8")
    (tmp_path / "linked-directory").symlink_to(outside, target_is_directory=True)
    (tmp_path / "linked-agents.md").symlink_to(outside / "AGENTS.md")

    result = discovery.discover(tmp_path)

    assert result.files == ()
    assert result.ecosystems == ()
    assert result.symlinks == ("linked-agents.md", "linked-directory")


@pytest.mark.skipif(os.name == "nt", reason="symlink creation may require elevated privileges on Windows")
def test_symlinked_repository_root_is_rejected(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    link = tmp_path / "repository-link"
    link.symlink_to(repository, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink component"):
        discovery.discover(link)


def test_cli_json_is_stable_and_machine_readable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "README.md").write_text("# Docs\n", encoding="utf-8")
    assert discovery.main([str(tmp_path), "--format", "json"]) == 0
    output = capsys.readouterr().out
    assert '"ecosystems": [' in output
    assert '"documentation"' in output
