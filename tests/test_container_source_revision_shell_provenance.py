"""Container provenance must not trust RUN checks executed by a custom Docker shell."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
INSPECTOR = ROOT / "skills/mcp-server-architect/tools/inspect_existing_project.py"


def _inspector() -> ModuleType:
    spec = importlib.util.spec_from_file_location("container_source_revision_shell_provenance", INSPECTOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_custom_shell_cannot_establish_source_revision_binding() -> None:
    inspector = _inspector()
    dockerfile = (
        "FROM python:3.12-slim\n"
        "ARG EXPECTED_SOURCE_REVISION\n"
        "COPY dist/ /tmp/dist/\n"
        'SHELL ["/tmp/dist/fake-shell"]\n'
        'RUN test "$(cat /tmp/dist/SOURCE_REVISION)" = "$EXPECTED_SOURCE_REVISION"\n'
    )

    assert inspector._source_revision_binding_state(dockerfile, ["EXPECTED_SOURCE_REVISION"]) == (True, False)
