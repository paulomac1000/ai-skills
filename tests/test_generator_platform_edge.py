"""Small hosted-CI boundary regression for the Python generator platform guard."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _implementation():
    name = "generator_platform_edge_impl"
    path = ROOT / "skills/mcp-server-architect/tools/generate_python_server_impl.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_atomic_publication_rejects_unsupported_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    implementation = _implementation()
    source = tmp_path / "source"
    source.write_text("payload", encoding="utf-8")
    destination = tmp_path / "destination"
    monkeypatch.setattr(implementation, "_runtime_platform", lambda: "freebsd")
    monkeypatch.setattr(implementation, "_runtime_os_name", lambda: "posix")

    with pytest.raises(RuntimeError, match="unsupported on freebsd"):
        implementation._rename_noreplace(source, destination)
