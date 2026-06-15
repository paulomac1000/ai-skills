"""Tests for skills/pre-commit-architect/precommit-standard.md (ref.precommit-standard).

Validates that the pre-commit standard document follows AFDS conventions,
contains all 15 PRECOMMIT rules from precommit-standard.md (v1.1.0, 2026-06-14), and passes
docs_validate.py validation.
"""

import re
from pathlib import Path

import pytest

from conftest import load_markdown_file, validate_file

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def pcstd_path(repo_root):
    return repo_root / "skills" / "pre-commit-architect" / "precommit-standard.md"


@pytest.fixture(scope="session")
def pcstd_content(pcstd_path):
    """Return the full file content as a string."""
    return pcstd_path.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def pcstd_fm_body(pcstd_path):
    fm, body = load_markdown_file(pcstd_path)
    if fm is None:
        raise ValueError(f"Failed to parse {pcstd_path}: {body}")
    return fm, body


@pytest.fixture(scope="session")
def pcstd_fm(pcstd_fm_body):
    return pcstd_fm_body[0]


@pytest.fixture(scope="session")
def pcstd_body(pcstd_fm_body):
    return pcstd_fm_body[1]


@pytest.fixture(scope="session")
def pcstd_result(pcstd_path, config, check_registry):
    return validate_file(pcstd_path, config, check_registry)


class TestFrontmatter:
    """Verify frontmatter fields are present and correct per AFDS spec."""

    def test_frontmatter_valid(self, pcstd_fm):
        """Frontmatter must have doc_id, type, standard_version, and upstream."""
        assert pcstd_fm.get("doc_id") == "ref.precommit-standard", (
            f"Expected doc_id 'ref.precommit-standard', got '{pcstd_fm.get('doc_id')}'"
        )
        assert pcstd_fm.get("type") == "ref", (
            f"Expected type 'ref', got '{pcstd_fm.get('type')}'"
        )
        version = pcstd_fm.get("standard_version")
        assert version is not None, "standard_version is missing from frontmatter"
        assert version == "1.1.0", (
            f"Expected standard_version '1.1.0', got '{version}'"
        )
        upstream = pcstd_fm.get("upstream")
        assert upstream is not None, "upstream field is missing from frontmatter"
        assert "ref.ci-cd-standard" in upstream, (
            f"Expected upstream to include 'ref.ci-cd-standard', got '{upstream}'"
        )


class TestAllNRules:
    """Verify all N PRECOMMIT rules (15 in v1.1.0) are present in the standard."""

    def test_all_n_rules_present(self, pcstd_content):
        """Document must contain rule anchors for PRECOMMIT-01 through PRECOMMIT-N (currently 15)."""
        missing = []
        for n in range(1, 16):
            rule_id = f"PRECOMMIT-{n:02d}"
            if rule_id not in pcstd_content:
                missing.append(rule_id)
        assert not missing, (
            f"Missing rule anchors: {', '.join(missing)}"
        )


class TestRuleAnchors:
    """Verify each rule uses the semantic anchor format."""

    def test_rules_have_semantic_anchors(self, pcstd_content):
        """Each rule must follow the **[RULE: PRECOMMIT-NN] [L1+/L2+]** format."""
        pattern = re.compile(r"\[RULE: PRECOMMIT-\d{2}\] \[L[12]\+?\]")
        matches = pattern.findall(pcstd_content)
        assert len(matches) >= 15, (
            f"Expected at least 15 rules with semantic anchors, "
            f"found {len(matches)}: {matches}"
        )


class TestSectionStructure:
    """Verify document has the required structural sections."""

    def test_section_structure_complete(self, pcstd_content):
        """Document must contain PURPOSE, SCOPE, RULES, STATE, and CHANGELOG sections."""
        required_sections = ["PURPOSE", "SCOPE", "RULES", "STATE", "CHANGELOG"]
        missing = []
        for section in required_sections:
            pattern = re.compile(rf"^##\s+{section}\b", re.MULTILINE)
            if not pattern.search(pcstd_content):
                missing.append(section)
        assert not missing, (
            f"Missing required sections (expected '## SECTION'): {', '.join(missing)}"
        )


