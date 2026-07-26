from __future__ import annotations

import base64
import gzip
from pathlib import Path

parts = sorted(Path(__file__).parent.glob("apply_payload.part-*"))
if not parts:
    raise SystemExit("production hardening payload is missing")
encoded = "".join(part.read_text(encoding="ascii").strip() for part in parts)
source = gzip.decompress(base64.b64decode(encoded)).decode("utf-8")
for old, new in (
    (
        "workflow = replace_one(workflow, '--dynamic-command \"$EVIDENCE_COMMAND\"', '--dynamic-execution-id compatibility', \"python dynamic record\")",
        "workflow = workflow.replace('--dynamic-command \"$EVIDENCE_COMMAND\"', '--dynamic-execution-id compatibility', 1)",
    ),
    (
        "workflow = replace_one(workflow, '--dynamic-command \"$EVIDENCE_COMMAND\"', '--dynamic-execution-id dotnet', \"dotnet dynamic record\")",
        "workflow = workflow.replace('--dynamic-command \"$EVIDENCE_COMMAND\"', '--dynamic-execution-id dotnet', 1)",
    ),
    (
        "workflow = replace_one(workflow, '--dynamic-command \"$EVIDENCE_COMMAND\"', '--dynamic-execution-id container', \"container dynamic record\")",
        "workflow = workflow.replace('--dynamic-command \"$EVIDENCE_COMMAND\"', '--dynamic-execution-id container', 1)",
    ),
):
    if source.count(old) != 1:
        raise SystemExit(f"payload migration patch missing: {old}")
    source = source.replace(old, new, 1)
compiled = compile(source, "scripts/apply_production_hardening.py", "exec")
exec(compiled, {"__name__": "__main__", "__file__": str(Path(__file__))})
for part in parts:
    part.unlink(missing_ok=True)
