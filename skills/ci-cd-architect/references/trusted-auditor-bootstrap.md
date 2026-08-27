---
description: Defines creation, rotation, verification, and compromise recovery for an auditor executed outside the candidate repository tree.
doc_id: reference.cicd.trusted-auditor-bootstrap
type: reference
status: active
rigor: normative
owners:
  - CI/CD maintainers
  - Security maintainers
verification:
  method: manual-review
  command: python skills/afds-doc-writer/validate.py --repository-root . skills/ci-cd-architect/references/trusted-auditor-bootstrap.md
---
# Trusted auditor bootstrap and recovery

## Trust objective

A candidate repository MUST NOT approve its own workflow policy by changing the auditor and the candidate workflow in the same trust domain. The acceptance authority MUST execute an immutable auditor revision obtained outside the candidate tree and bind its result to the full candidate commit SHA.

## Genesis revision

The first trusted auditor revision requires an explicit genesis procedure:

1. Review the complete auditor source, dependency lock, build recipe, tests, and published artifact from a clean repository checkout.
2. Execute the auditor against its own representative positive and adversarial fixtures.
3. Record the full source SHA, artifact digest, dependency-lock digest, claim-catalog SHA, reviewer identities, and approval decision.
4. Publish the record through a protected release path that cannot be modified by the candidate workflow.
5. Pin consumers to the full source SHA and, when distributed as a wheel or OCI artifact, the immutable artifact digest.

A branch, mutable tag, badge, commit message, or repository ownership claim is not genesis evidence.

## Routine rotation

A new trusted revision MUST be reviewed as a transition from the currently trusted revision. The rotation record MUST include:

- old and new full SHAs;
- semantic rule changes and compatibility impact;
- newly required permissions or dependencies;
- regression results against the previous fixture set;
- a bounded overlap period when both revisions are accepted;
- a removal date for the superseded revision.

A consumer MAY reject a new revision until the rotation record is independently approved.

## Key and authority rotation

Signing keys, GitHub environments, protected workflow repositories, and other acceptance authorities MUST rotate independently of candidate repositories. Rotation requires proof of control of both old and new authority when the old authority is still trusted. When that proof is unavailable, use the compromise recovery procedure.

## Compromise recovery

After suspected compromise:

1. Freeze approvals and mark affected auditor revisions and artifact digests revoked.
2. Establish a clean recovery authority through an out-of-band channel.
3. Rebuild the last known-good source with a clean dependency graph and compare source, package, and OCI identities.
4. Review all approvals issued after the earliest plausible compromise time.
5. Publish a signed revocation and replacement record containing the exact affected revisions.
6. Require consumers to pin the replacement revision before provider-backed or independent approval resumes.

A compromised authority MUST NOT approve its own recovery record.

## Consumer verification

Before execution, a consumer MUST verify:

- the auditor source revision is a full allowed SHA;
- the executable artifact digest is present in the acceptance record;
- the claim catalog is independently pinned;
- the revision is not revoked or expired;
- the evidence profile permits the requested maturity level;
- the result identifies the exact candidate repository and full candidate SHA.

Failures are blocking. Falling back to a candidate-tree auditor changes the result to local structural evidence and MUST NOT retain provider-backed or independently-approved status.
