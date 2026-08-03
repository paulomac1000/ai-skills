from __future__ import annotations

from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one occurrence, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


audit = Path("skills/agents-md-architect/tools/audit_agents_md.py")
replace_once(
    audit,
    "from typing import Literal, cast\n\nTOOLS =",
    "from typing import Literal, cast\n\nimport yaml\n\nTOOLS =",
)
replace_once(
    audit,
    '''def _extract_yaml_invocations(relative: str, text: str) -> set[str]:
    invocations: set[str] = set()
''',
    '''def _yaml_syntax_error(text: str) -> str | None:
    """Return a stable syntax error without constructing repository-controlled values."""
    try:
        for _event in yaml.parse(text, Loader=yaml.SafeLoader):
            pass
    except (yaml.YAMLError, RecursionError) as error:
        return str(error)
    return None


def _extract_yaml_invocations(relative: str, text: str) -> set[str]:
    invocations: set[str] = set()
''',
)
replace_once(
    audit,
    '''    subprocess_calls = {"run", "call", "check_call", "check_output", "Popen"}
    subprocess_modules = {"subprocess"}
    os_modules = {"os"}
''',
    '''    subprocess_calls = {"run", "call", "check_call", "check_output", "Popen"}
    subprocess_modules: set[str] = set()
    os_modules: set[str] = set()
''',
)
replace_once(
    audit,
    '''        total_bytes += result.byte_count
        if total_bytes > MAX_GATE_TOTAL_BYTES:
''',
    '''        if Path(relative).suffix.casefold() in {".yml", ".yaml"}:
            syntax_error = _yaml_syntax_error(result.text)
            if syntax_error is not None:
                findings.append(
                    AuditFinding(
                        relative,
                        "error",
                        "evidence.invalid-yaml",
                        1,
                        f"YAML gate source is invalid and cannot establish command evidence: {syntax_error}",
                    )
                )
                continue
        total_bytes += result.byte_count
        if total_bytes > MAX_GATE_TOTAL_BYTES:
''',
)

validator = Path("skills/agents-md-architect/tools/validate_agents_md.py")
replace_once(
    validator,
    '''        parent_commands = {item.key: item for item in parent.commands}
        for command in child.commands:
            inherited_command = parent_commands.get(command.key)
            if inherited_command and inherited_command.command != command.command and not command.explicit_local:
                findings.append(
                    Finding(
                        str(child.path),
                        "error",
                        "tree.conflicting-command",
                        command.line,
                        f"Command conflicts with inherited command at {parent.relative_path}:{inherited_command.line}.",
                    )
                )

        parent_ownership = {item.key: item for item in parent.ownership}
        for owner in child.ownership:
            inherited_owner = parent_ownership.get(owner.key)
            if inherited_owner and inherited_owner.target != owner.target and not owner.explicit_local:
                findings.append(
                    Finding(
                        str(child.path),
                        "error",
                        "tree.conflicting-owner",
                        owner.line,
                        f"Canonical owner conflicts with {parent.relative_path}:{inherited_owner.line}.",
                    )
                )
''',
    '''        inherited_commands: dict[str, tuple[ParsedDocument, CommandRule]] = {}
        for ancestor in ancestors:
            for item in ancestor.commands:
                inherited_commands[item.key] = (ancestor, item)
        for command in child.commands:
            inherited_entry = inherited_commands.get(command.key)
            if inherited_entry is None:
                continue
            inherited_source, inherited_command = inherited_entry
            if inherited_command.command != command.command and not command.explicit_local:
                findings.append(
                    Finding(
                        str(child.path),
                        "error",
                        "tree.conflicting-command",
                        command.line,
                        (
                            "Command conflicts with inherited command at "
                            f"{inherited_source.relative_path}:{inherited_command.line}."
                        ),
                    )
                )

        inherited_ownership: dict[str, tuple[ParsedDocument, OwnershipRule]] = {}
        for ancestor in ancestors:
            for item in ancestor.ownership:
                inherited_ownership[item.key] = (ancestor, item)
        for owner in child.ownership:
            inherited_entry = inherited_ownership.get(owner.key)
            if inherited_entry is None:
                continue
            inherited_source, inherited_owner = inherited_entry
            if inherited_owner.target != owner.target and not owner.explicit_local:
                findings.append(
                    Finding(
                        str(child.path),
                        "error",
                        "tree.conflicting-owner",
                        owner.line,
                        (
                            "Canonical owner conflicts with "
                            f"{inherited_source.relative_path}:{inherited_owner.line}."
                        ),
                    )
                )
''',
)
replace_once(
    validator,
    '''    Directive,
    DomainProfileName,
    Finding,
''',
    '''    CommandRule,
    Directive,
    DomainProfileName,
    Finding,
    OwnershipRule,
''',
)

