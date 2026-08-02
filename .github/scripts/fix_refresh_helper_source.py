from pathlib import Path

HELPER = Path(__file__).with_name("refresh_dependency_set.py")
OLD_PROFILE = (
    '            "For production, use the stable official SDK line with an upper bound that excludes the next major until migration is complete. '
    'The generated baseline uses `mcp>=1.27.2,<2`, while repository verification uses an exact stable pin. '
    'While official SDK v2 is pre-release, it belongs to a separate experimental CI lane with an exact pin and cannot define the production artifact. '
    'A candidate major becomes production-supported only after registration, lifecycle, transport, policy parity, content, cancellation, and artifact matrices pass.",'
)
NEW_PROFILE = OLD_PROFILE.replace("mcp>=1.27.2,<2", "mcp>=2.0.0,<3")
OLD_COMBINED = '    combined = "\\n".join((implementation, generator_test, profile))'
NEW_COMBINED = '    combined = "\\n".join((implementation, profile))'

text = HELPER.read_text(encoding="utf-8")
for old in (OLD_PROFILE, OLD_COMBINED):
    if old not in text:
        raise RuntimeError(f"expected helper source literal is missing: {old!r}")
text = text.replace(OLD_PROFILE, NEW_PROFILE).replace(OLD_COMBINED, NEW_COMBINED)
HELPER.write_text(text, encoding="utf-8", newline="")
