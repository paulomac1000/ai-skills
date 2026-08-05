#!/usr/bin/env python3
"""Apply the final bounded remediation for PR #18 and add focused regressions."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def write(relative: str, text: str) -> None:
    (ROOT / relative).write_text(text, encoding="utf-8")


def replace_once(relative: str, old: str, new: str) -> None:
    text = read(relative)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{relative}: expected one replacement, found {count}")
    write(relative, text.replace(old, new, 1))


def replace_count(relative: str, old: str, new: str, expected: int) -> None:
    text = read(relative)
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"{relative}: expected {expected} replacements, found {count}")
    write(relative, text.replace(old, new))


def remove_between(relative: str, start: str, end: str) -> None:
    text = read(relative)
    start_index = text.find(start)
    if start_index < 0:
        raise RuntimeError(f"{relative}: start marker not found: {start!r}")
    end_index = text.find(end, start_index)
    if end_index < 0:
        raise RuntimeError(f"{relative}: end marker not found: {end!r}")
    write(relative, text[:start_index] + text[end_index:])


# Route Codex context reads through the repository-confined shared reader.
replace_once(
    "skills/agents-md-architect/tools/agents_md_codex_platform.py",
    "from collections.abc import Iterable\nfrom pathlib import Path\n\nfrom agents_md_parse import read_utf8_bounded, trusted_input\nfrom agents_md_types import Finding\nfrom discover_repository import discover\n",
    "from collections.abc import Iterable\nfrom pathlib import Path\nimport sys\n\nTOOLS = Path(__file__).resolve().parent\nCONTRACTS = TOOLS.parents[2] / \"contracts\"\nif str(CONTRACTS) not in sys.path:\n    sys.path.insert(0, str(CONTRACTS))\n\nfrom agents_md_parse import trusted_input\nfrom agents_md_types import Finding\nfrom confined_io import ConfinedReadError, read_utf8_bounded\nfrom discover_repository import discover\n",
)
replace_once(
    "skills/agents-md-architect/tools/agents_md_codex_platform.py",
    """        result = read_utf8_bounded(trusted)
        if result.code is not None:
            findings.append(
                Finding(
                    str(path),
                    \"error\",
                    result.code,
                    1,
                    result.message or \"Codex instruction file could not be read.\",
                )
            )
            continue
        sizes[path] = result.byte_count
""",
    """        try:
            _text, byte_count = read_utf8_bounded(trusted, root, max_bytes)
        except ConfinedReadError as error:
            findings.append(
                Finding(
                    str(path),
                    \"error\",
                    error.code,
                    1,
                    error.message,
                )
            )
            continue
        sizes[path] = byte_count
