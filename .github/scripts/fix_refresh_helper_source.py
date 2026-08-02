from pathlib import Path

HELPER = Path(__file__).with_name("refresh_dependency_set.py")
OLD = (
    '            "For production, use the stable official SDK line with an upper bound that excludes the next major until migration is complete. '
    'The generated baseline uses `mcp>=1.27.2,<2`, while repository verification uses an exact stable pin. '
    'While official SDK v2 is pre-release, it belongs to a separate experimental CI lane with an exact pin and cannot define the production artifact. '
    'A candidate major becomes production-supported only after registration, lifecycle, transport, policy parity, content, cancellation, and artifact matrices pass.",'
)
NEW = OLD.replace("mcp>=1.27.2,<2", "mcp>=2.0.0,<3")

text = HELPER.read_text(encoding="utf-8")
if OLD not in text:
    raise RuntimeError("expected profile migration source literal is missing")
HELPER.write_text(text.replace(OLD, NEW), encoding="utf-8", newline="")
