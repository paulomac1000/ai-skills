#!/usr/bin/env python3
"""Parameterize project-reference identities in generated NuGet lock templates."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCKS = (
    ROOT
    / "skills/mcp-server-architect/tools/dotnet-template/src/"
    "__NAMESPACE__.Mcp.Server/packages.lock.json.template",
    ROOT
    / "skills/mcp-server-architect/tools/dotnet-template/tests/"
    "__NAMESPACE__.Mcp.Smoke/packages.lock.json.template",
)

for path in LOCKS:
    content = path.read_text(encoding="utf-8")
    rendered = content.replace("Locked", "__NAMESPACE__")
    if "Locked" in rendered:
        raise RuntimeError(f"unparameterized lock identity remains in {path}")
    path.write_text(rendered, encoding="utf-8", newline="\n")
