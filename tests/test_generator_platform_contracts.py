"""Error-path and platform coverage for both public project generators."""

from __future__ import annotations

import errno
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYTHON_GENERATOR = ROOT / "skills/mcp-server-architect/tools/generate_python_server.py"
DOTNET_GENERATOR = ROOT / "skills/mcp-server-architect/tools/generate_dotnet_server.py"


def load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeRename:
    """ctypes-compatible callable with writable signature attributes."""

    argtypes: list[Any] | None = None
    restype: Any = None

    def __init__(self, result: int) -> None:
        self.result = result
        self.calls: list[tuple[Any, ...]] = []

    def __call__(self, *args: Any) -> int:
        self.calls.append(args)
        return self.result


def test_dotnet_generator_validation_template_and_cli_contracts(tmp_path: Path, monkeypatch, capsys) -> None:
    generator = load(DOTNET_GENERATOR, "dotnet_generator_platform_contract")
    with pytest.raises(ValueError, match="server name"):
        generator.project_files("Acme", "x")

    missing = tmp_path / "missing"
    monkeypatch.setattr(generator, "TEMPLATE_ROOT", missing)
    with pytest.raises(FileNotFoundError):
        generator.project_files("Acme", "Acme MCP")

    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(generator, "TEMPLATE_ROOT", empty)
    with pytest.raises(RuntimeError, match="template is empty"):
        generator.project_files("Acme", "Acme MCP")

    monkeypatch.setattr(generator, "TEMPLATE_ROOT", ROOT / "skills/mcp-server-architect/tools/dotnet-template")
    target = tmp_path / "cli-dotnet"
    assert generator.main([str(target), "--namespace", "Acme.Product", "--name", "Acme MCP"]) == 0
    assert "generated" in capsys.readouterr().out
    assert (target / "src/Acme.Product.Mcp.Server/Acme.Product.Mcp.Server.csproj").is_file()


def test_dotnet_no_replace_platform_and_error_contracts(tmp_path: Path, monkeypatch) -> None:
    generator = load(DOTNET_GENERATOR, "dotnet_generator_rename_contract")
    destination = tmp_path / "destination"
    with pytest.raises(FileExistsError):
        generator._raise_rename_error(errno.EEXIST, destination)
    with pytest.raises(OSError):
        generator._raise_rename_error(errno.EACCES, destination)

    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(generator.platform, "system", lambda: "Plan9")
    with pytest.raises(RuntimeError, match="no configured"):
        generator._rename_noreplace(source, destination)

    renamed: list[tuple[Path, Path]] = []
    monkeypatch.setattr(generator.platform, "system", lambda: "Windows")
    monkeypatch.setattr(generator.os, "rename", lambda first, second: renamed.append((first, second)))
    generator._rename_noreplace(source, destination)
    assert renamed == [(source, destination)]

    monkeypatch.setattr(generator.platform, "system", lambda: "Linux")
    monkeypatch.setattr(generator.ctypes, "CDLL", lambda *_args, **_kwargs: SimpleNamespace())
    with pytest.raises(RuntimeError, match="renameat2"):
        generator._rename_noreplace(source, destination)

    successful = FakeRename(0)
    monkeypatch.setattr(generator.ctypes, "CDLL", lambda *_args, **_kwargs: SimpleNamespace(renameat2=successful))
    generator._rename_noreplace(source, destination)
    assert successful.calls

    failed = FakeRename(-1)
    monkeypatch.setattr(generator.ctypes, "CDLL", lambda *_args, **_kwargs: SimpleNamespace(renameat2=failed))
    monkeypatch.setattr(generator.ctypes, "get_errno", lambda: errno.EEXIST)
    with pytest.raises(FileExistsError):
        generator._rename_noreplace(source, destination)

    monkeypatch.setattr(generator.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(generator.ctypes, "CDLL", lambda *_args, **_kwargs: SimpleNamespace())
    with pytest.raises(RuntimeError, match="renamex_np"):
        generator._rename_noreplace(source, destination)


def test_python_generator_error_platform_and_cli_contracts(tmp_path: Path, monkeypatch, capsys) -> None:
    facade = load(PYTHON_GENERATOR, "python_generator_platform_contract")
    implementation = facade._implementation

    with pytest.raises(ValueError, match="server name"):
        facade.project_files("valid_mcp", "x")
    with pytest.raises(FileExistsError):
        implementation._raise_rename_error(errno.ENOTEMPTY, tmp_path / "target")
    with pytest.raises(OSError):
        implementation._raise_rename_error(errno.EPERM, tmp_path / "target")

    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    monkeypatch.setattr(implementation, "_runtime_platform", lambda: "plan9")
    monkeypatch.setattr(implementation, "_runtime_os_name", lambda: "posix")
    with pytest.raises(RuntimeError, match="no configured"):
        implementation._rename_noreplace(source, destination)

    renamed: list[tuple[Path, Path]] = []
    monkeypatch.setattr(implementation, "_runtime_platform", lambda: "win32")
    monkeypatch.setattr(implementation, "_runtime_os_name", lambda: "nt")
    monkeypatch.setattr(implementation.os, "rename", lambda first, second: renamed.append((first, second)))
    implementation._rename_noreplace(source, destination)
    assert renamed == [(source, destination)]

    monkeypatch.setattr(implementation, "_runtime_platform", lambda: "linux")
    monkeypatch.setattr(implementation.ctypes, "CDLL", lambda *_args, **_kwargs: SimpleNamespace())
    with pytest.raises(RuntimeError, match="renameat2"):
        implementation._rename_noreplace(source, destination)

    successful = FakeRename(0)
    monkeypatch.setattr(
        implementation.ctypes,
        "CDLL",
        lambda *_args, **_kwargs: SimpleNamespace(renameat2=successful),
    )
    implementation._rename_noreplace(source, destination)
    assert successful.calls

    monkeypatch.setattr(implementation, "_runtime_platform", lambda: "darwin")
    monkeypatch.setattr(implementation.ctypes, "CDLL", lambda *_args, **_kwargs: SimpleNamespace())
    with pytest.raises(RuntimeError, match="renamex_np"):
        implementation._rename_noreplace(source, destination)

    monkeypatch.undo()
    target = tmp_path / "cli-python"
    assert facade.main([str(target), "--package", "valid_mcp", "--name", "Valid MCP"]) == 0
    assert "Generated" in capsys.readouterr().out
    assert (target / "src/valid_mcp/server.py").is_file()


def test_python_generator_facade_rejects_missing_or_ambiguous_contract_fragments(tmp_path: Path, monkeypatch) -> None:
    facade = load(PYTHON_GENERATOR, "python_generator_facade_contract")
    monkeypatch.setattr(facade, "_LOCK_ROOT", tmp_path)
    with pytest.raises(RuntimeError, match="missing reviewed dependency contract"):
        facade._read_contract_file("missing.lock")
    with pytest.raises(RuntimeError, match="expected exactly one"):
        facade._replace_required("old old", "old", "new", file_name="test")
