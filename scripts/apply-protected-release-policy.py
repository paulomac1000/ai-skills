#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one match in {path}: found {count}")
    path.write_text(text.replace(old, new), encoding="utf-8")


impl = ROOT / "skills/ci-cd-architect/tools/check_github_actions_policy_impl.py"
replace_once(
    impl,
    '_MUTABLE_RUNNERS = {"ubuntu-latest", "windows-latest", "macos-latest"}\n',
    '_MUTABLE_RUNNERS = {"ubuntu-latest", "windows-latest", "macos-latest"}\n'
    '_PROTECTED_RELEASE_WRITE_SCOPES = frozenset({"packages", "contents", "id-token", "attestations"})\n',
)
replace_once(
    impl,
    """def _permission_findings(
    path: Path,
    permissions: Any,
    *,
    scope: str,
    allowed_read_scopes: frozenset[str] | None = None,
) -> list[Finding]:
""",
    """def _permission_findings(
    path: Path,
    permissions: Any,
    *,
    scope: str,
    allowed_read_scopes: frozenset[str] | None = None,
    allowed_write_scopes: frozenset[str] | None = None,
) -> list[Finding]:
""",
)
replace_once(
    impl,
    """        if _WRITE_PERMISSION.search(normalized_access):
            findings.append(
                Finding(
                    path,
                    f"{scope} grants {name}: {access}; this policy permits no write scope",
                )
            )
""",
    """        if _WRITE_PERMISSION.search(normalized_access):
            if allowed_write_scopes is None or normalized_name not in allowed_write_scopes:
                allowed = ", ".join(sorted(allowed_write_scopes or ())) or "none"
                findings.append(
                    Finding(
                        path,
                        f"{scope} grants {name}: {access}; allowed write scopes are: {allowed}",
                    )
                )
""",
)
replace_once(
    impl,
    """        if "uses" in job:
            findings.append(Finding(path, f"job {job_name!r} reusable workflow calls are not supported"))
            findings.extend(_external_action_findings(path, f"job {job_name!r}", job.get("uses")))
            continue
""",
    """        if "uses" in job:
            uses = job.get("uses")
            label = f"job {job_name!r}"
            if not isinstance(uses, str):
                findings.append(Finding(path, f"{label} reusable workflow reference must be a string"))
            elif (
                not uses.startswith("./.github/workflows/")
                or ".." in Path(uses).parts
                or Path(uses).suffix.casefold() not in _WORKFLOW_SUFFIXES
                or _EXPRESSION_REFERENCE.search(uses)
            ):
                findings.append(
                    Finding(
                        path,
                        f"{label} may call only a literal repository-local workflow below .github/workflows",
                    )
                )
            if pull_request_workflow and any(
                _SECRET_CONTEXT_REFERENCE.search(value) for value in _scalar_strings(job)
            ):
                findings.append(Finding(path, f"{label} pull-request call must not pass repository secrets"))
            continue
""",
)
replace_once(
    impl,
    """        if "permissions" in job:
            findings.extend(
                _permission_findings(
                    path,
                    job.get("permissions"),
                    scope=f"job {job_name!r}",
                    allowed_read_scopes=allowed_read_scopes,
                )
            )
""",
    """        if "permissions" in job:
            protected_release_job = not pull_request_workflow and "environment" in job
            findings.extend(
                _permission_findings(
                    path,
                    job.get("permissions"),
                    scope=f"job {job_name!r}",
                    allowed_read_scopes=allowed_read_scopes,
                    allowed_write_scopes=(
                        _PROTECTED_RELEASE_WRITE_SCOPES if protected_release_job else None
                    ),
                )
            )
""",
)

