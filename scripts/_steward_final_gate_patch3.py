from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
runpy.run_path(str(ROOT / "scripts/_steward_final_gate_patch2.py"), run_name="__main__")

path = ROOT / "skills/mcp-steward-architect/tools/steward-templates/dotnet/StewardSeedRuntime.cs.template"
text = path.read_text(encoding="utf-8")
old = "    private SeedAuthority AuthorityFor(string effectId, StewardSeedJob job, string source)\n"
new = "    private static SeedAuthority AuthorityFor(string effectId, StewardSeedJob job, string source)\n"
if text.count(old) != 1:
    raise RuntimeError(f"dotnet AuthorityFor static refinement: expected one match, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")

# Keep the compositional gate fully typed for the repository-wide mypy gate.
validator = ROOT / "skills/mcp-steward-architect/tools/validate_steward.py"
text = validator.read_text(encoding="utf-8")
old = '    contract = capability.get("contract") if isinstance(capability.get("contract"), dict) else {}\n'
new = '    raw_contract = capability.get("contract")\n    contract: dict[str, Any] = raw_contract if isinstance(raw_contract, dict) else {}\n'
if text.count(old) != 1:
    raise RuntimeError(f"validator capability contract typing refinement: expected one match, found {text.count(old)}")
validator.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