class TestCIMirroring:
    """Verify PRECOMMIT-01 enforces CI lint+test mirroring."""

    def test_ci_mirroring_rule(self, pcstd_content):
        """PRECOMMIT-01 must reference CI linting and testing mirroring."""
        match = re.search(
            r"\[RULE: PRECOMMIT-01\].*?\n"
            r"((?:(?!\[RULE: PRECOMMIT-\d{2}\]).*\n?)*)",
            pcstd_content,
        )
        assert match is not None, "PRECOMMIT-01 rule not found"
        rule_text = match.group(1)
        has_ci = "CI" in rule_text
        has_mirror = any(t in rule_text.lower() for t in ("mirror", "same", "lint"))
        assert has_ci and has_mirror, (
            f"PRECOMMIT-01 must reference CI lint/test mirroring. "
            f"Found text: {rule_text[:200].strip()}"
        )


class TestHookOrdering:
    """Verify PRECOMMIT-02 defines hook ordering chain."""

    def test_hook_ordering_rule(self, pcstd_content):
        """PRECOMMIT-02 must define the hook ordering chain."""
        match = re.search(
            r"\[RULE: PRECOMMIT-02\].*?\n"
            r"((?:(?!\[RULE: PRECOMMIT-\d{2}\]).*\n?)*)",
            pcstd_content,
        )
        assert match is not None, "PRECOMMIT-02 rule not found"
        rule_text = match.group(1)
        ordering_terms = ["generic", "lint", "format", "types", "security", "docs", "tests"]
        found = [t for t in ordering_terms if t in rule_text.lower()]
        assert len(found) >= 7, (
            f"PRECOMMIT-02 must define the hook ordering chain "
            f"(generic→lint→format→types→security→docs→tests). "
            f"Found {len(found)}/7 terms: {found}. Text: {rule_text[:300].strip()}"
        )


class TestFailFast:
    """Verify PRECOMMIT-06 requires fail_fast: false."""

    def test_fail_fast_rule(self, pcstd_content):
        """PRECOMMIT-06 must require all hooks to use fail_fast: false."""
        match = re.search(
            r"\[RULE: PRECOMMIT-06\].*?\n"
            r"((?:(?!\[RULE: PRECOMMIT-\d{2}\]).*\n?)*)",
            pcstd_content,
        )
        assert match is not None, "PRECOMMIT-06 rule not found"
        rule_text = match.group(1)
        assert "fail_fast" in rule_text, (
            f"PRECOMMIT-06 must mention fail_fast. Text: {rule_text[:200].strip()}"
        )
        assert "false" in rule_text.lower(), (
            f"PRECOMMIT-06 must require fail_fast: false. Text: {rule_text[:200].strip()}"
        )


class TestPython3Entry:
    """Verify PRECOMMIT-05 requires python3 in entry commands."""

    def test_python3_entry_rule(self, pcstd_content):
        """PRECOMMIT-05 must use python3, not python, in all entry commands."""
        match = re.search(
            r"\[RULE: PRECOMMIT-05\].*?\n"
            r"((?:(?!\[RULE: PRECOMMIT-\d{2}\]).*\n?)*)",
            pcstd_content,
        )
        assert match is not None, "PRECOMMIT-05 rule not found"
        rule_text = match.group(1)
        assert "python3" in rule_text, (
            f"PRECOMMIT-05 must require python3 (not python) in entry commands. "
            f"Text: {rule_text[:200].strip()}"
        )


class TestMypyOverrides:
    """Verify PRECOMMIT-11 requires [[tool.mypy.overrides]]."""

    def test_mypy_overrides_rule(self, pcstd_content):
        """PRECOMMIT-11 must require [[tool.mypy.overrides]] for all third-party deps."""
        match = re.search(
            r"\[RULE: PRECOMMIT-11\].*?\n"
            r"((?:(?!\[RULE: PRECOMMIT-\d{2}\]).*\n?)*)",
            pcstd_content,
        )
        assert match is not None, "PRECOMMIT-11 rule not found"
        rule_text = match.group(1)
        has_overrides = (
            "overrides" in rule_text.lower()
            or "[[tool.mypy.overrides]]" in rule_text
            or "mypy" in rule_text.lower()
        )
        assert has_overrides, (
            f"PRECOMMIT-11 must reference [[tool.mypy.overrides]] for "
            f"third-party dependency typing. Text: {rule_text[:200].strip()}"
        )




