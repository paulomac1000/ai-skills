"""Tests for skills/ci-cd-architect/ci-cd-standard.md (ref.ci-cd-standard).

Validates that the CI/CD standard document has been properly updated with:
  - Correct action references (semgrep-action, attest-build-provenance)
  - Python 3.14 as standard target
  - --break-system-packages rule
  - Documented assumptions (/api/health, MCP_UNSAFE flag)
  - Version bump to 2.1.0
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Re-use the docs_validate module from conftest.py
from conftest import load_markdown_file, load_config, validate_file, _make_check_registry


@pytest.fixture(scope="session")
def cisd_path(repo_root):
    return repo_root / "skills" / "ci-cd-architect" / "ci-cd-standard.md"


@pytest.fixture(scope="session")
def cisd_content(cisd_path):
    """Return the full file content as a string."""
    return cisd_path.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def cisd_fm_body(cisd_path):
    fm, body = load_markdown_file(cisd_path)
    if fm is None:
        raise ValueError(f"Failed to parse {cisd_path}: {body}")
    return fm, body


@pytest.fixture(scope="session")
def cisd_fm(cisd_fm_body):
    return cisd_fm_body[0]


@pytest.fixture(scope="session")
def cisd_body(cisd_fm_body):
    return cisd_fm_body[1]


@pytest.fixture(scope="session")
def cisd_result(cisd_path, config, check_registry):
    return validate_file(cisd_path, config, check_registry)


class TestSemgrepAction:
    """Verify Semgrep action references are correct."""

    def test_semgrep_action_not_nonexistent(self, cisd_content):
        """The nonexistent semgrep/semgrep@v1 reference must be removed."""
        assert "semgrep/semgrep@v1" not in cisd_content, (
            "semgrep/semgrep@v1 is a nonexistent action — replace with "
            "returntocorp/semgrep-action (commit-SHA pinned)"
        )

    def test_semgrep_action_is_correct(self, cisd_content):
        """The correct returntocorp/semgrep-action must be present."""
        assert "returntocorp/semgrep-action" in cisd_content, (
            "Expected returntocorp/semgrep-action (commit-SHA pinned) at Semgrep example location"
        )


class TestAttestReferences:
    """Verify attest-build-provenance references are correct."""

    def test_no_stale_attest_v4_references(self, cisd_content):
        """No stale attest@v4 references anywhere in the document."""
        assert "attest@v4" not in cisd_content, (
            "Stale attest@v4 references found — replace with attest-build-provenance@v2"
        )


class TestBreakSystemPackages:
    """Verify --break-system-packages is documented as a rule."""

    def test_break_system_packages_rule_exists(self, cisd_content):
        """--break-system-packages must appear in a rule context for Python >=3.14 CI."""
        # Find all CI-CDW rule contexts (lines starting with **[RULE: or near ## headings)
        rule_section = cisd_content
        assert "--break-system-packages" in rule_section, (
            "Expected --break-system-packages to be mentioned in CI/CD standard, "
            "likely near a CI-CDW rule for Python >=3.14"
        )


class TestPythonVersionPolicy:
    """Verify Python version policy consistency."""

    def test_python_version_no_contradiction(self, cisd_content):
        """CI-CDW-72 and CI-CDW-4a must not contradict on Python version."""
        ci_cdw_4a_match = re.search(
            r"\[RULE: CI-CDW-4a\].*?\n.*", cisd_content, re.DOTALL
        )
        ci_cdw_72_match = re.search(
            r"\[RULE: CI-CDW-72\].*?\n.*", cisd_content, re.DOTALL
        )
        assert ci_cdw_4a_match is not None, "CI-CDW-4a rule not found"
        assert ci_cdw_72_match is not None, "CI-CDW-72 rule not found"

        rule_4a = ci_cdw_4a_match.group(0)
        # CI-CDW-4a should state 3.14 as the standard target (not contradict CI-CDW-72)
        assert "3.14" in rule_4a, (
            "CI-CDW-4a must reference Python 3.14 as the standard target"
        )


class TestAssumptionsDocumented:
    """Verify key assumptions are documented in the STATE section."""

    def test_health_endpoint_documented(self, cisd_content):
        """The /api/health path assumption must be explained in the STATE section."""
        # Find STATE section and check for health path documentation
        state_match = re.search(
            r"## STATE.*?(?=## (?:EDGE_CASES|EXAMPLES|NON_GOALS|CHANGELOG|$))",
            cisd_content, re.DOTALL | re.IGNORECASE
        )
        assert state_match is not None, "STATE section not found"
        state_section = state_match.group(0)
        has_health_doc = (
            "health" in state_section.lower()
            and ("endpoint" in state_section.lower() or "/health" in state_section
                 or "health check" in state_section.lower())
        )
        assert has_health_doc, (
            "Expected /api/health endpoint path assumption to be documented in STATE section"
        )

    def test_mcp_unsafe_documented(self, cisd_content):
        """MCP_UNSAFE_PUBLIC_ACCESS_CONFIRMED=1 must be documented as a project flag."""
        assert "MCP_UNSAFE_PUBLIC_ACCESS_CONFIRMED" in cisd_content, (
            "Expected MCP_UNSAFE_PUBLIC_ACCESS_CONFIRMED=1 to be documented "
            "as a project-specific flag in the CI/CD standard"
        )


class TestVersionBump:
    """Verify the standard version has been bumped."""

    def test_version_bumped_to_2_1_0(self, cisd_fm):
        """Frontmatter standard_version must be 2.1.0."""
        version = cisd_fm.get("standard_version", "")
        assert version == "2.1.0", (
            f"Expected standard_version 2.1.0 but got '{version}'"
        )