""",
)

# Remove the duplicate legacy reader and keep Markdown parsing focused on parsing.
replace_once("skills/agents-md-architect/tools/agents_md_parse.py", "import os\n", "")
replace_once("skills/agents-md-architect/tools/agents_md_parse.py", "import stat\n", "")
replace_once("skills/agents-md-architect/tools/agents_md_parse.py", "    ReadResult,\n", "")
remove_between(
    "skills/agents-md-architect/tools/agents_md_parse.py",
    "def _supports_component_nofollow() -> bool:\n",
    "def _iter_code_span_matches(line: str) -> Iterator[tuple[str, int, int]]:\n",
)
replace_once(
    "skills/agents-md-architect/tools/agents_md_parse.py",
    """def _iter_code_span_matches(line: str) -> Iterator[tuple[str, int, int]]:
    index = 0
    while index < len(line):
        if line[index] != \"`\":
            index += 1
            continue
        end = index
        while end < len(line) and line[end] == \"`\":
            end += 1
        width = end - index
        closing = line.find(\"`\" * width, end)
        if closing < 0:
            return
        yield line[end:closing].strip(), index, closing + width
        index = closing + width
""",
    """def _iter_code_span_matches(line: str) -> Iterator[tuple[str, int, int]]:
    index = 0
    while index < len(line):
        if line[index] != \"`\":
            index += 1
            continue
        end = index
        while end < len(line) and line[end] == \"`\":
            end += 1
        width = end - index
        closing = end
        while closing < len(line):
            if line[closing] != \"`\":
                closing += 1
                continue
            closing_end = closing
            while closing_end < len(line) and line[closing_end] == \"`\":
                closing_end += 1
            if closing_end - closing == width:
                break
            closing = closing_end
        else:
            return
        yield line[end:closing].strip(), index, closing + width
        index = closing + width
""",
)

# Make lossless command normalization intrinsic to the implementation module.
replace_once("skills/agents-md-architect/tools/agents_md_shell_evidence_impl.py", "import shlex\n", "")
replace_once(
    "skills/agents-md-architect/tools/agents_md_shell_evidence_impl.py",
    "from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode\n",
    "from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode\n\nfrom agents_md_command import parse_invocation\n",
)
replace_once(
    "skills/agents-md-architect/tools/agents_md_shell_evidence_impl.py",
    """def _normalize_invocation(command: str) -> str | None:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return None
    return \" \".join(tokens) if tokens else None
""",
    """def _normalize_invocation(command: str) -> str | None:
    invocation = parse_invocation(command)
    return invocation.display if invocation is not None else None
""",
)
replace_once(
    "skills/agents-md-architect/tools/agents_md_shell_evidence_impl.py",
    """    if node is not None:
        visit(node, ())
    return nodes
""",
    """    if node is not None:
        try:
            visit(node, ())
        except RecursionError:
            return []
    return nodes
""",
)
replace_once(
    "skills/agents-md-architect/tools/agents_md_shell_evidence_impl.py",
    """def _compose_yaml(text: str) -> Node | None:
    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
    except (yaml.YAMLError, RecursionError):
        return None
    if root is not None and _has_duplicate_yaml_mapping_key(root):
        return None
    return root


def _yaml_syntax_error(text: str) -> str | None:
    \"\"\"Return a stable error that never includes repository-controlled excerpts.\"\"\"
    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
    except (yaml.YAMLError, RecursionError):
        return INVALID_YAML_MESSAGE
    if root is not None and _has_duplicate_yaml_mapping_key(root):
        return INVALID_YAML_MESSAGE
    return None
""",
    """def _compose_yaml(text: str) -> Node | None:
    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
        if root is not None and _has_duplicate_yaml_mapping_key(root):
            return None
    except (yaml.YAMLError, RecursionError):
        return None
    return root


def _yaml_syntax_error(text: str) -> str | None:
    \"\"\"Return a stable error that never includes repository-controlled excerpts.\"\"\"
    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
        if root is not None and _has_duplicate_yaml_mapping_key(root):
            return INVALID_YAML_MESSAGE
    except (yaml.YAMLError, RecursionError):
        return INVALID_YAML_MESSAGE
    return None
""",
)
replace_once(
    "skills/agents-md-architect/tools/agents_md_shell_evidence.py",
    "from agents_md_command import parse_invocation\n\n\ndef _normalize_invocation(command: str) -> str | None:\n    \"\"\"Return a round-trippable display string that preserves exact argv boundaries.\"\"\"\n    invocation = parse_invocation(command)\n    return invocation.display if invocation is not None else None\n\n\n# The implementation resolves this global at call time. Replace its legacy\n# whitespace-joining normalizer before exposing any extractor aliases.\n_impl._normalize_invocation = _normalize_invocation\n\n",
    "",
)

# Publish and type-check both halves of the workflow policy auditor.
replace_once(
    "skills/ci-cd-architect/manifest.yaml",
    "required:\n- SKILL.md\n- STANDARD.md\n- tools/check_github_actions_policy.py\n",
    "required:\n- SKILL.md\n- STANDARD.md\n- tools/check_github_actions_policy.py\n- tools/check_github_actions_policy_impl.py\n",
)
replace_once(
    "scripts/quality_targets.py",
    "    \"skills/ci-cd-architect/tools/check_github_actions_policy.py\",\n",
    "    \"skills/ci-cd-architect/tools/check_github_actions_policy.py\",\n    \"skills/ci-cd-architect/tools/check_github_actions_policy_impl.py\",\n",
)

# Keep self-hosting subprocess tests bounded and the lstat test double API-compatible.
replace_count(
    "tests/test_agents_md_release_contract.py",
    "        text=True,\n    )",
    "        text=True,\n        timeout=120,\n    )",
    2,
)
replace_once(
    "tests/test_latest_bot_followup.py",
    """    def replaced_lstat(path: os.PathLike[str] | str) -> os.stat_result:
        return replacement_stat if Path(path) == workflow else real_lstat(path)
""",
    """    def replaced_lstat(
        path: os.PathLike[str] | str,
        *,
        dir_fd: int | None = None,
    ) -> os.stat_result:
        if dir_fd is not None:
            return real_lstat(path, dir_fd=dir_fd)
        return replacement_stat if Path(path) == workflow else real_lstat(path)
""",
)

# Retire tests bound to the removed legacy reader; shared-reader and Codex-race tests replace them.
for obsolete in ("import stat\n", "from types import SimpleNamespace\n", "import agents_md_parse as parser  # noqa: E402\n"):
    replace_once("tests/test_agents_md_codex_followup.py", obsolete, "")
remove_between(
    "tests/test_agents_md_codex_followup.py",
    "def test_bounded_reader_requests_only_limit_plus_one(\n",
    "def test_python_docstring_does_not_establish_gate_evidence(tmp_path: Path) -> None:\n",
)
remove_between(
    "tests/test_agents_md_codex_followup.py",
    "def test_no_nofollow_fallback_rejects_changed_file_identity(\n",
    "def test_github_literal_run_joins_shell_continuations(tmp_path: Path) -> None:\n",
)
remove_between(
    "tests/test_agents_md_codex_followup.py",
    "def test_component_safe_reader_rejects_intermediate_symlink(tmp_path: Path) -> None:\n",
    "def test_invalid_github_yaml_cannot_establish_gate_evidence(tmp_path: Path) -> None:\n",
)

write(
    "tests/test_final_audit_regressions.py",
    '''"""Regressions for the final independent audit of PR #18."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills/agents-md-architect/tools"
CONTRACTS = ROOT / "contracts"
SCRIPTS = ROOT / "scripts"
for candidate in (TOOLS, CONTRACTS, SCRIPTS):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agents_md_codex_platform as codex_platform  # noqa: E402
import agents_md_parse as parser  # noqa: E402
import agents_md_shell_evidence_impl as shell_impl  # noqa: E402
import confined_io  # noqa: E402
from quality_targets import TYPE_PATHS  # noqa: E402


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_parser_no_longer_exposes_the_legacy_reader() -> None:
    assert not hasattr(parser, "read_utf8_bounded")


def test_inline_code_closer_requires_an_exact_backtick_run() -> None:
    line = "Use `literal ``missing.md`` text` as an example."
    assert list(parser.iter_references([(1, line)])) == []


def test_recursive_yaml_alias_fails_closed_without_recursion_error() -> None:
    text = "jobs: &jobs\n  loop: *jobs\n"
    assert shell_impl._yaml_syntax_error(text) == shell_impl.INVALID_YAML_MESSAGE
    assert shell_impl._extract_yaml_invocations(".github/workflows/ci.yml", text) == set()


def test_shell_implementation_preserves_argv_without_wrapper_rebinding() -> None:
    assert shell_impl._extract_shell_invocations("python 'scripts/full gate.py'") == {
        "python 'scripts/full gate.py'"
    }
    wrapper = (TOOLS / "agents_md_shell_evidence.py").read_text(encoding="utf-8")
    assert "_impl._normalize_invocation =" not in wrapper


def test_codex_fallback_rejects_intermediate_directory_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    outside = tmp_path / "outside"
    write(repository / "nested/AGENTS.md", "inside")
    write(outside / "AGENTS.md", "outside secret")

    probe = repository / "symlink-probe"
    try:
        probe.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlinks are unavailable: {error}")
    else:
        probe.unlink()

    target = (repository / "nested/AGENTS.md").absolute()
    real_open_stable = confined_io.open_stable
    replaced = False

    def replacing_open_stable(
        path: Path,
        flags: int,
        *,
        component_nofollow: bool | None = None,
    ) -> tuple[int, object]:
        nonlocal replaced
        if not replaced and Path(path).absolute() == target:
            replaced = True
            (repository / "nested").rename(repository / "nested-original")
            (repository / "nested").symlink_to(outside, target_is_directory=True)
        return real_open_stable(path, flags, component_nofollow=False)

    monkeypatch.setattr(confined_io, "open_stable", replacing_open_stable)
    findings = codex_platform._validate_codex_context(repository, (), 1024)

    assert replaced
    assert "input.read-error" in {finding.code for finding in findings}


def test_workflow_policy_impl_is_published_and_type_checked() -> None:
    implementation = "skills/ci-cd-architect/tools/check_github_actions_policy_impl.py"
    manifest = yaml.safe_load((ROOT / "skills/ci-cd-architect/manifest.yaml").read_text(encoding="utf-8"))
    assert "tools/check_github_actions_policy_impl.py" in manifest["required"]
    assert implementation in TYPE_PATHS
''',
)

replace_once(
    "CHANGELOG.md",
    "- Added a self-hosting release contract that runs the published strict validator and repository auditor against the repository's own root `AGENTS.md`.\n",
    "- Added a self-hosting release contract that runs the published strict validator and repository auditor against the repository's own root `AGENTS.md`.\n- Unified Codex context reads on shared component-confined I/O, removed the legacy duplicate reader, hardened exact Markdown span and recursive YAML parsing, and made policy-auditor publication and typing explicit.\n",
)

print("Applied final PR #18 audit remediation.")
