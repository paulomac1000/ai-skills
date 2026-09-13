from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "scripts/_steward_final_gate_patch.py"
text = PATCH.read_text(encoding="utf-8")
old = '''def replace_once(path: str, old: str, new: str, label: str) -> None:\n    target = ROOT / path\n    text = target.read_text(encoding="utf-8")\n    count = text.count(old)\n    if count != 1:\n        raise RuntimeError(f"{label}: expected one match, found {count}")\n    target.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\\n")\n'''
new = '''def replace_once(path: str, old: str, new: str, label: str) -> None:\n    target = ROOT / path\n    text = target.read_text(encoding="utf-8")\n    count = text.count(old)\n    repeated_first = {\n        "template submit capability contract",\n        "template submit finalization reserve",\n        "generator submit contract",\n        "generator submit reserve",\n    }\n    expected = 2 if label in repeated_first else 1\n    if count != expected:\n        raise RuntimeError(f"{label}: expected {expected} match(es), found {count}")\n    target.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\\n")\n'''
if text.count(old) != 1:
    raise RuntimeError("patch helper drift: expected exactly one helper definition")
PATCH.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
runpy.run_path(str(PATCH), run_name="__main__")


def target_replace_once(relative: str, old: str, new: str, label: str) -> None:
    path = ROOT / relative
    body = path.read_text(encoding="utf-8")
    count = body.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one target match, found {count}")
    path.write_text(body.replace(old, new, 1), encoding="utf-8", newline="\n")


runtime = "skills/mcp-steward-architect/tools/steward-templates/python/steward_runtime.py.template"
target_replace_once(
    runtime,
    '                "INSERT INTO steward_jobs VALUES(?,?,?,?,0,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",\n                (job_id, lineage_id, generation, attempt_id, _canonical(subject), _canonical(candidate), request_digest,\n                 "queued", "admitted", "none", None, now, now, now, now, 1, "admitted", deadline, None,\n                 f"steward-runtime:{attempt_id}", generation, deadline),',
    '                "INSERT INTO steward_jobs("\n                "job_id,lineage_id,generation,attempt_id,version,subject_json,candidate_json,request_digest,status,stage,cancellation,"\n                "blocked_reason,created_at,updated_at,heartbeat_at,progress_at,progress_revision,progress_marker,deadline_at,"\n                "finalization_starts_at,lease_owner,lease_fencing_token,lease_expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",\n                (job_id, lineage_id, generation, attempt_id, 0, _canonical(subject), _canonical(candidate), request_digest,\n                 "queued", "admitted", "none", None, now, now, now, now, 1, "admitted", deadline, None,\n                 f"steward-runtime:{attempt_id}", generation, deadline),',
    "python explicit steward job insert",
)

test_file = "tests/test_mcp_steward_architect.py"
target_replace_once(
    test_file,
    '    mutation["effects"][0]["capability_ref"] = "missing:capability"\n    mutation["effects"][0]["capability_contract"]["id"] = "missing:capability"',
    '    mutation["effects"][0]["capability_ref"] = "missing:capability"',
    "focused unresolved capability test",
)

for relative in (
    "skills/mcp-steward-architect/tools/steward-templates/python/test_steward_runtime.py.template",
    "tests/test_mcp_steward_runtime_security.py",
    "tests/test_mcp_steward_evidence_selectors.py",
):
    target = ROOT / relative
    target.write_text(target.read_text(encoding="utf-8").rstrip() + "\n", encoding="utf-8", newline="\n")
