from pathlib import Path

path = Path("skills/agents-md-architect/tools/validate_agents_md.py")
text = path.read_text(encoding="utf-8")
replacements = {
    """            inherited_entry = inherited_commands.get(command.key)
            if inherited_entry is None:
                continue
            inherited_source, inherited_command = inherited_entry
""": """            inherited_command_entry = inherited_commands.get(command.key)
            if inherited_command_entry is None:
                continue
            inherited_source, inherited_command = inherited_command_entry
""",
    """            inherited_entry = inherited_ownership.get(owner.key)
            if inherited_entry is None:
                continue
            inherited_source, inherited_owner = inherited_entry
""": """            inherited_owner_entry = inherited_ownership.get(owner.key)
            if inherited_owner_entry is None:
                continue
            inherited_source, inherited_owner = inherited_owner_entry
""",
}
for old, new in replacements.items():
    if text.count(old) != 1:
        raise RuntimeError(f"expected one generated block, found {text.count(old)}")
    text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
