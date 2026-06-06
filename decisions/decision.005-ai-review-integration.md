---
doc_id: decision.005
type: decision
status: accepted
rigor_tier: L2
stability: stable
ai_scope: review_only
source_of_truth: true
upstream: [ref.ci-cd-standard]
last_verified: 2026-06-05
owners: ["ai-skills-maintainer"]
description: Process for handling AI code review feedback on CI/CD workflows including SHA verification protocol
---

# ADR: AI Review Integration Protocol for CI/CD Workflows

> [!NOTE]
> Architecture Decision Record. Documents the process for handling AI-generated code review suggestions in CI/CD pipelines, specifically around commit SHA pinning verification.

## CONTEXT

AI code review tools integrated into CI/CD pipelines can suggest changes including commit SHA pinning for GitHub Actions. These tools are probabilistic text generators and may hallucinate or suggest incorrect SHAs. During adoption of SHA-pinned actions across CI/CD templates, AI reviewers suggested non-existent SHAs, wrong repos, and version tags that did not exist upstream. A verification protocol is needed to ensure AI-suggested SHAs are validated before merging, regardless of which AI tool generated them.

## DECISION

### 1. SHA Verification Protocol

Every AI-suggested commit SHA for a GitHub Action MUST be verified before merging. The verification uses a two-tier fallback strategy:

- **Primary:** `git ls-remote <repo-url> refs/tags/v<semver>^{}` -- requests the peeled (dereferenced) commit SHA. Annotated tags in Git store a tag object rather than directly pointing to a commit; without the `^{}` suffix, `git ls-remote` returns the tag object SHA, which will not match a commit SHA and causes false verification failures.
  - If `^{}` returns a SHA, compare it to the AI-suggested SHA. Exact match required.
  - If `^{}` returns nothing (lightweight tags or servers that do not support the peeled syntax), fall back to `git ls-remote <repo-url> refs/tags/v<semver>` (without `^{}`) and compare that SHA directly.
- **Fallback: GitHub API v3** -- used when `git ls-remote` is unavailable or its output is unreliable:
  1. `GET /repos/<owner>/<repo>/git/ref/tags/v<semver>` → inspect `.object.type`.
     - If `"tag"` (annotated tag): dereference via `GET /repos/<owner>/<repo>/git/tags/<object.sha>` → use `.object.sha` from the response.
     - If `"commit"` (lightweight tag): use `.object.sha` directly.
  2. Compare the resolved commit SHA to the AI-suggested SHA. Exact match required.

If neither method produces an exact match, the SHA MUST be rejected. The CI/CD standard's action-version-matrix reference serves as the ground truth for known-valid SHAs.

### 2. Dependabot PR Review

Dependabot-generated pull requests that update GitHub Actions MUST be reviewed for SHA pinning compliance. All actions in the workflow MUST use pinned commit SHAs, not floating `@v<major>` or `@v<major>.<minor>` tags. The review must verify:

- Every action step references a full 40-character commit SHA
- The SHA matches the resolved tag SHA from `git ls-remote`
- No action references a mutable tag (`@v3`, `@v2.1`) as the primary reference

### 3. AI-Suggested Changes Must Be Verified

AI code review tools may suggest both SHA changes and structural workflow changes. All AI-suggested modifications to CI/CD workflow files MUST go through the SHA verification protocol before merge approval. This applies regardless of:

- The AI tool that generated the suggestion
- The confidence score reported by the tool
- Whether the suggestion appears in a review comment, a summary, or an inline suggestion

## ALTERNATIVES_CONSIDERED

- **Trust AI suggestions without verification:** Rejected. AI tools have been observed hallucinating non-existent SHAs. A verification protocol is the minimum safety barrier.
    - **Manual SHA verification only:** Rejected. Human reviewers cannot reliably distinguish valid from hallucinated SHAs without tooling. Verification must be automated or assisted by tooling.
- **Pin to `@latest` or `@main`:** Rejected. Mutable references defeat supply chain security. Only immutable commit SHAs provide reproducibility and tamper resistance.
- **Rely on Dependabot alone for action updates:** Rejected. Dependabot updates known actions but does not review custom or third-party actions that AI tools could suggest adding.

## CONSEQUENCES

**Positive:**
- Prevents merging of non-existent or malicious action SHAs suggested by AI tools
- Verification protocol is tool-agnostic and works with any AI code review system
- Two-tier fallback covers both lightweight and annotated tags
- Dependabot reviews ensure consistent SHA pinning across all workflow files
**Negative:**
- Adds a manual verification step to the review process for AI-suggested changes
- `git ls-remote` requires network access and may fail in air-gapped environments
- Fallback API call depends on GitHub API availability and rate limits
**Risks:**
- AI tools may adapt by suggesting valid SHAs that point to compromised action versions. Mitigation: SHA verification is a correctness check, not a security audit. Action provenance must be validated separately.
- Automated SHA verification may be bypassed in urgent hotfix merges. Mitigation: Enforce at the CI level rather than relying on human review discipline.

## STATUS

- `accepted: 2026-06-05` -- Approved as part of the CI/CD security baseline
## CHANGELOG

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0.0 | 2026-06-05 | Initial decision -- SHA verification protocol, Dependabot review rules, AI suggestion verification requirement | ai-skills-maintainer |

