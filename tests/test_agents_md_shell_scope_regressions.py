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


# ---------- hTzs: independent command-substitution scope ----------


def test_command_substitution_has_independent_directory_scope() -> None:
    scoped = _scoped('cd tools\necho "$(cd nested; python check.py)"\npython after.py\n')
    assert ("python check.py", "tools/nested") in scoped
    assert ("python after.py", "tools") in scoped
    assert not any(command == "python check.py" and scope == "tools" for command, scope in scoped)


def test_substitution_scope_cannot_mutate_parent_directory() -> None:
    scoped = _scoped('echo "$(cd somewhere; python inner.py)"\npython after.py\n')
    assert ("python inner.py", "somewhere") in scoped
    assert ("python after.py", ".") in scoped


def test_substitution_recursion_and_size_envelope_fail_closed() -> None:
    deep = 'echo "$(echo "$(echo "$(echo "$(echo "$(python x.py)")")")")")"'
    _scoped, issues = _scoped_issues(deep)
    assert issues and "bounded static analysis envelope" in issues[0]


# ---------- hTzu: quoted parentheses inside substitutions ----------


def test_literal_open_paren_in_substitution_body_is_data() -> None:
    scoped = _scoped("tag=\"$(printf '(')\"\npython check.py\n")
    assert any(command == "printf '('" for command, _scope in scoped)
    assert ("python check.py", ".") in scoped


def test_literal_close_paren_in_substitution_body_is_data() -> None:
    scoped = _scoped("tag=\"$(printf ')')\"\npython check.py\n")
    assert any(command == "printf ')'" for command, _scope in scoped)
    assert ("python check.py", ".") in scoped


def test_unbalanced_substitution_body_fails_closed() -> None:
    _scoped, issues = _scoped_issues("tag=\"$(echo '('\"\npython check.py\n")
    assert issues and "substitution" in issues[-1]


def test_nested_substitution_body_boundary_is_preserved() -> None:
    scoped = _scoped('a="$(echo $(python inner.py))"\npython check.py\n')
    assert ("python check.py", ".") in scoped


# ---------- hTzz: balanced nested conditionals ----------


def test_balanced_nested_one_line_conditional_is_processed() -> None:
    scoped, issues = _scoped_issues("if true; then\n    if true; then python check.py; fi\nfi\npython after.py\n")
    assert issues == []
    assert ("python check.py", ".") in scoped
    assert ("python after.py", ".") in scoped


def test_nested_conditional_transition_fails_closed() -> None:
    _scoped, issues = _scoped_issues("if true; then\n    if true; then cd nested; fi\nfi\npython check.py\n")
    assert issues and "directory transition" in issues[0]


def test_multiline_nested_conditional_keeps_depth_balanced() -> None:
    scoped, issues = _scoped_issues(
        "if true; then\n    if false; then\npython nested_check.py\n    fi\nfi\npython after.py\n"
    )
    assert ("python nested_check.py", ".") in scoped
    assert ("python after.py", ".") in scoped
    assert not any("unterminated" in issue for issue in issues)


# ---------- heredoc same-line suffix (review 5838117760) ----------


def test_command_after_same_line_heredoc_is_retained() -> None:
    scoped = _scoped("cat <<EOF; python check.py\npayload\nEOF\n")
    assert ("python check.py", ".") in scoped


def test_pipeline_heredoc_stage_stays_in_surface() -> None:
    scoped = _scoped("cat <<EOF | python check.py\npayload\nEOF\n")
    assert any("python check.py" in command for command, _scope in scoped)


def test_multiple_heredoc_redirections_fail_closed() -> None:
    _scoped, issues = _scoped_issues("cat <<A <<B\npayload\nB\nA\npython check.py\n")
    assert issues and "multiple heredoc" in issues[0]


# ---------- ok_b / ok_o / 5839793113: function braces and conditional order ----------


def test_next_line_function_brace_does_not_execute_uncalled_body() -> None:
    scoped, issues = _scoped_issues("helper()\n{\ncd tools\n}\npython check.py\n")
    assert issues == []
    assert ("python check.py", ".") in scoped
    assert not any(scope == "tools" for _command, scope in scoped)