class TestSecretScanning:
    """Verify PRECOMMIT-14 requires secret scanning tools."""

    def test_secret_scanning_rule(self, pcstd_content):
        """PRECOMMIT-14 must require secret scanning tools (detect-private-key, gitleaks, or detect-secrets)."""
        match = re.search(
            r"\[RULE: PRECOMMIT-14\].*?\n"
            r"((?:(?!\[RULE: PRECOMMIT-\d{2}\]).*\n?)*)",
            pcstd_content,
        )
        assert match is not None, "PRECOMMIT-14 rule not found"
        rule_text = match.group(1)
        secret_terms = ["detect-private-key", "gitleaks", "detect-secrets", "secret"]
        found = [t for t in secret_terms if t.lower() in rule_text.lower()]
        assert len(found) >= 1, (
            f"PRECOMMIT-14 must require secret scanning tools. "
            f"Found {len(found)} terms: {found}. Text: {rule_text[:300].strip()}"
        )

    def test_precommit_14_content_not_collection_error(self, pcstd_content):
        """PRECOMMIT-14 must NOT be about test collection (which is PRECOMMIT-13's job)."""
        match = re.search(
            r"\[RULE: PRECOMMIT-14\].*?\n"
            r"((?:(?!\[RULE: PRECOMMIT-\d{2}\]).*\n?)*)",
            pcstd_content,
        )
        assert match is not None, "PRECOMMIT-14 rule not found"
        rule_text = match.group(1).lower()
        forbidden_terms = ["fastmcp", "test_server.py", "pytest --collect-only", "importerror"]
        present = [t for t in forbidden_terms if t in rule_text]
        assert not present, (
            f"PRECOMMIT-14 must not be about test collection. "
            f"Found forbidden terms: {present}. Text: {rule_text[:300].strip()}"
        )


class TestCustomScripts:
    """Verify PRECOMMIT-15 defines custom local validation script conventions."""

    def test_custom_scripts_rule(self, pcstd_content):
        """PRECOMMIT-15 must define conventions: scripts/ dir, python3, fail_fast, pass_filenames."""
        match = re.search(
            r"\[RULE: PRECOMMIT-15\].*?\n"
            r"((?:(?!\[RULE: PRECOMMIT-\d{2}\]).*\n?)*)",
            pcstd_content,
        )
        assert match is not None, "PRECOMMIT-15 rule not found"
        rule_text = match.group(1)
        required_terms = ["scripts/", "python3", "fail_fast", "pass_filenames"]
        missing = [t for t in required_terms if t not in rule_text]
        assert not missing, (
            f"PRECOMMIT-15 must define custom script conventions. "
            f"Missing: {', '.join(missing)}. Text: {rule_text[:300].strip()}"
        )


class TestExternalReferences:
    """Verify the standard cites canonical pre-commit references instead of duplicating them."""

    def test_precommit_canonical_url_in_definitions(self, pcstd_content):
        """DEFINITIONS section must reference https://pre-commit.com/ as canonical upstream."""
        match = re.search(r"## DEFINITIONS(.*?)(?=\n##\s)", pcstd_content, re.DOTALL)
        assert match is not None, "DEFINITIONS section not found"
        defs_text = match.group(1)
        assert "https://pre-commit.com/" in defs_text, (
            f"DEFINITIONS must reference canonical pre-commit URL "
            f"(https://pre-commit.com/). Text: {defs_text[:300].strip()}"
        )

    def test_v110_changelog_mentions_external_references(self, pcstd_content):
        """v1.1.0 changelog must mention external reference integration or the canonical URL."""
        match = re.search(r"###\s*\[1\.1\.0\].*?(?=\n###\s|\Z)", pcstd_content, re.DOTALL)
        assert match is not None, "v1.1.0 changelog entry not found"
        entry_text = match.group(0)
        assert (
            "https://pre-commit.com/" in entry_text
            or "instead of duplicating" in entry_text.lower()
        ), (
            f"v1.1.0 changelog must mention external references. "
            f"Text: {entry_text[:300].strip()}"
        )


class TestPassesAFDS:
    """Verify the standard passes AFDS validation via docs_validate.py."""

    def test_passes_afds(self, pcstd_result):
        """docs_validate.py must return no blocking errors on the standard."""
        assert pcstd_result.passed, (
            f"AFDS validation failed: {pcstd_result.errors[:5]}"
        )
