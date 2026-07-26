from __future__ import annotations

import json
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    source = target.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one match, found {count}")
    target.write_text(source.replace(old, new), encoding="utf-8", newline="\n")


def replace_count(path: str, old: str, new: str, expected: int) -> None:
    target = Path(path)
    source = target.read_text(encoding="utf-8")
    count = source.count(old)
    if count != expected:
        raise SystemExit(f"{path}: expected {expected} matches, found {count}")
    target.write_text(source.replace(old, new), encoding="utf-8", newline="\n")


replace_once(
    "contracts/evidence.py",
    '''        raw_results = report.get("results")
        if not isinstance(raw_results, list) or not raw_results:
            errors.append("evidence report has no machine result files")
            result_digests: set[str] = set()
            passed_cases: set[str] = set()
        else:
            result_digests = set()
            passed_cases = set()
            for index, raw in enumerate(raw_results):
                if not isinstance(raw, Mapping):
                    errors.append(f"evidence report results[{index}] is not an object")
                    continue
                path = self._safe_report_path(str(raw.get("path") or ""))
                if raw.get("format") != "junit":
                    errors.append(f"evidence report results[{index}] is not JUnit")
                    continue
                payload = self._read_member(archive_bytes, path)
                digest = f"sha256:{hashlib.sha256(payload).hexdigest()}"
                if raw.get("digest") != digest:
                    errors.append(f"evidence report results[{index}] digest does not match artifact bytes")
                    continue
                result_digests.add(digest)
                passed_cases.update(
                    identity for identity, status in self._junit_cases(payload).items() if status == "passed"
                )

        claims = report.get("claims")
        if not isinstance(claims, list) or not claims:
            errors.append("evidence report has no claims")
        else:
            for index, raw in enumerate(claims):
                if not isinstance(raw, Mapping):
                    errors.append(f"evidence report claims[{index}] is not an object")
                    continue
                digests = raw.get("result_digests")
                tests = raw.get("test_cases")
                command_digest = str(raw.get("command_digest") or "")
                if (
                    not isinstance(digests, list)
                    or not digests
                    or any(digest not in result_digests for digest in digests)
                ):
                    errors.append(f"evidence report claims[{index}] is not bound to verified result bytes")
                if (
                    not isinstance(tests, list)
                    or not tests
                    or any(not isinstance(test, str) or test not in passed_cases for test in tests)
                ):
                    errors.append(f"evidence report claims[{index}] is not bound to passed test cases")
''',
    '''        raw_results = report.get("results")
        result_cases: dict[str, set[str]] = {}
        if not isinstance(raw_results, list) or not raw_results:
            errors.append("evidence report has no machine result files")
        else:
            for index, raw in enumerate(raw_results):
                if not isinstance(raw, Mapping):
                    errors.append(f"evidence report results[{index}] is not an object")
                    continue
                path = self._safe_report_path(str(raw.get("path") or ""))
                if raw.get("format") != "junit":
                    errors.append(f"evidence report results[{index}] is not JUnit")
                    continue
                payload = self._read_member(archive_bytes, path)
                digest = f"sha256:{hashlib.sha256(payload).hexdigest()}"
                if raw.get("digest") != digest:
                    errors.append(f"evidence report results[{index}] digest does not match artifact bytes")
                    continue
                result_cases[digest] = {
                    identity for identity, status in self._junit_cases(payload).items() if status == "passed"
                }

        claims = report.get("claims")
        if not isinstance(claims, list) or not claims:
            errors.append("evidence report has no claims")
        else:
            for index, raw in enumerate(claims):
                if not isinstance(raw, Mapping):
                    errors.append(f"evidence report claims[{index}] is not an object")
                    continue
                digests = raw.get("result_digests")
                tests = raw.get("test_cases")
                command_digest = str(raw.get("command_digest") or "")
                verified_claim_cases: set[str] = set()
                if (
                    not isinstance(digests, list)
                    or not digests
                    or any(not isinstance(digest, str) or digest not in result_cases for digest in digests)
                ):
                    errors.append(f"evidence report claims[{index}] is not bound to verified result bytes")
                else:
                    for digest in digests:
                        verified_claim_cases.update(result_cases[digest])
                if (
                    not isinstance(tests, list)
                    or not tests
                    or any(not isinstance(test, str) or test not in verified_claim_cases for test in tests)
                ):
                    errors.append(f"evidence report claims[{index}] is not bound to passed test cases in its result bytes")
''',
)