def test_missing_function_brace_fails_closed() -> None:
    _scoped, issues = _scoped_issues("helper()\npython check.py\n")
    assert issues and "opening brace" in issues[-1]


def test_quoted_closing_brace_keeps_function_open() -> None:
    scoped, issues = _scoped_issues("helper() { printf '}'\ncd tools\n}\npython check.py\n")
    assert issues == []
    assert ("python check.py", ".") in scoped
    assert not any(scope == "tools" for _command, scope in scoped)


def test_inline_fi_before_suffix_closes_conditional_before_cd() -> None:
    scoped, issues = _scoped_issues("if true; then :; fi; echo done\ncd tools\npython check.py\n")
    assert issues == []
    assert ("python check.py", "tools") in scoped
    assert not any(command == "python check.py" and scope == "." for command, scope in scoped)


def test_inline_conditional_transition_fail_closed_is_preserved() -> None:
    _scoped, issues = _scoped_issues("if false; then cd tools; fi\npython check.py\n")
    assert issues and "directory transition" in issues[0]


def test_function_invocation_still_fails_closed() -> None:
    _scoped, issues = _scoped_issues("helper() { echo yes; }\nhelper\npython check.py\n")
    assert issues and "helper" in issues[0]


# ---------- qpx3 / qpx- (review 5841921630) ----------


def test_uncalled_function_heredoc_opener_is_never_attributed() -> None:
    run = "helper() {\n    cd tools\n    python ghost.py <<'GHOST'\ndata line\nGHOST\n}\npython check.py\n"
    scoped, issues = _scoped_issues(run)
    assert issues == []
    assert ("python check.py", ".") in scoped
    assert not any("ghost.py" in command for command, _scope in scoped)
    assert not any(scope == "tools" for _command, scope in scoped)


def test_nested_fi_suffix_is_processed_with_inherited_context() -> None:
    scoped, issues = _scoped_issues("if false; then\n    if true; then\n        :\n    fi; python check.py\nfi\n")
    assert issues == []
    assert ("python check.py", ".") in scoped


def test_nested_fi_suffix_transition_fails_closed() -> None:
    scoped, issues = _scoped_issues(
        "if false; then\n    if true; then\n        :\n    fi; cd tools\nfi\npython check.py\n"
    )
    assert not any(scope == "tools" for _command, scope in scoped)
    assert issues and "directory transition" in issues[-1]


def test_top_level_fi_suffix_transition_still_applies() -> None:
    scoped, issues = _scoped_issues("if true; then :; fi; cd tools\npython check.py\n")
    assert issues == []
    assert ("python check.py", "tools") in scoped


# ---------- v9hO / v9hd (Codex round on 296f244) ----------


def test_mid_stream_loop_header_fails_closed() -> None:
    scoped, issues = _scoped_issues("echo begin; while false; do cd tools; done\npython check.py\n")
    assert not any(scope == "tools" for _command, scope in scoped)
    assert issues and "loop control flow" in issues[0]


def test_line_leading_loop_header_fails_closed() -> None:
    _scoped, issues = _scoped_issues("while false; do cd tools; done\npython check.py\n")
    assert issues and "loop control flow" in issues[0]


def test_segment_level_fi_closes_block_conditional() -> None:
    scoped, issues = _scoped_issues("if true; then\necho done; fi\npython check.py\n")
    assert issues == []
    assert ("python check.py", ".") in scoped


def test_segment_level_fi_then_unconditional_cd_applies() -> None:
    scoped, issues = _scoped_issues("if false; then\necho done; fi; cd tools\npython check.py\n")
    assert issues == []
    assert ("python check.py", "tools") in scoped


# ---------- 2BaK / 2BaN (Codex round on a46f941) ----------


def test_prefixed_function_definition_body_is_inert() -> None:
    scoped, issues = _scoped_issues("echo begin; helper() { :; cd tools; }; python check.py\n")
    assert issues == []
    assert ("echo begin", ".") in scoped
    assert ("python check.py", ".") in scoped
    assert not any(scope == "tools" for _command, scope in scoped)


