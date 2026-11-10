"""PR #217 review-round regressions: one coherent shell scope engine (issue #212).

Covers the review findings against the rewrite of agents_md_shell_scoping:
conditional-body fail-closed transitions (P1), `fi` suffix transitions (ccTL),
function-close suffixes (ZDcO), argument-boundary-safe reconstruction (ccTD),
comment stripping order (ccTR), heredoc recognition before conditional parsing
(ZDcJ/ZK7Q/E), substitution entrypoint extraction (dHft), composite step env
(dHfz) and the release-workflow heredoc loop fixture (F).
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills" / "agents-md-architect" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from agents_md_composite_steps import composite_action_invocations  # noqa: E402
from agents_md_gate_sources import classify_gate_sources  # noqa: E402
from agents_md_shell_scoping import shell_invocations_with_scope  # noqa: E402
from discover_repository import discover  # noqa: E402


def _scoped(run: str, base: str = ".") -> list[tuple[str, str]]:
    scoped, _issues = shell_invocations_with_scope(run, base, "regression")
    return scoped


def _scoped_issues(run: str, base: str = ".") -> tuple[list[tuple[str, str]], list[str]]:
    return shell_invocations_with_scope(run, base, "regression")


# ---------- P1 (review 5832796774): conditional body ----------


def test_conditional_body_transition_fails_closed() -> None:
    scoped, issues = _scoped_issues("if false; then\ncd tools\nfi\npython check.py\n")
    assert not any(scope == "tools" for _command, scope in scoped)
    assert issues and "directory transition" in issues[0]


def test_conditional_body_python_is_retained_without_transitions() -> None:
    scoped = _scoped("if true; then\npython tools_check.py\nfi\n")
    assert ("python tools_check.py", ".") in scoped


# ---------- ZDcM / ccTL: commands and transitions after `fi` ----------


def test_fi_suffix_command_is_retained() -> None:
    scoped = _scoped("if true; then\necho yes\nfi; python check.py\n")
    assert ("python check.py", ".") in scoped


def test_fi_suffix_transition_is_applied_not_appended() -> None:
    scoped = _scoped("if true; then\necho yes\nfi; cd tools\npython check.py\n")
    assert ("python check.py", "tools") in scoped
    assert not any(command.startswith("cd ") for command, _scope in scoped)


# ---------- ZDcO: function definition closures ----------


def test_inline_function_close_suffix_is_retained() -> None:
    scoped = _scoped("helper() { echo yes; }; python check.py\n")
    assert ("python check.py", ".") in scoped


def test_multiline_function_close_suffix_is_retained() -> None:
    scoped = _scoped("helper() {\n  echo yes\n}; python check.py\n")
    assert ("python check.py", ".") in scoped


# ---------- ccTD: argument boundaries ----------


def test_quoted_assignment_boundary_survives_reconstruction() -> None:
    scoped = _scoped('PYTHONPATH="vendor libs" python -m check\n')
    assert shlex.split(scoped[0][0])[0] == "PYTHONPATH=vendor libs"


def test_if_opener_quoted_assignment_boundary_survives() -> None:
    scoped = _scoped('if true; then PYTHONPATH="vendor libs" python -m check; fi\n')
    assert any(shlex.split(command)[0] == "PYTHONPATH=vendor libs" for command, _scope in scoped)


# ---------- ccTR: comments before scope syntax ----------


def test_full_line_comment_does_not_block_parsing() -> None:
    scoped = _scoped("# Don't execute this comment\npython check.py\n")
    assert ("python check.py", ".") in scoped


def test_trailing_comment_keeps_transition() -> None:
    scoped = _scoped("cd tools # note\npython check.py\n")
    assert ("python check.py", "tools") in scoped


def test_comment_braces_never_create_structure() -> None:
    scoped, issues = _scoped_issues("# helper() {\npython check.py\n")
    assert issues == []
    assert ("python check.py", ".") in scoped


# ---------- ZDcJ / ZK7Q / E: heredoc recognition ----------


def test_heredoc_opener_command_is_retained() -> None:
    scoped = _scoped("python check.py <<'EOF'\nbody\nEOF\n")
    assert ("python check.py", ".") in scoped


def test_heredoc_opener_pipeline_is_retained() -> None:
    scoped = _scoped("cat <<EOF | python x.py\nbody\nEOF\n")
    assert any("python x.py" in command for command, _scope in scoped)


def test_heredoc_inside_conditional_opener_isolates_python_data() -> None:
    run = "if true; then cat <<'PY'\nif True:\n    print(\"data\")\nPY\nfi\npython check.py\n"
    scoped, issues = _scoped_issues(run)
    assert issues == []
    assert ("python check.py", ".") in scoped
    assert not any("print" in command for command, _scope in scoped)


def test_release_workflow_heredoc_python_loop_is_not_a_bash_loop() -> None:
    run = "python - <<'PY'\nimport yaml\nfor item in items:\n    print(item)\nPY\npython check.py\n"
    scoped, issues = _scoped_issues(run)
    assert issues == []
    assert ("python check.py", ".") in scoped
    assert not any("for item" in command for command, _scope in scoped)


def test_body_heredoc_isolates_data_inside_conditional() -> None:
    scoped, issues = _scoped_issues("if true; then\ncat <<'EOF'\nfor x in y:\n    print(x)\nEOF\nfi\npython check.py\n")
    assert issues == []
    assert ("python check.py", ".") in scoped
    assert not any("print" in command for command, _scope in scoped)


# ---------- dHft: command substitutions ----------


def test_command_substitution_entrypoint_is_counted() -> None:
    scoped = _scoped('out="$(python check.py)"\n')
    assert ("python check.py", ".") in scoped


def test_unterminated_substitution_fails_closed() -> None:
    _scoped, issues = _scoped_issues('tag="$(\ngh api example\n')
    assert issues and "substitution" in issues[-1]


# ---------- G: unsupported quoting and unclosed structures ----------


def test_malformed_quoting_produces_typed_issue() -> None:
    _scoped, issues = _scoped_issues('cd "tools\npython check.py\n')
    assert issues and "not statically parseable" in issues[0]


def test_unclosed_heredoc_and_conditional_fail_closed() -> None:
    _scoped, issues = _scoped_issues("if true; then\ncat <<'EOF'\nbody\n")
    assert len(issues) >= 2


# ---------- nested subshell restoration ----------


def test_nested_subshell_scope_is_restored() -> None:
    scoped = _scoped("(\ncd tools\n)\npython check.py\n")
    assert ("python check.py", ".") in scoped


# ---------- dHfz: composite step env ----------


def test_composite_step_pythonpath_is_carried() -> None:
    text = (
        "name: probe\n"
        "description: probe\n"
        "runs:\n"
        "  using: composite\n"
        "  steps:\n"
        "    - run: python -m check\n"
        "      shell: bash\n"
        "      env:\n"
        "        PYTHONPATH: lib\n"
    )
    scoped, issues, _references = composite_action_invocations(text, "actions/probe/action.yml")
    assert issues == []
    assert scoped == [("python -m check", ".", "lib")]


def test_composite_step_non_scalar_pythonpath_fails_closed() -> None:
    text = (
        "name: probe\n"
        "description: probe\n"
        "runs:\n"
        "  using: composite\n"
        "  steps:\n"
        "    - run: python -m check\n"
        "      shell: bash\n"
        "      env:\n"
        "        PYTHONPATH:\n"
        "          nested: value\n"
    )
    _scoped, issues, _references = composite_action_invocations(text, "actions/probe/action.yml")
    assert any("PYTHONPATH" in issue for issue in issues)


# ---------- full classifier: quoted PYTHONPATH ownership ----------


def test_quoted_pythonpath_counts_the_actual_source(tmp_path: Path) -> None:
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    (vendor / "check.py").write_text("VALUE = 1\n", encoding="utf-8")
    quoted = tmp_path / "vendor libs"
    quoted.mkdir()
    (quoted / "check.py").write_text("VALUE = 2\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  probe:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        '      - run: PYTHONPATH="vendor libs" python -m check\n',
        encoding="utf-8",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    counted = {item.path for item in inventory.sources if item.counted}
    assert ".github/workflows/ci.yml" in counted
    assert "vendor libs/check.py" in counted
    assert "vendor/check.py" not in counted
