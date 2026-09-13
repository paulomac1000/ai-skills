from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "skills/mcp-steward-architect/tools/steward-templates/dotnet/StewardSeedRuntime.cs.template"
text = PATH.read_text(encoding="utf-8")
old = '''    public StewardSeedRuntime(string stateDirectory, ISeedClock clock, ISeedProvider provider, SeedFaultInjector faults, string profilePath, string proofPath)\n    {\n        Directory.CreateDirectory(stateDirectory);\n        _snapshotPath = Path.Combine(stateDirectory, "steward-state.json");\n        _ownerLock = new FileStream(Path.Combine(stateDirectory, "steward-state.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);\n        _clock = clock; _provider = provider; _faults = faults; _policy = SeedPolicy.Load(profilePath, proofPath); _state = LoadOrQuarantine();\n    }'''
new = '''    public StewardSeedRuntime(string stateDirectory, ISeedClock clock, ISeedProvider provider, SeedFaultInjector faults, string profilePath, string proofPath)\n    {\n        Directory.CreateDirectory(stateDirectory);\n        _snapshotPath = Path.Combine(stateDirectory, "steward-state.json");\n        _ownerLock = new FileStream(Path.Combine(stateDirectory, "steward-state.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);\n        _clock = clock; _provider = provider; _faults = faults;\n        try\n        {\n            _policy = SeedPolicy.Load(profilePath, proofPath);\n            _state = LoadOrQuarantine();\n        }\n        catch\n        {\n            // A constructor that fails closed must still release the single-owner lock.\n            // Otherwise the failed instance can strand the state directory on Windows\n            // even though no usable Steward runtime was ever returned to the caller.\n            _ownerLock.Dispose();\n            throw;\n        }\n    }'''
count = text.count(old)
if count != 1:
    raise RuntimeError(f"constructor anchor drift: expected exactly one match, found {count}")
PATH.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
print("patched StewardSeedRuntime constructor exception safety")