def test_prefixed_function_definition_multiline_body_is_inert() -> None:
    scoped, issues = _scoped_issues("echo begin; helper()\n{\ncd tools\n}\npython check.py\n")
    assert not any(scope == "tools" for _command, scope in scoped)
    assert ("python check.py", ".") in scoped


def test_command_wrapped_cd_applies_transition() -> None:
    scoped, issues = _scoped_issues("cd tools; command cd ..; python check.py\n")
    assert issues == []
    assert ("python check.py", ".") in scoped
    assert not any(command == "python check.py" and scope == "tools" for command, scope in scoped)


def test_command_v_lookup_stays_surface_without_transition() -> None:
    scoped, issues = _scoped_issues("command -v cd\npython check.py\n")
    assert issues == []
    assert ("python check.py", ".") in scoped


def test_unsupported_wrapper_flag_fails_closed() -> None:
    _scoped, issues = _scoped_issues("command -x cd tools\npython check.py\n")
    assert issues and "wrapper flag" in issues[0]


# ---------- 5840414479: F1/F2/F3 ----------


def test_mid_line_conditional_transition_fails_closed() -> None:
    scoped, issues = _scoped_issues("echo begin; if false; then cd tools; fi\npython check.py\n")
    assert not any(scope == "tools" for _command, scope in scoped)
    assert issues and "directory transition" in issues[0]


def test_mid_line_conditional_invocations_are_attributed() -> None:
    scoped = _scoped("echo begin; if true; then python check.py; fi\n")
    assert ("python check.py", ".") in scoped


def test_structural_close_ignores_quoted_brace_suffix() -> None:
    scoped = _scoped("helper() { :; }; python check.py --format '{}'\n")
    assert any("--format '{}'" in command for command, _scope in scoped)


def test_structural_close_ignores_quoted_x_brace_suffix() -> None:
    scoped = _scoped("helper() { :; }; python check.py --format '{x}'\n")
    assert any("--format '{x}'" in command for command, _scope in scoped)


def test_inner_fi_restores_parent_conditional_context() -> None:
    scoped, issues = _scoped_issues("if false; then\n    if true; then :; fi; cd tools\nfi\npython check.py\n")
    assert not any(scope == "tools" for _command, scope in scoped)
    assert issues and "directory transition" in issues[0]


def test_closed_top_level_conditional_still_applies_cd() -> None:
    scoped = _scoped("if true; then :; fi\ncd tools\npython check.py\n")
    assert ("python check.py", "tools") in scoped


# ---------- metamorphic: ownership must be invariant to harmless syntax ----------


def _checkpy_ownership(run: str) -> list[tuple[str, str]]:
    return [entry for entry in _scoped(run) if "check.py" in entry[0]]


def test_metamorphic_harmless_prefix_keeps_ownership() -> None:
    assert _checkpy_ownership("if true; then python check.py; fi\n") == _checkpy_ownership(
        "echo begin; if true; then python check.py; fi\n"
    )


def test_metamorphic_quoted_argument_keeps_ownership() -> None:
    plain = _scoped("python -m check\n")
    quoted = _scoped('python -m "check"\n')
    assert plain == quoted


def test_metamorphic_extra_enclosing_conditional_keeps_ownership() -> None:
    single = _checkpy_ownership("if true; then python check.py; fi\n")
    nested = _checkpy_ownership("if true; then if true; then python check.py; fi; fi\n")
    assert single == nested


# ---------- round 14 (Codex 2BaK / 2BaN): mid-stream definitions and wrapped builtins ----------


def test_mid_stream_function_definition_body_is_inert_and_suffix_runs_at_root() -> None:
    """Codex 2BaK: `echo begin; helper() { :; cd tools; }; python check.py`."""
    scoped = _scoped("echo begin; helper() { :; cd tools; }; python check.py\n")
    assert ("python check.py", ".") in scoped, "the same-line suffix runs at the ambient scope"
    assert not any(scope == "tools" for _command, scope in scoped), "the uncalled body's cd is inert"


def test_mid_stream_multiline_function_body_transfers_to_line_branch() -> None:
    """Codex 2BaK: the body may close on a later line of the same workflow."""
    scoped = _scoped("echo begin; helper() {\ncd tools\n}\npython check.py\n")
    assert ("python check.py", ".") in scoped
    assert not any(scope == "tools" for _command, scope in scoped)