"""New test classes for production fixes — to be appended to test_precommit_standard.py.

These 6 classes cover:
- TestShellTemplate
- TestAfdsNamingConsistency
- TestAgentsMdConstraint
- TestDornyMarocchinoInCiTemplate
- TestSonarQubeInDotnetTemplate
- TestPipeToPythonMitigated
"""


class TestShellTemplate:
    """Verify `pre-commit-shell.j2` exists, parses as Jinja2, and supports 4 languages.

    This template is the native bash `.githooks/pre-commit` (no pre-commit
    framework) variant for .NET, Rust, Go, and Python projects.
    """

    @pytest.fixture(scope="class")
    def shell_template_path(self, repo_root):
        return repo_root / "skills" / "pre-commit-architect" / "templates" / "pre-commit-shell.j2"

    @pytest.fixture(scope="class")
    def shell_template_content(self, shell_template_path):
        return shell_template_path.read_text(encoding="utf-8")

    def test_shell_template_exists(self, shell_template_path):
        """The shell template file MUST exist at the canonical location."""
        assert shell_template_path.exists(), (
            f"Shell template not found at {shell_template_path}"
        )
        assert shell_template_path.is_file(), (
            f"Path {shell_template_path} is not a file"
        )

    def test_shell_template_parses_as_jinja2(self, shell_template_path):
        """The shell template MUST parse as a valid Jinja2 template."""
        import jinja2
        source = shell_template_path.read_text(encoding="utf-8")
        env = jinja2.Environment()
        # Should not raise TemplateSyntaxError
        env.parse(source)

    @pytest.mark.parametrize("language", ["dotnet", "rust", "go", "python"])
    def test_shell_template_has_language_branch(self, shell_template_content, language):
        """The shell template MUST define a `case "$LANGUAGE" in {language})` branch for each supported language."""
        # Look for a `case "$LANGUAGE" in` line followed by `<language>)` within 400 chars
        pattern = rf'case\s+"\$LANGUAGE"\s+in[\s\S]{{0,400}}\b{language}\)'
        assert re.search(pattern, shell_template_content), (
            f"Shell template must define a `case \"$LANGUAGE\" in {language})` branch"
        )

    def test_shell_template_has_format_check(self, shell_template_content):
        """The shell template MUST include a format check section."""
        assert "Format" in shell_template_content, (
            "Shell template must include a format check section"
        )
        # Verify it's a labeled check (Check 1: Format)
        assert re.search(r"Check\s+1:\s*Format", shell_template_content), (
            "Shell template must include a labeled format check (`Check 1: Format`)"
        )

    def test_shell_template_has_compile_check(self, shell_template_content):
        """The shell template MUST include a compile/syntax check section."""
        assert re.search(r"Compile\s*/\s*syntax", shell_template_content, re.IGNORECASE), (
            "Shell template must include a compile/syntax check section"
        )
        assert re.search(r"Check\s+2:", shell_template_content), (
            "Shell template must label compile/syntax as Check 2"
        )

    def test_shell_template_has_merge_conflict_check(self, shell_template_content):
        """The shell template MUST include a merge-conflict-markers check."""
        assert "Merge conflict" in shell_template_content, (
            "Shell template must include a merge conflict markers check"
        )
        # Also verify it actually greps for the conflict markers
        assert "<<<<<<<" in shell_template_content, (
            "Merge conflict check must actually grep for `<<<<<<<` markers"
        )

    def test_shell_template_has_private_key_check(self, shell_template_content):
        """The shell template MUST include a private-key/secret scan check (PRECOMMIT-14)."""
        assert "Private key" in shell_template_content, (
            "Shell template must include a private key/secret scan check"
        )
        # Verify it actually matches the BEGIN PRIVATE KEY pattern
        assert "BEGIN" in shell_template_content and "PRIVATE" in shell_template_content, (
            "Private key check must match `-----BEGIN ... PRIVATE KEY-----` blocks"
        )

    def test_shell_template_has_installation_instruction(self, shell_template_content):
        """The shell template MUST document `git config --local core.hooksPath` as the install instruction."""
        assert "git config --local core.hooksPath" in shell_template_content, (
            "Shell template must document `git config --local core.hooksPath .githooks` "
            "as the install instruction"
        )


