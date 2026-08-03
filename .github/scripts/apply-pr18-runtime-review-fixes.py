from __future__ import annotations

from pathlib import Path

AUDIT = Path("skills/agents-md-architect/tools/audit_agents_md.py")
MANIFEST = Path("skills/agents-md-architect/manifest.yaml")
TESTS = Path("tests/test_agents_md_codex_followup.py")
CHANGELOG = Path("CHANGELOG.md")

contents = {
    path: path.read_text(encoding="utf-8")
    for path in (AUDIT, MANIFEST, TESTS, CHANGELOG)
}


def replace_once(path: Path, old: str, new: str) -> None:
    text = contents[path]
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one occurrence, found {count}")
    contents[path] = text.replace(old, new, 1)


replace_once(
    AUDIT,
    "from typing import Literal, cast",
    "from typing import Literal",
)
replace_once(
    AUDIT,
    "for node in cast(list[ast.AST], tree.body):",
    "for node in ast.walk(tree):",
)
replace_once(
    AUDIT,
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
            findings.append(
                AuditFinding(
                    root.as_posix(),
                    "error",
                    "evidence.gate-sources-too-large",
                    1,
                    f"CI/task source aggregate exceeds {MAX_GATE_TOTAL_BYTES} bytes.",
                )
            )
            break
''',
    '''        total_bytes += result.byte_count
        if total_bytes > MAX_GATE_TOTAL_BYTES:
            findings.append(
                AuditFinding(
                    root.as_posix(),
                    "error",
                    "evidence.gate-sources-too-large",
                    1,
                    f"CI/task source aggregate exceeds {MAX_GATE_TOTAL_BYTES} bytes.",
                )
            )
            break
        if Path(relative).suffix.casefold() in {".yml", ".yaml"}:
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
''',
)
replace_once(
    MANIFEST,
    '''dependencies:
  skills: []
  tools:
  - python
''',
    '''dependencies:
  skills: []
  tools:
  - python
  packages:
    python:
    - PyYAML>=6.0.3,<7
''',
)

regressions = r'''


def test_nested_python_imports_establish_real_gate_evidence(tmp_path: Path) -> None:
    write(
        tmp_path / "scripts/ci.py",
        """def run_gate() -> None:
    import subprocess

    subprocess.run(["python", "scripts/ghost.py"], check=True)
""",
    )
    write(
        tmp_path / "AGENTS.md",
        valid_application().replace("python scripts/ci.py", "python scripts/ghost.py"),
    )
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "commands.unlocated-full-gate" not in codes(findings)


def test_nested_os_import_establishes_real_gate_evidence(tmp_path: Path) -> None:
    write(
        tmp_path / "scripts/ci.py",
        """def run_gate() -> None:
    from os import system as execute

    execute("python scripts/ghost.py")
""",
    )
    write(
        tmp_path / "AGENTS.md",
        valid_application().replace("python scripts/ci.py", "python scripts/ghost.py"),
    )
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "commands.unlocated-full-gate" not in codes(findings)


def test_invalid_yaml_still_consumes_gate_byte_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    write(tmp_path / "AGENTS.md", valid_application())
    monkeypatch.setattr(audit_module, "MAX_GATE_TOTAL_BYTES", 32)
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "evidence.gate-sources-too-large" in codes(findings)


def test_agents_skill_declares_yaml_runtime_dependency() -> None:
    manifest = yaml.safe_load(
        (ROOT / "skills/agents-md-architect/manifest.yaml").read_text(encoding="utf-8")
    )
    assert manifest["dependencies"]["packages"]["python"] == ["PyYAML>=6.0.3,<7"]
'''
if "test_nested_python_imports_establish_real_gate_evidence" in contents[TESTS]:
    raise RuntimeError("runtime review regressions already exist")
contents[TESTS] = contents[TESTS].rstrip() + regressions + "\n"

replace_once(
    CHANGELOG,
    "- Hardened full ancestor directive, command, and canonical-owner inheritance; rejected invalid YAML as command evidence; and required real Python imports before trusting subprocess or operating-system calls.",
    "- Hardened full ancestor directive, command, and canonical-owner inheritance; rejected invalid YAML as command evidence; required real Python imports before trusting subprocess or operating-system calls; and declared the PyYAML runtime dependency used by the audit tool.",
)

for path, text in contents.items():
    path.write_text(text, encoding="utf-8")