replace_once(
    "contracts/evidence.py",
    '''            "tested_checkout_sha": expected_revision,
            "provider_run_head_sha": str(run.get("head_sha") or ""),
''',
    '''            "tested_checkout_sha": expected_revision,
            "merge_sha": None,
            "provider_run_head_sha": str(run.get("head_sha") or ""),
''',
)

replace_once(
    "contracts/evidence.py",
    '''        page = 1
        while True:
            commits = self._get_list(f"/repos/{repository}/pulls/{pull_request}/commits?per_page=100&page={page}")
            for commit in commits:
                for field in ("author", "committer"):
                    identity = self._canonical_user(commit.get(field))
                    if identity is not None:
                        identities.add(identity)
            if len(commits) < 100:
                break
            page += 1
        identities.update(self._observed_producers)
''',
    '''        raw_commit_count = pull.get("commits")
        if type(raw_commit_count) is not int or raw_commit_count < 0:
            raise ValueError("pull request has no canonical commit count")
        if raw_commit_count > 250:
            raise ValueError("cannot prove reviewer independence for a pull request with more than 250 commits")
        page = 1
        observed_commits = 0
        while observed_commits < raw_commit_count:
            commits = self._get_list(f"/repos/{repository}/pulls/{pull_request}/commits?per_page=100&page={page}")
            if not commits:
                break
            observed_commits += len(commits)
            for commit in commits:
                for field in ("author", "committer"):
                    identity = self._canonical_user(commit.get(field))
                    if identity is not None:
                        identities.add(identity)
            page += 1
        if observed_commits != raw_commit_count:
            raise ValueError("cannot prove reviewer independence because provider commit enumeration is incomplete")
        identities.update(self._observed_producers)
''',
)

replace_once(
    "contracts/write_evidence_report.py",
    '    merge_sha = None if args.merge_sha in {None, "", source_head_sha} else _sha(args.merge_sha, "merge_sha")\n',
    '''    if args.merge_sha not in {None, "", source_head_sha}:
        raise ValueError("merge_sha is unsupported until it can be verified independently")
    merge_sha = None
''',
)

workflow_path = Path(".github/workflows/ci.yml")
workflow = workflow_path.read_text(encoding="utf-8")
merge_env = '          MERGE_SHA: ${{ github.sha }}\n'
merge_arg = '             --merge-sha "$MERGE_SHA"'
if workflow.count(merge_env) != 5:
    raise SystemExit(f"workflow: expected 5 MERGE_SHA env entries, found {workflow.count(merge_env)}")
if workflow.count(merge_arg) != 5:
    raise SystemExit(f"workflow: expected 5 merge args, found {workflow.count(merge_arg)}")
workflow = workflow.replace(merge_env, "").replace(merge_arg, "")
if workflow.count('filesystem-${{ matrix.lock_id }}.xml') != 3:
    raise SystemExit("workflow: filesystem result path count changed")
workflow = workflow.replace('filesystem-${{ matrix.lock_id }}.xml', "filesystem-junit.xml")
workflow_path.write_text(workflow, encoding="utf-8", newline="\n")

