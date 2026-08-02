#!/usr/bin/env python3
"""Apply all accepted PR #18 review fixes atomically."""

from __future__ import annotations

import ast

from . import audit_patch, discovery_patch, parser_patch, regressions, validator_patch
from .common import ROOT, write_atomically


def main() -> None:
    new_test_path = "tests/test_agents_md_codex_followup.py"
    if (ROOT / new_test_path).exists():
        raise RuntimeError(f"refusing to overwrite existing {new_test_path}")
    outputs = {
        "skills/agents-md-architect/tools/agents_md_parse.py": parser_patch.stage(),
        "skills/agents-md-architect/tools/validate_agents_md.py": validator_patch.stage(),
        "skills/agents-md-architect/tools/audit_agents_md.py": audit_patch.stage(),
        "skills/agents-md-architect/tools/discover_repository.py": discovery_patch.stage_discovery(),
        "tests/test_agents_md_review_regressions.py": discovery_patch.stage_existing_tests(),
        new_test_path: regressions.render(),
    }
    for relative, content in outputs.items():
        ast.parse(content, filename=relative)
    write_atomically(outputs)


if __name__ == "__main__":
    main()
