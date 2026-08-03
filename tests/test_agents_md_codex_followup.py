"""Regressions for the final Codex follow-up on PR #18."""

from __future__ import annotations

import stat
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills/agents-md-architect/tools"
sys.path.insert(0, str(TOOLS))

import agents_md_parse as parser  # noqa: E402
import audit_agents_md as audit_module  # noqa: E402
import discover_repository as discovery  # noqa: E402
import validate_agents_md as validator  # noqa: E402


def codes(findings: list[Any]) -> set[str]:
    return {item.code for item in findings}


def valid_application(extra: str = "") -> str:
    return f"""# AGENTS.md

## Scope

These instructions apply to the repository.

## Commands and verification

- Full gate: `python scripts/ci.py`

## Safety boundaries

Secrets must not be committed. Destructive writes require explicit authorization and rollback.

## Definition of done

Report the exact revision, skipped checks, and residual risk.
{extra}"""


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_deep_child_inherits_root_directive_through_intermediate_file(tmp_path: Path) -> None:
    root = write(
        tmp_path / "AGENTS.md",
        valid_application("\nDo not edit generated files.\n"),
    )
    intermediate = write(
        tmp_path / "packages/AGENTS.md",
        valid_application(),
    )
    deep = write(
        tmp_path / "packages/api/AGENTS.md",
        valid_application("\nAlways edit generated files.\n"),
    )
    findings = validator.validate_many(
        [root, intermediate, deep],
        "application",
        tmp_path,
        "monorepo",
        "en",
    )
    assert "tree.conflicting-rule" in codes(findings)


def test_fenced_example_inside_list_is_not_active_instruction(tmp_path: Path) -> None:
    path = write(
        tmp_path / "AGENTS.md",
        valid_application(
            """

- Example:

    ```python
    CONSENT_KEYWORDS = ["approve"]
    [Missing](docs/missing.md)
    ```
"""
        ),
    )
    findings = validator.validate_path(path, "application", tmp_path, "single", "en")
    assert "safety.keyword-approval" not in codes(findings)
    assert "links.missing" not in codes(findings)
    assert "structure.unclosed-fence" not in codes(findings)


def test_bounded_reader_requests_only_limit_plus_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read_sizes: list[int] = []

    class FakeStream:
        def __enter__(self) -> FakeStream:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, size: int) -> bytes:
            read_sizes.append(size)
            return b"x" * size

    monkeypatch.setattr(parser.os, "open", lambda *_args, **_kwargs: 42)
    if not parser._supports_component_nofollow():
        monkeypatch.setattr(
            parser.os,
            "lstat",
            lambda _path: SimpleNamespace(st_mode=stat.S_IFREG, st_size=1, st_dev=1, st_ino=1),
        )
    monkeypatch.setattr(
        parser.os,
        "fstat",
        lambda _descriptor: SimpleNamespace(st_mode=stat.S_IFREG, st_size=1, st_dev=1, st_ino=1),
    )
    monkeypatch.setattr(parser.os, "fdopen", lambda *_args, **_kwargs: FakeStream())
    monkeypatch.setattr(parser.os, "close", lambda _descriptor: None)

    result = parser.read_utf8_bounded(Path("ignored"), max_bytes=8)
    assert read_sizes == [9]
    assert result.code == "input.too-large"


def test_python_docstring_does_not_establish_gate_evidence(tmp_path: Path) -> None:
    write(
        tmp_path / "scripts/ci.py",
        '"""Example only: python scripts/ghost.py"""\nprint("gate")\n',
    )
    write(
        tmp_path / "AGENTS.md",
        valid_application().replace("python scripts/ci.py", "python scripts/ghost.py"),
    )
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "commands.unlocated-full-gate" in codes(findings)


def test_python_subprocess_call_establishes_gate_evidence(tmp_path: Path) -> None:
    write(
        tmp_path / "scripts/ci.py",
        'import subprocess\nsubprocess.run(["python", "tools/gate.py"], check=True)\n',
    )
    write(
        tmp_path / "AGENTS.md",
        valid_application().replace("python scripts/ci.py", "python tools/gate.py"),
    )
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "commands.unlocated-full-gate" not in codes(findings)