publish = ROOT / "skills/ci-cd-architect/templates/publish.yml.template"
replace_once(publish, "runs-on: ubuntu-latest", "runs-on: ubuntu-24.04")
# Template contains two runner declarations.
text = publish.read_text(encoding="utf-8")
text = text.replace("runs-on: ubuntu-latest", "runs-on: ubuntu-24.04")
publish.write_text(text, encoding="utf-8")
replace_once(
    publish,
    """        env:
          IMAGE_REPOSITORY: ghcr.io/${{ github.repository }}
          IMMUTABLE_TAG: sha-${{ needs.validate.outputs.release_short_sha }}
        run: |
          set -euo pipefail
          docker push --all-tags "$IMAGE_REPOSITORY"
          digest="$(docker inspect --format='{{index .RepoDigests 0}}' "$IMAGE_REPOSITORY:$IMMUTABLE_TAG" | cut -d@ -f2)"
          test -n "$digest"
          echo "digest=$digest" >> "$GITHUB_OUTPUT"
""",
    """        env:
          IMAGE_REPOSITORY: ghcr.io/${{ github.repository }}
          IMAGE_TAGS: ${{ steps.meta.outputs.tags }}
          IMMUTABLE_TAG: sha-${{ needs.validate.outputs.release_short_sha }}
        run: |
          set -euo pipefail
          while IFS= read -r image_tag; do
            test -n "$image_tag" || continue
            docker push "$image_tag"
          done <<< "$IMAGE_TAGS"
          digest="$(docker buildx imagetools inspect "$IMAGE_REPOSITORY:$IMMUTABLE_TAG" --format '{{json .Manifest.Digest}}' | tr -d '"')"
          test -n "$digest"
          echo "digest=$digest" >> "$GITHUB_OUTPUT"
""",
)

standard = ROOT / "skills/ci-cd-architect/STANDARD.md"
replace_once(
    standard,
    """- Top-level permissions default to `contents: read`; jobs elevate only capabilities they use.
""",
    """- Top-level permissions default to `contents: read`; jobs elevate only capabilities they use.
- Write scopes are forbidden for pull-request code. A non-PR job may use only `packages`, `contents`, `id-token`, or `attestations` write access, and only when it names a protected release environment. Repository-local reusable workflows are permitted through literal `./.github/workflows/*.yml` references; external or expression-derived workflow calls are not.
""",
)
replace_once(
    standard,
    """7. captures the registry digest and attests that digest.
""",
    """7. pushes only the explicitly derived tags, captures the registry digest, and attests that digest.
""",
)

skill = ROOT / "skills/ci-cd-architect/SKILL.md"
replace_once(
    skill,
    """- Do not grant write permissions to untrusted pull-request code.
""",
    """- Do not grant write permissions to untrusted pull-request code. Keep workflow-level permissions read-only; narrowly scoped write access belongs only to a non-PR job protected by a named release environment.
""",
)
replace_once(
    skill,
    """- Do not publish an artifact that was not tested in its published form.
""",
    """- Do not publish an artifact that was not tested in its published form, and never use broad operations such as `docker push --all-tags` when release channels have different promotion rights.
""",
)

tests = ROOT / "tests/test_ci_cd_workflow_policy.py"
with tests.open("a", encoding="utf-8") as handle:
    handle.write(
        r'''


def test_protected_non_pr_release_job_may_use_narrow_write_scopes(tmp_path: Path) -> None:
    workflow = tmp_path / "release.yml"
    workflow.write_text(
        """
name: release
on: workflow_dispatch
permissions:
  contents: read
concurrency:
  group: release
  cancel-in-progress: false
jobs:
  publish:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    environment: production-release
    permissions:
      contents: write
      packages: write
      id-token: write
      attestations: write
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          persist-credentials: false
""".lstrip(),
        encoding="utf-8",
    )
    assert _messages(workflow) == []


def test_write_scope_without_release_environment_is_rejected(tmp_path: Path) -> None:
    workflow = tmp_path / "unsafe-release.yml"
    workflow.write_text(
        """
name: unsafe
on: workflow_dispatch
permissions:
  contents: read
concurrency:
  group: unsafe
  cancel-in-progress: false
jobs:
  publish:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    permissions:
      packages: write
    steps: []
""".lstrip(),
        encoding="utf-8",
    )
    assert any("allowed write scopes are: none" in message for message in _messages(workflow))


def test_literal_repository_local_reusable_workflow_is_accepted(tmp_path: Path) -> None:
    workflow = tmp_path / "caller.yml"
    workflow.write_text(
        """
name: caller
on: workflow_dispatch
permissions:
  contents: read
concurrency:
  group: caller
  cancel-in-progress: false
jobs:
  build:
    uses: ./.github/workflows/container-build.yml
""".lstrip(),
        encoding="utf-8",
    )
    assert _messages(workflow) == []
'''
    )

# Self-remove the one-shot migration machinery.
(ROOT / ".github/workflows/apply-protected-release-policy.yml").unlink(missing_ok=True)
Path(__file__).unlink(missing_ok=True)