replace_once(
    "contracts/evidence-claim-plan.yaml",
    '''  filesystem:
    - kind: rule
      subject: mcp.artifact.exact
      command: python -m pytest tests/test_generator_platform_contracts.py
      selectors: ["*test_*"]
      result_files: ["filesystem-*.xml"]
''',
    '''  filesystem:
    - kind: rule
      subject: mcp.artifact.exact
      command: >-
        python -m pytest
        tests/test_mcp_generator.py::test_generator_concurrent_create_has_one_winner_and_never_replaces
        tests/test_mcp_dotnet_generator.py::test_generator_concurrent_create_has_one_winner_and_never_replaces
        tests/test_mcp_dotnet_generator.py::test_generator_preserves_competing_target_created_before_publish
        tests/test_mcp_dotnet_namespace.py
        --junitxml=filesystem-junit.xml
      selectors:
        - "*test_generator_concurrent_create_has_one_winner_and_never_replaces*"
        - "*test_generator_preserves_competing_target_created_before_publish*"
        - "*test_mcp_dotnet_namespace*"
      result_files: ["filesystem-junit.xml"]
''',
)

replace_once(
    "tests/test_mcp_generator.py",
    '''                result = await session.call_tool("list_items", {"limit": 1})
                assert result.isError is not True
''',
    '''                result = await session.call_tool("list_items", {"limit": 1})
                assert result.isError is not True
                denied = await session.call_tool(
                    "put_item",
                    {"item_id": "blocked", "name": "Blocked", "expected_version": 0},
                )
                assert denied.isError is True
                assert any(
                    "AUTHORIZATION_FAILED" in str(getattr(content, "text", ""))
                    for content in denied.content
                )
''',
)

replace_once(
    "tests/test_evidence_verifier.py",
    '        "merge_sha": "b" * 40,\n',
    '        "merge_sha": None,\n',
)
replace_once(
    "tests/test_evidence_verifier.py",
    '''        "/repos/owner/repository/pulls/12": {
            "head": {"sha": SHA},
            "user": {"id": 800, "login": "author"},
        },
''',
    '''        "/repos/owner/repository/pulls/12": {
            "head": {"sha": SHA},
            "user": {"id": 800, "login": "author"},
            "commits": 1,
        },
''',
)
replace_once(
    "tests/test_evidence_verifier.py",
    '''    errors = StubVerifier(responses, archive).verify_action(reference, SHA)
    assert any("not bound to passed test cases" in error for error in errors)


def test_result_digest_and_failed_junit_are_rejected() -> None:
''',
    '''    errors = StubVerifier(responses, archive).verify_action(reference, SHA)
    assert any("not bound to passed test cases" in error for error in errors)


def test_claim_test_cases_must_come_from_the_claimed_result_digest() -> None:
    reference, responses, _ = successful_fixture()
    second_path = "second-results.xml"
    second_junit = (
        b'<testsuite tests="1" failures="0" errors="0" skipped="0">'
        b'<testcase classname="tests.test_other" name="test_other" />'
        b"</testsuite>"
    )
    second_digest = "sha256:" + hashlib.sha256(second_junit).hexdigest()
    document = json.loads(make_report())
    document["results"].append(
        {
            "path": second_path,
            "format": "junit",
            "digest": second_digest,
            "summary": {"tests": 1, "passed": 1, "skipped": 0, "failures": 0, "errors": 0},
        }
    )
    document["claims"][0]["result_digests"] = [RESULT_DIGEST]
    document["claims"][0]["test_cases"] = ["tests.test_other::test_other"]
    report = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\\n").encode()
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(REPORT_PATH, report)
        archive.writestr(RESULT_PATH, JUNIT)
        archive.writestr(second_path, second_junit)
    archive_bytes = output.getvalue()
    provider_digest = "sha256:" + hashlib.sha256(archive_bytes).hexdigest()
    reference = dict(
        reference,
        provider_digest=provider_digest,
        report_digest="sha256:" + hashlib.sha256(report).hexdigest(),
    )
    responses = dict(responses)
    responses["/repos/owner/repository/actions/artifacts/400"] = {
        **responses["/repos/owner/repository/actions/artifacts/400"],  # type: ignore[arg-type]
        "digest": provider_digest,
    }
    errors = StubVerifier(responses, archive_bytes).verify_action(reference, SHA)
    assert any("not bound to passed test cases in its result bytes" in error for error in errors)


def test_non_null_unverified_merge_sha_is_rejected() -> None:
    reference, responses, _ = successful_fixture()
    report = make_report(merge_sha="b" * 40)
    archive = make_zip(report)
    provider_digest = "sha256:" + hashlib.sha256(archive).hexdigest()
    reference = dict(
        reference,
        provider_digest=provider_digest,
        report_digest="sha256:" + hashlib.sha256(report).hexdigest(),
    )
    responses = dict(responses)
    responses["/repos/owner/repository/actions/artifacts/400"] = {
        **responses["/repos/owner/repository/actions/artifacts/400"],  # type: ignore[arg-type]
        "digest": provider_digest,
    }
    errors = StubVerifier(responses, archive).verify_action(reference, SHA)
    assert "evidence report merge_sha does not match the referenced execution" in errors


def test_result_digest_and_failed_junit_are_rejected() -> None:
''',
)
replace_once(
    "tests/test_evidence_verifier.py",
    '''def test_artifact_path_and_github_com_scope_fail_closed() -> None:
''',
    '''def test_review_fails_closed_when_provider_cannot_enumerate_every_pr_commit() -> None:
    reference, responses, archive = successful_fixture()
    responses = dict(responses)
    responses["/repos/owner/repository/pulls/12"] = {
        "head": {"sha": SHA},
        "user": {"id": 800, "login": "author"},
        "commits": 251,
    }
    review_reference = {
        "provider": "github",
        "repository": "owner/repository",
        "pull_request": 12,
        "review_id": 500,
        "login": "reviewer",
        "id": 600,
        "revision": SHA,
        "state": "APPROVED",
    }
    errors = StubVerifier(responses, archive).verify_review(review_reference, SHA)
    assert any("more than 250 commits" in error for error in errors)


def test_artifact_path_and_github_com_scope_fail_closed() -> None:
''',
)