def test_wrapped_builtin_transition_is_applied() -> None:
    """Codex 2BaN: `command cd ..` is a real directory transition."""
    scoped = _scoped("cd tools; command cd ..; python check.py\n")
    assert ("python check.py", ".") in scoped
    assert not any(scope == "tools" for _command, scope in scoped)


def test_builtin_lookup_is_preserved_without_transition() -> None:
    """`command -v cd` is a lookup-only invocation, never a transition."""
    scoped = _scoped("command -v cd; python check.py\n")
    assert ("python check.py", ".") in scoped


def test_unsupported_builtin_wrapper_flag_fails_closed() -> None:
    scoped, issues = _scoped_issues("command -f cd; python check.py\n")
    assert issues and "builtin wrapper flag" in issues[0]


def test_brace_aware_split_keeps_semicolons_inside_bodies_whole() -> None:
    """The definition body's own separators never split the ordered stream."""
    scoped = _scoped("helper() { printf a; printf b; }; python check.py\n")
    assert ("python check.py", ".") in scoped


def test_seeded_definition_invocation_still_fails_closed() -> None:
    """An INVOKED defined function keeps failing closed (2BaK's inert-body
    fix must not turn uncalled definitions into callable no-ops)."""
    scoped, issues = _scoped_issues("helper() { :; cd tools; }\nhelper\npython check.py\n")
    assert issues and "helper" in issues[0]


# ---------- round 15 (Codex 5omx / 5om4, review 5849719155) ----------


def test_quoted_json_argument_never_recurses_and_stays_inert() -> None:
    """Codex 5omx: a quoted '{"a":"x;y"}' argument is DATA — no structural
    group, no recursion, the invocation attributed at the ambient scope."""
    scoped, issues = _scoped_issues('python real.py --json \'{"a":"x;y"}\'\n')
    assert issues == [], f"no fail-closed issue for valid quoted data: {issues}"
    assert any(command.startswith("python real.py") for command, _scope in scoped)


def test_escaped_brace_argument_is_inert_data() -> None:
    scoped, issues = _scoped_issues('python real.py --json \'{\\"a\\":\\"x\\"}\'\n')
    assert issues == []
    assert any(command.startswith("python real.py") for command, _scope in scoped)


def test_substitution_marker_identity_across_inert_definition() -> None:
    """Codex 5om4: `f() { echo "$(python ghost.py)"; }; echo "$(python real.py)"`
    executes ONLY real.py — the skipped body's substitution can never be
    consumed by the suffix's marker (indexed markers + boundary slicing)."""
    scoped = _scoped('f() { echo "$(python ghost.py)"; }; echo "$(python real.py)"\n')
    commands = " | ".join(command for command, _scope in scoped)
    assert "real.py" in commands, "the real invocation is analyzed"
    assert "ghost.py" not in commands, "the skipped body's substitution is never analyzed"


def test_full_classifier_counts_real_not_ghost(tmp_path: Path) -> None:
    """Integration through classify_gate_sources (the public audit surface),
    not only the private scoping helper. Uses pytest's tmp_path (an already
    resolved path) — a raw tempfile path carries symlink components on
    macOS (/var -> /private/var) that the repository's fail-closed root
    discovery refuses by design."""
    from agents_md_gate_sources import classify_gate_sources
    from discover_repository import discover

    root = tmp_path
    (root / "real.py").write_text("def main() -> None:\n    pass\n", encoding="utf-8")
    ghost_dir = root / "tools"
    ghost_dir.mkdir()
    (ghost_dir / "ghost.py").write_text("def main() -> None:\n    pass\n", encoding="utf-8")
    workflow = root / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        '      - run: f() { echo "$(python tools/ghost.py)"; }; echo "$(python real.py)"\n',
        encoding="utf-8",
    )
    inventory = classify_gate_sources(root, discover(root), limit=64)
    counted = {source.path for source in inventory.sources if source.counted}
    assert "real.py" in counted, "the actually executed script is counted"
    assert "tools/ghost.py" not in counted, "the uncalled body's script is never counted"
    assert inventory.issues == ()
