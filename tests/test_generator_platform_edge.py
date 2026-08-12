"""Small hosted-CI boundary regressions for Python generator guards."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_atomic_publication_rejects_unsupported_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    implementation = _load(
        "generator_platform_edge_impl",
        "skills/mcp-server-architect/tools/generate_python_server_impl.py",
    )
    source = tmp_path / "source"
    source.write_text("payload", encoding="utf-8")
    destination = tmp_path / "destination"
    monkeypatch.setattr(implementation, "_runtime_platform", lambda: "freebsd")
    monkeypatch.setattr(implementation, "_runtime_os_name", lambda: "posix")

    with pytest.raises(RuntimeError, match="unsupported on freebsd"):
        implementation._rename_noreplace(source, destination)


def test_atomic_publication_exercises_macos_no_replace_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    implementation = _load(
        "generator_platform_edge_macos_impl",
        "skills/mcp-server-architect/tools/generate_python_server_impl.py",
    )

    class FakeRename:
        argtypes = None
        restype = None

        def __call__(self, source: bytes, destination: bytes, flags: int) -> int:
            assert source
            assert destination
            assert flags == 0x00000004
            return 0

    class FakeLibC:
        renamex_np = FakeRename()

    source = tmp_path / "source"
    source.write_text("payload", encoding="utf-8")
    destination = tmp_path / "destination"
    monkeypatch.setattr(implementation, "_runtime_platform", lambda: "darwin")
    monkeypatch.setattr(implementation, "_runtime_os_name", lambda: "posix")
    monkeypatch.setattr(implementation.ctypes, "CDLL", lambda *args, **kwargs: FakeLibC())

    implementation._rename_noreplace(source, destination)


def test_generator_cli_fails_closed_for_existing_destination(tmp_path: Path) -> None:
    generator = _load(
        "generator_platform_edge_public",
        "skills/mcp-server-architect/tools/generate_python_server.py",
    )
    destination = tmp_path / "existing"
    destination.mkdir()

    with pytest.raises(SystemExit):
        generator.main([str(destination), "--package", "sample_server"])
