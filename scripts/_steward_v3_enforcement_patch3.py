from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
runpy.run_path(str(ROOT / "scripts/_steward_v3_enforcement_patch2.py"), run_name="__main__")


def replace_once(path: str, old: str, new: str, label: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


runtime = "skills/mcp-steward-architect/tools/steward-templates/dotnet/StewardSeedRuntime.cs.template"
replace_once(
    runtime,
    "public sealed class FakeSeedProvider : ISeedProvider\n{\n    public string ProducerId => \"seed-provider\";",
    "public sealed class FakeSeedProvider : ISeedProvider\n{\n    private static readonly string[] ObservedTargetBinding = [\"target\"];\n    public string ProducerId => \"seed-provider\";",
    "dotnet fake provider static binding",
)
replace_once(
    runtime,
    'binding = new { satisfied = new[] { "target" } },',
    "binding = new { satisfied = ObservedTargetBinding },",
    "dotnet fake provider avoids repeated array allocation",
)
replace_once(
    runtime,
    "private static readonly IReadOnlyDictionary<string, int> AuthorityRank = new Dictionary<string, int>(StringComparer.Ordinal)",
    "private static readonly Dictionary<string, int> AuthorityRank = new(StringComparer.Ordinal)",
    "dotnet authority rank concrete field",
)
replace_once(
    runtime,
    '        var cancellationDispatch = effectId == "cancellation-dispatch";\n        if (Terminal.Contains(job.Status) || (!cancellationDispatch && job.Cancellation is "requested" or "fenced" or "reconciling")) return "LostAuthority";\n        if (cancellationDispatch && job.Cancellation is not ("requested" or "reconciling")) return "LostAuthority";',
    '        var cancellationDispatch = effectId == "cancellation-dispatch";\n        var cancellationFenced = job.Cancellation is "requested" or "fenced" or "reconciling";\n        if (Terminal.Contains(job.Status) || (!cancellationDispatch && cancellationFenced)) return "LostAuthority";\n        if (cancellationDispatch && job.Cancellation is not ("requested" or "reconciling")) return "LostAuthority";',
    "dotnet explicit cancellation predicate",
)

smoke = "skills/mcp-steward-architect/tools/steward-templates/dotnet/SmokeProgram.cs.template"
replace_once(
    smoke,
    "sealed class CountingSeedProvider : ISeedProvider\n{",
    "sealed class CountingSeedProvider : ISeedProvider\n{\n    private static readonly string[] ObservedTargetBinding = [\"target\"];",
    "dotnet smoke counting provider binding field",
)
replace_once(
    smoke,
    'binding = new { satisfied = new[] { "target" } },',
    "binding = new { satisfied = ObservedTargetBinding },",
    "dotnet smoke counting provider avoids array allocation",
)
replace_once(
    smoke,
    "sealed class UnapprovedSeedProvider : ISeedProvider\n{",
    "sealed class UnapprovedSeedProvider : ISeedProvider\n{\n    private static readonly string[] ObservedTargetBinding = [\"target\"];",
    "dotnet smoke unapproved provider binding field",
)
replace_once(
    smoke,
    'binding = new { satisfied = new[] { "target" } },',
    "binding = new { satisfied = ObservedTargetBinding },",
    "dotnet smoke unapproved provider avoids array allocation",
)

print("Steward v3 dotnet quality refinements applied")