tests = Path("tests/test_agents_md_codex_followup.py")
addition = r'''


def test_invalid_github_yaml_cannot_establish_gate_evidence(tmp_path: Path) -> None:
    write(
        tmp_path / ".github/workflows/ci.yml",
        """name: Invalid CI

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: python scripts/ghost.py
     invalid_sibling: true
""",
    )
    write(
        tmp_path / "AGENTS.md",
        valid_application().replace("python scripts/ci.py", "python scripts/ghost.py"),
    )
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "evidence.invalid-yaml" in codes(findings)
    assert "commands.unlocated-full-gate" in codes(findings)


def test_local_subprocess_name_does_not_establish_gate_evidence(tmp_path: Path) -> None:
    write(
        tmp_path / "scripts/ci.py",
        """class subprocess:
    @staticmethod
    def run(_args: object, **_kwargs: object) -> None:
        return None

subprocess.run(["python", "scripts/ghost.py"], check=True)
""",
    )
    write(
        tmp_path / "AGENTS.md",
        valid_application().replace("python scripts/ci.py", "python scripts/ghost.py"),
    )
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "commands.unlocated-full-gate" in codes(findings)


def test_deep_child_inherits_root_command_through_intermediate_file(tmp_path: Path) -> None:
    root = write(tmp_path / "AGENTS.md", valid_application())
    intermediate = write(
        tmp_path / "packages/AGENTS.md",
        valid_application().replace(
            "- Full gate: `python scripts/ci.py`",
            "- Focused check: `python -m pytest packages`",
        ),
    )
    deep = write(
        tmp_path / "packages/api/AGENTS.md",
        valid_application().replace("python scripts/ci.py", "python scripts/other.py"),
    )
    findings = validator.validate_many(
        [root, intermediate, deep],
        "application",
        tmp_path,
        "monorepo",
        "en",
    )
    assert "tree.conflicting-command" in codes(findings)


def test_deep_child_inherits_root_owner_through_intermediate_file(tmp_path: Path) -> None:
    write(tmp_path / "docs/root.md", "# Root owner\n")
    write(tmp_path / "docs/deep.md", "# Deep owner\n")
    root = write(
        tmp_path / "AGENTS.md",
        valid_application("\n## Sources of truth\n\n- [Normative contract](docs/root.md) — accepted behavior.\n"),
    )
    intermediate = write(tmp_path / "packages/AGENTS.md", valid_application())
    deep = write(
        tmp_path / "packages/api/AGENTS.md",
        valid_application(
            "\n## Sources of truth\n\n- [Normative contract](../../docs/deep.md) — accepted behavior.\n"
        ),
    )
    findings = validator.validate_many(
        [root, intermediate, deep],
        "application",
        tmp_path,
        "monorepo",
        "en",
    )
    assert "tree.conflicting-owner" in codes(findings)
'''
text = tests.read_text(encoding="utf-8")
marker = "def test_invalid_github_yaml_cannot_establish_gate_evidence"
if marker in text:
    raise RuntimeError("regression tests already applied")
tests.write_text(text.rstrip() + addition + "\n", encoding="utf-8")