class TestAfdsNamingConsistency:
    """Verify ZERO `CAFDS` occurrences in source files (production fix for naming bug).

    The "AFDS" (AI-First Documentation Standard) was originally typed as "CAFDS"
    in some files; all such references must be purged from canonical source files.
    """

    @pytest.fixture(scope="class")
    def target_files(self, repo_root):
        return [
            repo_root / "skills" / "mcp-server-architect" / "SKILL.md",
            repo_root / "skills" / "pre-commit-architect" / "precommit-standard.md",
            repo_root / "skills" / "pre-commit-architect" / "references" / "pitfalls.md",
            repo_root / "skills" / "ci-cd-architect" / "ci-cd-standard.md",
            repo_root / "decisions" / "decision.007-precommit-architect.md",
        ]

    @pytest.mark.parametrize("idx", list(range(5)))
    def test_no_cafds_substring(self, target_files, idx):
        """No file may contain the 'CAFDS' substring (case-sensitive)."""
        path = target_files[idx]
        content = path.read_text(encoding="utf-8")
        assert "CAFDS" not in content, (
            f"{path.name} contains the forbidden 'CAFDS' substring "
            f"(should be 'AFDS'). Found {content.count('CAFDS')} occurrence(s)."
        )

    @pytest.mark.parametrize("idx", list(range(5)))
    def test_no_cafds_hook_id_prefix(self, target_files, idx):
        """No file may contain a hook id with the 'cafds-' prefix (case-insensitive)."""
        path = target_files[idx]
        content = path.read_text(encoding="utf-8")
        # Look for hook id patterns: `id: cafds-...` or `id: "cafds-..."` (case-insensitive)
        matches = re.findall(
            r"\bid\s*:\s*[\"']?(cafds-[\w-]+)",
            content,
            re.IGNORECASE,
        )
        assert not matches, (
            f"{path.name} contains forbidden 'cafds-' hook id prefix(es): {matches}"
        )

    @pytest.mark.parametrize("idx", list(range(5)))
    def test_no_cortexa_reference(self, target_files, idx):
        """No file may contain a 'Cortexa' reference (forbidden term)."""
        path = target_files[idx]
        content = path.read_text(encoding="utf-8")
        assert "Cortexa" not in content, (
            f"{path.name} contains the forbidden 'Cortexa' reference. "
            f"Found {content.count('Cortexa')} occurrence(s)."
        )


class TestAgentsMdConstraint:
    """Verify SKILL.md includes the explicit constraint preventing hallucinated hooks in AGENTS.md.

    The pre-commit-architect SKILL.md MUST include the constraint that the
    hook summary table in AGENTS.md must NOT add hooks not present in the
    generated `.pre-commit-config.yaml`. This prevents the LLM from inventing
    hook IDs that don't exist.
    """

    @pytest.fixture(scope="class")
    def precommit_skill_path(self, repo_root):
        return repo_root / "skills" / "pre-commit-architect" / "SKILL.md"

    @pytest.fixture(scope="class")
    def precommit_skill_content(self, precommit_skill_path):
        return precommit_skill_path.read_text(encoding="utf-8")

    def test_constraint_block_present(self, precommit_skill_content):
        """SKILL.md MUST contain the constraint text preventing hallucinated hooks."""
        expected = "Do NOT add hooks not present in the generated file"
        assert expected in precommit_skill_content, (
            f"SKILL.md must contain the constraint: '{expected}'"
        )

    def test_constraint_near_agents_md_template(self, precommit_skill_content):
        """The constraint MUST be located near the AGENTS.md generation template (around line 194)."""
        lines = precommit_skill_content.splitlines()
        match_line = None
        for i, line in enumerate(lines):
            if "Do NOT add hooks not present in the generated file" in line:
                match_line = i + 1
                break
        assert match_line is not None, "Constraint phrase not found in SKILL.md"
        # The AGENTS.md generation template starts at the "## Pre-commit Hooks" section
        # in Workflow 2. The constraint is the last line of that block. Allow ±30 line window.
        assert 160 < match_line < 250, (
            f"Constraint appears at line {match_line}, expected to be near the "
            f"AGENTS.md generation template (lines 160-250)"
        )


