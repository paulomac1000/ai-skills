"""Provider claim matching binds adoption selectors to canonical JUnit result bindings."""

from contracts.evidence import GitHubEvidenceVerifier


def _report(identity: str, *, status: str = "passed") -> dict[str, object]:
    return {
        "claims": [
            {
                "kind": "rule",
                "subject": "mcp.authorization.server-side",
                "result": "passed",
                "command_digest": "sha256:" + "a" * 64,
                "result_bindings": [
                    {
                        "result_path": "repository-junit.xml",
                        "result_digest": "sha256:" + "b" * 64,
                        "test_cases": [{"identity": identity, "status": status}],
                    }
                ],
            }
        ]
    }


def _expected(test_case: str) -> dict[str, str]:
    return {
        "kind": "rule",
        "subject": "mcp.authorization.server-side",
        "result": "passed",
        "command_digest": "sha256:" + "a" * 64,
        "test_case": test_case,
    }


def test_expected_pytest_case_matches_canonical_writer_junit_binding() -> None:
    assert GitHubEvidenceVerifier._claim_matches(
        _report("tests.test_rule::test_rule"),
        _expected("tests/test_rule.py::test_rule"),
    )


def test_wrong_or_nonpassing_junit_case_cannot_satisfy_adoption_claim() -> None:
    expected = _expected("tests/test_rule.py::test_rule")
    assert not GitHubEvidenceVerifier._claim_matches(
        _report("tests.test_rule::test_other"),
        expected,
    )
    assert not GitHubEvidenceVerifier._claim_matches(
        _report("tests.test_rule::test_rule", status="skipped"),
        expected,
    )


def test_claim_without_test_case_keeps_exact_field_matching() -> None:
    expected = _expected("tests/test_rule.py::test_rule")
    del expected["test_case"]
    assert GitHubEvidenceVerifier._claim_matches(
        _report("tests.test_rule::test_other"),
        expected,
    )