def test_discovery_stops_scandir_at_global_entry_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    consumed = 0

    class FakeEntry:
        def __init__(self, name: str) -> None:
            self.name = name
            self.path = str(tmp_path / name)

        def is_symlink(self) -> bool:
            return False

        def is_dir(self, *, follow_symlinks: bool) -> bool:
            assert follow_symlinks is False
            return False

        def is_file(self, *, follow_symlinks: bool) -> bool:
            assert follow_symlinks is False
            return True

    class FakeScandir:
        def __enter__(self) -> FakeScandir:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def __iter__(self) -> FakeScandir:
            return self

        def __next__(self) -> FakeEntry:
            nonlocal consumed
            consumed += 1
            if consumed > 2:
                raise AssertionError("scandir consumed past the global budget")
            return FakeEntry(f"file-{consumed}.txt")

    monkeypatch.setattr(discovery, "MAX_DISCOVERY_ENTRIES", 1)
    monkeypatch.setattr(discovery.os, "scandir", lambda _path: FakeScandir())
    result = discovery.discover(tmp_path)
    assert consumed == 2
    assert any("discovery entries exceed" in issue for issue in result.issues)


def test_github_env_command_does_not_establish_gate_evidence(tmp_path: Path) -> None:
    write(
        tmp_path / ".github/workflows/ci.yml",
        """name: CI

env:
  command: python scripts/ghost.py

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo real gate
""",
    )
    write(
        tmp_path / "AGENTS.md",
        valid_application().replace("python scripts/ci.py", "python scripts/ghost.py"),
    )
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "commands.unlocated-full-gate" in codes(findings)


def test_github_folded_run_reconstructs_executable_command(tmp_path: Path) -> None:
    write(
        tmp_path / ".github/workflows/ci.yml",
        """name: CI

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: >
          python -m
          pytest
""",
    )
    write(
        tmp_path / "AGENTS.md",
        valid_application().replace("python scripts/ci.py", "python -m pytest"),
    )
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "commands.unlocated-full-gate" not in codes(findings)


def test_dotnet_probe_consumes_shared_discovery_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_entries = 0
    scandir_calls = 0

    class FakeEntry:
        def __init__(self, name: str, *, directory: bool = False) -> None:
            self.name = name
            self.path = str(tmp_path / name)
            self.directory = directory

        def is_symlink(self) -> bool:
            return False

        def is_dir(self, *, follow_symlinks: bool) -> bool:
            assert follow_symlinks is False
            return self.directory

        def is_file(self, *, follow_symlinks: bool) -> bool:
            assert follow_symlinks is False
            return not self.directory

    class FakeScandir:
        def __init__(self, entries: list[FakeEntry], *, probe: bool = False) -> None:
            self.entries = iter(entries)
            self.probe = probe

        def __enter__(self) -> FakeScandir:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def __iter__(self) -> FakeScandir:
            return self

        def __next__(self) -> FakeEntry:
            nonlocal probe_entries
            if self.probe:
                probe_entries += 1
                if probe_entries > 3:
                    raise AssertionError(".NET probe consumed past the shared budget")
                return FakeEntry(f"sibling-{probe_entries}.txt")
            return next(self.entries)

    def fake_scandir(_path: object) -> FakeScandir:
        nonlocal scandir_calls
        scandir_calls += 1
        if scandir_calls == 1:
            return FakeScandir([FakeEntry("obj", directory=True)])
        return FakeScandir([], probe=True)

    monkeypatch.setattr(discovery, "MAX_DISCOVERY_ENTRIES", 2)
    monkeypatch.setattr(discovery.os, "scandir", fake_scandir)
    result = discovery.discover(tmp_path)
    assert probe_entries == 2
    assert any("discovery entries exceed" in issue for issue in result.issues)


def test_no_nofollow_fallback_rejects_changed_file_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = SimpleNamespace(st_mode=stat.S_IFREG, st_size=1, st_dev=1, st_ino=10)
    after = SimpleNamespace(st_mode=stat.S_IFREG, st_size=1, st_dev=1, st_ino=11)
    closed: list[int] = []

    monkeypatch.setattr(parser.os, "O_NOFOLLOW", 0, raising=False)
    monkeypatch.setattr(parser.os, "lstat", lambda _path: before)
    monkeypatch.setattr(parser.os, "open", lambda *_args, **_kwargs: 42)
    monkeypatch.setattr(parser.os, "fstat", lambda _descriptor: after)
    monkeypatch.setattr(parser.os, "close", closed.append)
    monkeypatch.setattr(
        parser.os,
        "fdopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("changed identity must not be read")),
    )

    result = parser.read_utf8_bounded(Path("ignored"), max_bytes=8)
    assert result.code == "input.read-error"
    assert "identity changed" in (result.message or "")
    assert closed == [42]


def test_github_literal_run_joins_shell_continuations(tmp_path: Path) -> None:
    write(
        tmp_path / ".github/workflows/ci.yml",
        """name: CI

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: |
          python scripts/ci.py \
            --strict
""",
    )
    write(
        tmp_path / "AGENTS.md",
        valid_application().replace("python scripts/ci.py", "python scripts/ci.py --strict"),
    )
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "commands.unlocated-full-gate" not in codes(findings)


