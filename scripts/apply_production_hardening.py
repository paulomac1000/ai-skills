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
    (
        "workflow = replace_one(workflow, '--result-file python-container.xml', '--execution-record evidence/executions/container.json', \"container record\")",
        "workflow = replace_one(workflow, '--dynamic-lane docker-artifact             --result-file python-container.xml             --output', '--dynamic-lane docker-artifact             --execution-record evidence/executions/container.json             --output', \"container record\")",
    ),
    (
        'write("tests/test_evidence_verifier.py", decoded(TEST_VERIFIER_B64))',
        'write("tests/test_evidence_verifier.py", decoded(TEST_VERIFIER_B64) + "\\nsuccessful_fixture = fixture\\n")',
    ),
):
    if source.count(old) != 1:
        raise SystemExit(f"payload migration patch missing: {old}")
    source = source.replace(old, new, 1)
compiled = compile(source, "scripts/apply_production_hardening.py", "exec")
exec(compiled, {"__name__": "__main__", "__file__": str(Path(__file__))})

test_path = Path(__file__).resolve().parents[1] / "tests/test_evidence_verifier.py"
test_source = test_path.read_text(encoding="utf-8")
for old, new in (
    ("    report: bytes,\n", "    report: bytes | None,\n"),
    (
        '    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:\n        archive.writestr(REPORT_PATH, report)\n        for path, payload in (results or {RESULT_PATH: JUNIT}).items():\n',
        '    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:\n        if report is not None:\n            archive.writestr(REPORT_PATH, report)\n        for path, payload in (results or {RESULT_PATH: JUNIT}).items():\n',
    ),
):
    if test_source.count(old) != 1:
        raise SystemExit(f"test compatibility patch missing: {old}")
    test_source = test_source.replace(old, new, 1)
test_path.write_text(test_source, encoding="utf-8", newline="\n")

for part in parts:
    part.unlink(missing_ok=True)
