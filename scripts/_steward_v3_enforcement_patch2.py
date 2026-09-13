from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
runpy.run_path(str(ROOT / "scripts/_steward_v3_enforcement_patch.py"), run_name="__main__")


def replace_once(path: str, old: str, new: str, label: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


replace_once(
    "skills/mcp-steward-architect/tools/steward-templates/python/steward_runtime.py.template",
    '    if job["status"] in _TERMINAL or job["cancellation"] in {"requested", "fenced", "reconciling"}:\n        reasons.append(("LostAuthority", "job is terminal or cancellation-fenced"))',
    '    cancellation_dispatch = effect["id"] == "cancellation-dispatch"\n    if job["status"] in _TERMINAL or (\n        not cancellation_dispatch and job["cancellation"] in {"requested", "fenced", "reconciling"}\n    ):\n        reasons.append(("LostAuthority", "job is terminal or cancellation-fenced"))\n    if cancellation_dispatch and job["cancellation"] not in {"requested", "reconciling"}:\n        reasons.append(("LostAuthority", "cancellation dispatch requires an active cancellation request"))',
    "python cancellation-specific mutation admission",
)
replace_once(
    "skills/mcp-steward-architect/tools/steward-templates/dotnet/StewardSeedRuntime.cs.template",
    '        if (Terminal.Contains(job.Status) || job.Cancellation is "requested" or "fenced" or "reconciling") return "LostAuthority";',
    '        var cancellationDispatch = effectId == "cancellation-dispatch";\n        if (Terminal.Contains(job.Status) || (!cancellationDispatch && job.Cancellation is "requested" or "fenced" or "reconciling")) return "LostAuthority";\n        if (cancellationDispatch && job.Cancellation is not ("requested" or "reconciling")) return "LostAuthority";',
    ".NET cancellation-specific mutation admission",
)
replace_once(
    "tests/test_mcp_steward_runtime_security.py",
    "            store.save_terminal(job_id, completion, handoff)\n            published = True",
    "            store.save_terminal(\n                job_id, completion, handoff, expected_attempt_id=initial[\"attemptId\"],\n                expected_version=initial[\"version\"], mutation_decision_ref=\"test-admission\"\n            )\n            published = True",
    "terminal read regression fenced save",
)

print("Steward v3 cancellation/terminal regression refinements applied")
