"""Generate regressions for the final Codex follow-up."""

from __future__ import annotations

from textwrap import dedent


def render() -> str:
    return dedent(
        r'''
        """Regressions for the final Codex follow-up on PR #18."""

        from __future__ import annotations

        import stat
        import sys
        from pathlib import Path
        from types import SimpleNamespace
        from typing import Any

        import pytest

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
            monkeypatch.setattr(
                parser.os,
                "fstat",
                lambda _descriptor: SimpleNamespace(st_mode=stat.S_IFREG, st_size=1),
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
        '''
    ).lstrip()