class TestDornyMarocchinoInCiTemplate:
    """Verify ci.yml.j2 includes test-reporter and sticky-pull-request-comment with correct permissions.

    Production fix: ci.yml.j2 was missing the dorny/test-reporter and
    marocchino/sticky-pull-request-comment actions, and the test job lacked
    `pull-requests: write` permission. This caused PR feedback to fail silently
    with 403 errors. See CI-CDW-68a in ci-cd-standard.md.
    """

    @pytest.fixture(scope="class")
    def ci_template_path(self, repo_root):
        return repo_root / "skills" / "ci-cd-architect" / "templates" / "ci.yml.j2"

    @pytest.fixture(scope="class")
    def ci_template_content(self, ci_template_path):
        return ci_template_path.read_text(encoding="utf-8")

    def test_dorny_test_reporter_with_sha(self, ci_template_content):
        """ci.yml.j2 MUST include `dorny/test-reporter@<40-char-sha>` (SHA-pinned, CI-CDW-73)."""
        pattern = r"dorny/test-reporter@[a-f0-9]{40}"
        match = re.search(pattern, ci_template_content)
        assert match is not None, (
            f"ci.yml.j2 must include `dorny/test-reporter@<40-char-sha>`. "
            f"Found: {re.findall(r'dorny/test-reporter@\\S+', ci_template_content)}"
        )

    def test_marocchino_sticky_pull_request_comment_with_sha(self, ci_template_content):
        """ci.yml.j2 MUST include `marocchino/sticky-pull-request-comment@<40-char-sha>`."""
        pattern = r"marocchino/sticky-pull-request-comment@[a-f0-9]{40}"
        match = re.search(pattern, ci_template_content)
        assert match is not None, (
            f"ci.yml.j2 must include `marocchino/sticky-pull-request-comment@<40-char-sha>`. "
            f"Found: {re.findall(r'marocchino/sticky-pull-request-comment@\\S+', ci_template_content)}"
        )

    def test_test_job_has_pull_requests_write_permission(self, ci_template_content):
        """The test job MUST have `permissions: pull-requests: write` (CI-CDW-68a)."""
        # Find the test: job definition (indented with 2 spaces)
        lines = ci_template_content.splitlines()
        test_line_idx = None
        for i, line in enumerate(lines):
            if re.match(r"^\s{2}test:\s*$", line):
                test_line_idx = i
                break
        assert test_line_idx is not None, "test: job definition not found in ci.yml.j2"
        # Look ahead 25 lines for the permissions block
        lookahead = "\n".join(lines[test_line_idx:test_line_idx + 25])
        assert "permissions:" in lookahead, (
            f"test: job must declare `permissions:` within its first 25 lines. "
            f"Found:\n{lookahead[:500]}"
        )
        assert "pull-requests: write" in lookahead, (
            f"test: job must include `pull-requests: write` permission. "
            f"Found:\n{lookahead[:500]}"
        )