replace_once(
    "tests/test_write_evidence_report.py",
    '''        "--merge-sha",
        "b" * 40,
''',
    "",
)
replace_once(
    "tests/test_write_evidence_report.py",
    '''    assert document["tested_checkout_sha"] == SHA
    assert document["producer"] == {"provider": "github", "login": "author", "id": 40}
''',
    '''    assert document["tested_checkout_sha"] == SHA
    assert document["merge_sha"] is None
    assert document["producer"] == {"provider": "github", "login": "author", "id": 40}
''',
)
replace_once(
    "tests/test_write_evidence_report.py",
    '''def test_writer_rejects_merge_checkout_and_failed_or_unmapped_results(tmp_path: Path) -> None:
    arguments = _arguments(tmp_path)
    tested_index = arguments.index("--tested-checkout-sha") + 1
''',
    '''def test_writer_rejects_merge_checkout_and_failed_or_unmapped_results(tmp_path: Path) -> None:
    arguments = _arguments(tmp_path)
    arguments[arguments.index("--run-id"):arguments.index("--run-id")] = ["--merge-sha", "b" * 40]
    with pytest.raises(ValueError, match="unsupported until it can be verified independently"):
        main(arguments)

    arguments = _arguments(tmp_path)
    tested_index = arguments.index("--tested-checkout-sha") + 1
''',
)

replace_once(
    "contracts/README.md",
    '''- `merge_sha`: the synthetic pull-request merge revision, when distinct;
''',
    '''- `merge_sha`: reserved and required to be `null` until a provider adapter can independently prove the synthetic merge commit and its parents;
''',
)
replace_once(
    "contracts/README.md",
    '''The writer records `source_head_sha`, `tested_checkout_sha`, optional `merge_sha`, and the provider's `head_sha` separately. A pull-request merge ref is never silently treated as the assessed source revision.
''',
    '''The writer records `source_head_sha`, `tested_checkout_sha`, and the provider's `head_sha` separately. In schema v2 `merge_sha` is required to be `null`: evidence-producing jobs test the exact source HEAD, and an unverified synthetic pull-request merge ref is rejected rather than treated as evidence.
''',
)

Path(".github/current-audit-fix.py").unlink()
Path(".github/workflows/_apply-current-audit-fix.yml").unlink()