def test_component_safe_reader_rejects_intermediate_symlink(tmp_path: Path) -> None:
    if not parser._supports_component_nofollow():
        pytest.skip("component-wise no-follow open is not available")
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    write(outside / "secret.txt", "outside")
    (tmp_path / "redirect").symlink_to(outside, target_is_directory=True)
    result = parser.read_utf8_bounded(tmp_path / "redirect/secret.txt")
    assert result.code == "input.read-error"
    assert result.text is None


def test_invalid_github_yaml_cannot_establish_gate_evidence(tmp_path: Path) -> None:
    write(
        tmp_path / ".github/workflows/ci.yml",
        """name: Invalid CI

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: python scripts/ghost.py
     invalid_sibling: true
""",
    )
    write(
        tmp_path / "AGENTS.md",
        valid_application().replace("python scripts/ci.py", "python scripts/ghost.py"),
    )
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "evidence.invalid-yaml" in codes(findings)
    assert "commands.unlocated-full-gate" in codes(findings)


def test_local_subprocess_name_does_not_establish_gate_evidence(tmp_path: Path) -> None:
    write(
        tmp_path / "scripts/ci.py",
        """class subprocess:
    @staticmethod
    def run(_args: object, **_kwargs: object) -> None:
        return None

subprocess.run(["python", "scripts/ghost.py"], check=True)
""",
    )
    write(
        tmp_path / "AGENTS.md",
        valid_application().replace("python scripts/ci.py", "python scripts/ghost.py"),
    )
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "commands.unlocated-full-gate" in codes(findings)


def test_deep_child_inherits_root_command_through_intermediate_file(tmp_path: Path) -> None:
    root = write(tmp_path / "AGENTS.md", valid_application())
    intermediate = write(
        tmp_path / "packages/AGENTS.md",
        valid_application().replace(
            "- Full gate: `python scripts/ci.py`",
            "- Focused check: `python -m pytest packages`",
        ),
    )
    deep = write(
        tmp_path / "packages/api/AGENTS.md",
        valid_application().replace("python scripts/ci.py", "python scripts/other.py"),
    )
    findings = validator.validate_many(
        [root, intermediate, deep],
        "application",
        tmp_path,
        "monorepo",
        "en",
    )
    assert "tree.conflicting-command" in codes(findings)


def test_deep_child_inherits_root_owner_through_intermediate_file(tmp_path: Path) -> None:
    write(tmp_path / "docs/root.md", "# Root owner\n")
    write(tmp_path / "docs/deep.md", "# Deep owner\n")
    root = write(
        tmp_path / "AGENTS.md",
        valid_application("\n## Sources of truth\n\n- [Normative contract](docs/root.md) — accepted behavior.\n"),
    )
    intermediate = write(tmp_path / "packages/AGENTS.md", valid_application())
    deep = write(
        tmp_path / "packages/api/AGENTS.md",
        valid_application("\n## Sources of truth\n\n- [Normative contract](../../docs/deep.md) — accepted behavior.\n"),
    )
    findings = validator.validate_many(
        [root, intermediate, deep],
        "application",
        tmp_path,
        "monorepo",
        "en",
    )
    assert "tree.conflicting-owner" in codes(findings)


def test_nested_python_imports_establish_real_gate_evidence(tmp_path: Path) -> None:
    write(
        tmp_path / "scripts/ci.py",
        """def run_gate() -> None:
    import subprocess

    subprocess.run(["python", "scripts/ghost.py"], check=True)
""",
    )
    write(
        tmp_path / "AGENTS.md",
        valid_application().replace("python scripts/ci.py", "python scripts/ghost.py"),
    )
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "commands.unlocated-full-gate" not in codes(findings)


def test_nested_os_import_establishes_real_gate_evidence(tmp_path: Path) -> None:
    write(
        tmp_path / "scripts/ci.py",
        """def run_gate() -> None:
    from os import system as execute

    execute("python scripts/ghost.py")
""",
    )
    write(
        tmp_path / "AGENTS.md",
        valid_application().replace("python scripts/ci.py", "python scripts/ghost.py"),
    )
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "commands.unlocated-full-gate" not in codes(findings)


def test_invalid_yaml_still_consumes_gate_byte_budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write(
        tmp_path / ".github/workflows/ci.yml",
        """name: Invalid CI

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: python scripts/ghost.py
     invalid_sibling: true
""",
    )
    write(tmp_path / "AGENTS.md", valid_application())
    monkeypatch.setattr(audit_module, "MAX_GATE_TOTAL_BYTES", 32)
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "evidence.gate-sources-too-large" in codes(findings)


def test_agents_skill_declares_yaml_runtime_dependency() -> None:
    manifest = yaml.safe_load((ROOT / "skills/agents-md-architect/manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["dependencies"]["packages"]["python"] == ["PyYAML>=6.0.3,<7"]