class TestSonarQubeInDotnetTemplate:
    """Verify dotnet-ci.yml.j2 includes the SonarQube job gated by use_sonarqube flag.

    Production fix: the .NET CI variant must support an opt-in SonarQube job
    that runs the begin → build → end dance with the .NET scanner and waits
    for the SonarQube quality gate. The job requires `pull-requests: write`
    permission for status reporting back to PRs.
    """

    @pytest.fixture(scope="class")
    def dotnet_template_path(self, repo_root):
        return repo_root / "skills" / "ci-cd-architect" / "templates" / "dotnet-ci.yml.j2"

    @pytest.fixture(scope="class")
    def dotnet_template_content(self, dotnet_template_path):
        return dotnet_template_path.read_text(encoding="utf-8")

    def test_sonarqube_job_gated_by_use_sonarqube(self, dotnet_template_content):
        """The sonarqube job MUST be gated by `{% if use_sonarqube %}`."""
        # Match `{% if use_sonarqube %}` (allow whitespace variations)
        if_pattern = r"\{%\s*if\s+use_sonarqube\s*%\}"
        assert re.search(if_pattern, dotnet_template_content), (
            "dotnet-ci.yml.j2 must gate the sonarqube job with `{% if use_sonarqube %}`"
        )
        # The sonarqube: job definition must exist
        assert re.search(r"^\s{2}sonarqube:\s*$", dotnet_template_content, re.MULTILINE), (
            "dotnet-ci.yml.j2 must define a `sonarqube:` job"
        )
        # And it must end with a matching `{% endif %}`
        if_match = re.search(if_pattern, dotnet_template_content)
        endif_match = re.search(r"\{%\s*endif\s*%\}", dotnet_template_content[if_match.end():])
        assert endif_match is not None, (
            "sonarqube job must be closed with `{% endif %}`"
        )

    def test_sonarqube_quality_gate_action_with_sha(self, dotnet_template_content):
        """The SonarQube job MUST use SonarSource/sonarqube-quality-gate-action pinned to SHA."""
        pattern = r"SonarSource/sonarqube-quality-gate-action@[a-f0-9]{40}"
        assert re.search(pattern, dotnet_template_content), (
            "dotnet-ci.yml.j2 must include `SonarSource/sonarqube-quality-gate-action@<40-char-sha>`"
        )

    def test_sonarscanner_begin_and_end(self, dotnet_template_content):
        """The SonarQube job MUST call `dotnet sonarscanner begin` and `dotnet sonarscanner end`."""
        assert "dotnet sonarscanner begin" in dotnet_template_content, (
            "dotnet-ci.yml.j2 must include `dotnet sonarscanner begin`"
        )
        assert "dotnet sonarscanner end" in dotnet_template_content, (
            "dotnet-ci.yml.j2 must include `dotnet sonarscanner end`"
        )

    def test_sonarqube_job_has_pull_requests_write_permission(self, dotnet_template_content):
        """The sonarqube job MUST have `permissions: pull-requests: write` (CI-CDW-68a)."""
        # Find the sonarqube: job block (between {% if use_sonarqube %} and {% endif %})
        if_match = re.search(
            r"\{%\s*if\s+use_sonarqube\s*%\}(.*?)\{%\s*endif\s*%\}",
            dotnet_template_content,
            re.DOTALL,
        )
        assert if_match is not None, "sonarqube job block not found"
        sonarqube_block = if_match.group(1)
        assert "permissions:" in sonarqube_block, (
            "sonarqube job must declare `permissions:` block"
        )
        assert "pull-requests: write" in sonarqube_block, (
            "sonarqube job must include `pull-requests: write` permission"
        )


class TestPipeToPythonMitigated:
    """Verify all docs_validate.py curl URLs are SHA-pinned (no mutable `main` branch).

    Production fix: 4 files contained `curl ... | python3 -` patterns that
    downloaded docs_validate.py from `raw.githubusercontent.com/.../main/...`
    (mutable branch). All references must use the SHA-pinned URL:

        https://raw.githubusercontent.com/paulomac1000/ai-skills/
            a1b15016df18479027b2064949a3cba1658b6c63/
            skills/afds-doc-writer/docs_validate.py
    """

    PINNED_SHA = "a1b15016df18479027b2064949a3cba1658b6c63"
    MUTABLE_BRANCH = "raw.githubusercontent.com/paulomac1000/ai-skills/main/"
    PINNED_URL = (
        f"raw.githubusercontent.com/paulomac1000/ai-skills/{PINNED_SHA}/"
        f"skills/afds-doc-writer/docs_validate.py"
    )

    @pytest.fixture(scope="class")
    def target_files(self, repo_root):
        return [
            repo_root / "skills" / "pre-commit-architect" / "templates" / "pre-commit-python.j2",
            repo_root / "skills" / "pre-commit-architect" / "templates" / "pre-commit-mcp.j2",
            repo_root / "skills" / "ci-cd-architect" / "templates" / "ci.yml.j2",
            repo_root / "skills" / "ci-cd-architect" / "ci-cd-standard.md",
        ]

    @pytest.mark.parametrize("idx", list(range(4)))
    def test_pinned_sha_url_present(self, target_files, idx):
        """Each file MUST contain the SHA-pinned docs_validate.py URL."""
        path = target_files[idx]
        content = path.read_text(encoding="utf-8")
        assert self.PINNED_URL in content, (
            f"{path.name} must contain the SHA-pinned URL: {self.PINNED_URL}"
        )

    @pytest.mark.parametrize("idx", list(range(4)))
    def test_no_mutable_main_branch(self, target_files, idx):
        """Each file MUST NOT contain the mutable `main` branch URL."""
        path = target_files[idx]
        content = path.read_text(encoding="utf-8")
        assert self.MUTABLE_BRANCH not in content, (
            f"{path.name} contains the mutable `main` branch URL: {self.MUTABLE_BRANCH}. "
            f"Use the SHA-pinned URL instead: {self.PINNED_URL}"
        )
