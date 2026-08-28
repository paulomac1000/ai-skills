from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills/readme-architect"


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_collector_uses_non_secret_repository_evidence(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "sample"\nversion = "1.2.3"\nrequires-python = ">=3.12"\n',
        encoding="utf-8",
    )
    (tmp_path / ".env.example").write_text(
        "API_TOKEN=super-secret-placeholder\nMCP_PORT=8000\n",
        encoding="utf-8",
    )
    (tmp_path / "server.py").write_text('server = FastMCP("sample")\n', encoding="utf-8")
    collector = _load_module("collector", SKILL_ROOT / "tools/collect_readme_evidence.py")

    report = collector.build_report(tmp_path)

    assert report["manifests"]["pyproject.toml"]["name"] == "sample"
    assert report["environment_examples"][".env.example"] == ["API_TOKEN", "MCP_PORT"]
    rendered = json.dumps(report)
    assert "super-secret-placeholder" not in rendered
    assert report["registry_and_server_hints"] == [{"path": "server.py", "markers": ["FastMCP"]}]


def test_auditor_accepts_a_minimal_server_readme(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Example server\n\nA small service.\n\n"
        "## Quick start\n\nRun the service.\n\n"
        "## Security\n\nBinds locally by default.\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(SKILL_ROOT / "tools/audit_readme.py"), str(readme), "--profile", "server"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 error(s)" in result.stdout


def test_auditor_fails_broken_links_and_placeholder_content(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Example\n\nTODO\n\n[Missing](docs/missing.md)\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(SKILL_ROOT / "tools/audit_readme.py"), str(readme)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "TODO/FIXME/TBD marker" in result.stdout
    assert "broken relative link/image: docs/missing.md" in result.stdout


def test_auditor_warns_for_manual_volatile_metrics(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Example\n\n## Testing\n\nThe suite has 412 tests and coverage is 91%.\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(SKILL_ROOT / "tools/audit_readme.py"), str(readme)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "hand-maintained test count" in result.stdout
    assert "hard-coded coverage claim" in result.stdout
