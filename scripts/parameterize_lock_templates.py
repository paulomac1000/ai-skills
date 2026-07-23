#!/usr/bin/env python3
"""Parameterize NuGet project identities and teach the generator their lower-case form."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old in text:
        if text.count(old) != 1:
            raise RuntimeError(f"{path}: expected one replacement")
        path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
        return
    if new not in text:
        raise RuntimeError(f"{path}: neither reviewed old nor new fragment is present")


generator = ROOT / "skills/mcp-server-architect/tools/generate_dotnet_server.py"
replace_once(
    generator,
    '    return value.replace("__NAMESPACE__", namespace).replace("__SERVER_NAME__", server_name)\n',
    '    return (\n'
    '        value.replace("__NAMESPACE_LOWER__", namespace.lower())\n'
    '        .replace("__NAMESPACE__", namespace)\n'
    '        .replace("__SERVER_NAME__", server_name)\n'
    '    )\n',
)

tests = ROOT / "tests/test_mcp_dotnet_generator.py"
replace_once(
    tests,
    '    assert "<RestorePackagesWithLockFile>true</RestorePackagesWithLockFile>" in build_props\n\n'
    '    packages = (target / "Directory.Packages.props").read_text(encoding="utf-8")\n',
    '    assert "<RestorePackagesWithLockFile>true</RestorePackagesWithLockFile>" in build_props\n\n'
    '    server_lock = (target / "src/Acme.Mcp.Server/packages.lock.json").read_text(encoding="utf-8")\n'
    '    smoke_lock = (target / "tests/Acme.Mcp.Smoke/packages.lock.json").read_text(encoding="utf-8")\n'
    '    for lock in (server_lock, smoke_lock):\n'
    '        assert "Locked" not in lock\n'
    '        assert "locked.mcp." not in lock\n'
    '        assert "__NAMESPACE" not in lock\n'
    '    assert "acme.mcp.domain" in server_lock\n'
    '    assert "acme.mcp.server" in smoke_lock\n\n'
    '    packages = (target / "Directory.Packages.props").read_text(encoding="utf-8")\n',
)

locks = (
    ROOT
    / "skills/mcp-server-architect/tools/dotnet-template/src/"
    "__NAMESPACE__.Mcp.Server/packages.lock.json.template",
    ROOT
    / "skills/mcp-server-architect/tools/dotnet-template/tests/"
    "__NAMESPACE__.Mcp.Smoke/packages.lock.json.template",
)
for path in locks:
    content = path.read_text(encoding="utf-8")
    rendered = content.replace("locked.mcp.", "__NAMESPACE_LOWER__.mcp.")
    rendered = rendered.replace("Locked", "__NAMESPACE__")
    if "locked.mcp." in rendered or "Locked" in rendered:
        raise RuntimeError(f"unparameterized lock identity remains in {path}")
    path.write_text(rendered, encoding="utf-8", newline="\n")
