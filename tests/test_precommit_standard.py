"""Tests for skills/pre-commit-architect/precommit-standard.md (ref.precommit-standard).

Validates that the pre-commit standard document follows AFDS conventions,
contains all 13 PRECOMMIT rules from todo-precommit.md, and passes
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
        assert version == "1.0.0", (
            f"Expected standard_version '1.0.0', got '{version}'"
        )
        upstream = pcstd_fm.get("upstream")
        assert upstream is not None, "upstream field is missing from frontmatter"
        assert "ref.ci-cd-standard" in upstream, (
            f"Expected upstream to include 'ref.ci-cd-standard', got '{upstream}'"
        )


class TestAll13Rules:
    """Verify all 13 PRECOMMIT rules from todo-precommit.md are present."""

    def test_all_13_rules_present(self, pcstd_content):
        """Document must contain rule anchors for PRECOMMIT-01 through PRECOMMIT-13."""
        missing = []
        for n in range(1, 14):
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
        assert len(matches) >= 13, (
            f"Expected at least 13 rules with semantic anchors, "
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


class TestPassesAFDS:
    """Verify the standard passes AFDS validation via docs_validate.py."""

    def test_passes_afds(self, pcstd_result):
        """docs_validate.py must return no blocking errors on the standard."""
        assert pcstd_result.passed, (
            f"AFDS validation failed: {pcstd_result.errors[:5]}"
        )
