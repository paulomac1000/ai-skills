from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "contracts" / "artifact_closure.py"
SPEC = importlib.util.spec_from_file_location("artifact_closure", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

ClosureCurrentness = MODULE.ClosureCurrentness
DeliverableKind = MODULE.DeliverableKind
DeliverableObservation = MODULE.DeliverableObservation
DeliverableRequirement = MODULE.DeliverableRequirement
Presence = MODULE.Presence
ReleaseDeliverableManifest = MODULE.ReleaseDeliverableManifest
SmokeStatus = MODULE.SmokeStatus
UnexpectedComponentObservation = MODULE.UnexpectedComponentObservation
UnexpectedComponentPolicy = MODULE.UnexpectedComponentPolicy
UnexpectedCriticality = MODULE.UnexpectedCriticality
UnexpectedDisposition = MODULE.UnexpectedDisposition
classify_artifact_closure_currentness = MODULE.classify_artifact_closure_currentness
evaluate_artifact_closure = MODULE.evaluate_artifact_closure
manifest_digest = MODULE.manifest_digest
manifest_document = MODULE.manifest_document
verify_artifact_closure_receipt_integrity = MODULE.verify_artifact_closure_receipt_integrity
verify_artifact_closure_receipt_semantics = MODULE.verify_artifact_closure_receipt_semantics

DIGEST_1 = "sha256:" + "1" * 64
DIGEST_2 = "sha256:" + "2" * 64
CLAIM_EVIDENCE_DIGEST = "sha256:" + "3" * 64
EVIDENCE_DIGEST_2 = "sha256:" + "4" * 64
SMOKE_PROFILE_DIGEST_HOST = "sha256:" + "5" * 64
SMOKE_PROFILE_DIGEST_STEWARDCTL = "sha256:" + "6" * 64
SMOKE_PROFILE_DIGEST_WORKER = "sha256:" + "7" * 64
SMOKE_PROFILE_DIGEST_OTHER = "sha256:" + "8" * 64
SOURCE_REVISION = "a" * 40
OTHER_SOURCE_REVISION = "b" * 40


class ArtifactClosureTests(unittest.TestCase):
    def manifest(self) -> ReleaseDeliverableManifest:
        return ReleaseDeliverableManifest(
            manifest_id="project-steward-production",
            revision="1",
            policy_ref="policy:release/project-steward/0.9",
            deliverables=(
                DeliverableRequirement(
                    "host",
                    DeliverableKind.RUNTIME_ENTRYPOINT,
                    expected_identity_ref="entrypoint:ProjectSteward.Host",
                    smoke_profile_ref="smoke:host-version",
                    smoke_profile_digest=SMOKE_PROFILE_DIGEST_HOST,
                    smoke_required=True,
                ),
                DeliverableRequirement(
                    "stewardctl",
                    DeliverableKind.OPERATOR_ENTRYPOINT,
                    expected_identity_ref="entrypoint:stewardctl",
                    smoke_profile_ref="smoke:stewardctl-help",
                    smoke_profile_digest=SMOKE_PROFILE_DIGEST_STEWARDCTL,
                    smoke_required=True,
                ),
                DeliverableRequirement(
                    "dev-helper",
                    DeliverableKind.OTHER,
                    required=False,
                ),
            ),
        )

    def observation(
        self,
        deliverable_id: str,
        *,
        presence: Presence = Presence.PRESENT,
        identity_ref: str | None = None,
        smoke_profile_ref: str | None = None,
        smoke_profile_digest: str | None = None,
        smoke_status: SmokeStatus = SmokeStatus.PASS,
    ) -> DeliverableObservation:
        if smoke_profile_ref is None and smoke_status in {SmokeStatus.PASS, SmokeStatus.FAIL}:
            smoke_profile_ref = {
                "host": "smoke:host-version",
                "stewardctl": "smoke:stewardctl-help",
                "worker": "smoke:worker-start",
            }.get(deliverable_id, f"smoke:{deliverable_id}")
        if smoke_profile_digest is None and smoke_status in {SmokeStatus.PASS, SmokeStatus.FAIL}:
            smoke_profile_digest = {
                "host": SMOKE_PROFILE_DIGEST_HOST,
                "stewardctl": SMOKE_PROFILE_DIGEST_STEWARDCTL,
                "worker": SMOKE_PROFILE_DIGEST_WORKER,
            }.get(deliverable_id, SMOKE_PROFILE_DIGEST_OTHER)
        return DeliverableObservation(
            deliverable_id=deliverable_id,
            artifact_digest=DIGEST_1,
            presence=presence,
            identity_ref=identity_ref,
            smoke_profile_ref=smoke_profile_ref,
            smoke_profile_digest=smoke_profile_digest,
            smoke_status=smoke_status,
            evidence_ref=f"evidence:{deliverable_id}",
            evidence_digest=CLAIM_EVIDENCE_DIGEST,
        )

    def evaluate(self, *observations: DeliverableObservation, manifest=None, unexpected=()):
        return evaluate_artifact_closure(
            manifest or self.manifest(),
            tuple(observations),
            source_revision=SOURCE_REVISION,
            artifact_ref="oci:project-steward@sha256:111",
            artifact_digest=DIGEST_1,
            artifact_evidence_ref="artifact-evidence:project-steward-090",
            unexpected_components=tuple(unexpected),
        )

    def test_project_steward_fixture_requires_stewardctl_in_exact_artifact(self) -> None:
        receipt = self.evaluate(
            self.observation("host", identity_ref="entrypoint:ProjectSteward.Host"),
            self.observation(
                "stewardctl", presence=Presence.MISSING, identity_ref=None, smoke_status=SmokeStatus.UNKNOWN
            ),
        )
        self.assertEqual("INCOMPLETE", receipt["verdict"])
        self.assertEqual(["stewardctl"], receipt["missing_required"])
        self.assertNotIn("dev-helper", receipt["missing_required"])

    def test_source_tests_or_docs_cannot_substitute_for_artifact_observation(self) -> None:
        receipt = self.evaluate()
        self.assertEqual("INCOMPLETE", receipt["verdict"])
        self.assertEqual(["host", "stewardctl"], receipt["unknown_required"])

    def test_complete_when_required_entrypoints_are_present_identified_and_smoked(self) -> None:
        receipt = self.evaluate(
            self.observation("host", identity_ref="entrypoint:ProjectSteward.Host"),
            self.observation("stewardctl", identity_ref="entrypoint:stewardctl"),
        )
        self.assertEqual("COMPLETE", receipt["verdict"])
        self.assertEqual([], receipt["missing_required"])
        self.assertEqual([], receipt["unknown_required"])
        self.assertEqual([], receipt["identity_mismatches"])
        self.assertEqual([], receipt["smoke_failures"])

    def test_wrong_identity_blocks_closure(self) -> None:
        receipt = self.evaluate(
            self.observation("host", identity_ref="entrypoint:ProjectSteward.Host"),
            self.observation("stewardctl", identity_ref="entrypoint:other-cli"),
        )
        self.assertEqual("INCOMPLETE", receipt["verdict"])
        self.assertEqual("stewardctl", receipt["identity_mismatches"][0]["deliverable_id"])

    def test_required_smoke_unknown_or_failed_blocks_closure(self) -> None:
        for status in (SmokeStatus.UNKNOWN, SmokeStatus.FAIL, SmokeStatus.NOT_REQUIRED):
            with self.subTest(status=status):
                receipt = self.evaluate(
                    self.observation("host", identity_ref="entrypoint:ProjectSteward.Host"),
                    self.observation("stewardctl", identity_ref="entrypoint:stewardctl", smoke_status=status),
                )
                self.assertEqual("INCOMPLETE", receipt["verdict"])
                self.assertEqual(status.value, receipt["smoke_failures"][0]["smoke_status"])
                self.assertEqual("smoke:stewardctl-help", receipt["smoke_failures"][0]["expected_smoke_profile_ref"])

    def test_wrong_smoke_profile_blocks_closure(self) -> None:
        receipt = self.evaluate(
            self.observation("host", identity_ref="entrypoint:ProjectSteward.Host"),
            self.observation(
                "stewardctl",
                identity_ref="entrypoint:stewardctl",
                smoke_profile_ref="smoke:obsolete-stewardctl-check",
            ),
        )
        self.assertEqual("INCOMPLETE", receipt["verdict"])
        self.assertEqual(
            {
                "deliverable_id": "stewardctl",
                "smoke_status": "PASS",
                "expected_smoke_profile_ref": "smoke:stewardctl-help",
                "observed_smoke_profile_ref": "smoke:obsolete-stewardctl-check",
            },
            receipt["smoke_failures"][0],
        )

    def test_present_optional_deliverable_honors_declared_checks(self) -> None:
        manifest = ReleaseDeliverableManifest(
            manifest_id="optional-checks",
            revision="1",
            policy_ref="policy:optional-checks",
            deliverables=(
                DeliverableRequirement(
                    "optional-tool",
                    DeliverableKind.OPERATOR_ENTRYPOINT,
                    required=False,
                    expected_identity_ref="entrypoint:optional-tool",
                    smoke_profile_ref="smoke:optional-tool",
                    smoke_profile_digest=SMOKE_PROFILE_DIGEST_OTHER,
                    smoke_required=True,
                ),
            ),
        )
        receipt = self.evaluate(
            self.observation(
                "optional-tool",
                identity_ref="entrypoint:wrong-tool",
                smoke_profile_ref="smoke:optional-tool",
                smoke_status=SmokeStatus.FAIL,
            ),
            manifest=manifest,
        )
        self.assertEqual("INCOMPLETE", receipt["verdict"])
        self.assertEqual("optional-tool", receipt["identity_mismatches"][0]["deliverable_id"])
        self.assertEqual("optional-tool", receipt["smoke_failures"][0]["deliverable_id"])
        self.assertTrue(verify_artifact_closure_receipt_semantics(receipt, manifest))

    def test_optional_absent_deliverable_does_not_block(self) -> None:
        receipt = self.evaluate(
            self.observation("host", identity_ref="entrypoint:ProjectSteward.Host"),
            self.observation("stewardctl", identity_ref="entrypoint:stewardctl"),
            self.observation(
                "dev-helper", presence=Presence.MISSING, identity_ref=None, smoke_status=SmokeStatus.NOT_REQUIRED
            ),
        )
        self.assertEqual("COMPLETE", receipt["verdict"])

    def test_receipt_tampering_is_unknown_not_current(self) -> None:
        manifest = self.manifest()
        receipt = self.evaluate(
            self.observation("host", identity_ref="entrypoint:ProjectSteward.Host"),
            self.observation("stewardctl", identity_ref="entrypoint:stewardctl"),
            manifest=manifest,
        )
        self.assertTrue(verify_artifact_closure_receipt_integrity(receipt))
        receipt["verdict"] = "INCOMPLETE"
        self.assertFalse(verify_artifact_closure_receipt_integrity(receipt))
        self.assertEqual(
            ClosureCurrentness.UNKNOWN,
            classify_artifact_closure_currentness(
                receipt,
                current_source_revision=SOURCE_REVISION,
                current_artifact_ref="oci:project-steward@sha256:111",
                current_artifact_digest=DIGEST_1,
                current_artifact_evidence_ref="artifact-evidence:project-steward-090",
                current_artifact_evidence_digest=receipt["artifact_evidence_digest"],
                current_manifest=manifest,
            ),
        )

    def test_recomputed_digest_cannot_make_malformed_receipt_current(self) -> None:
        manifest = self.manifest()
        receipt = self.evaluate(
            self.observation("host", identity_ref="entrypoint:ProjectSteward.Host"),
            self.observation("stewardctl", identity_ref="entrypoint:stewardctl"),
            manifest=manifest,
        )
        receipt["observed"] = "malformed"
        payload = dict(receipt)
        payload.pop("receipt_digest")
        receipt["receipt_digest"] = MODULE._sha256_document(payload)
        self.assertFalse(verify_artifact_closure_receipt_integrity(receipt))
        self.assertEqual(
            ClosureCurrentness.UNKNOWN,
            classify_artifact_closure_currentness(
                receipt,
                current_source_revision=SOURCE_REVISION,
                current_artifact_ref="oci:project-steward@sha256:111",
                current_artifact_digest=DIGEST_1,
                current_artifact_evidence_ref="artifact-evidence:project-steward-090",
                current_artifact_evidence_digest=receipt["artifact_evidence_digest"],
                current_manifest=manifest,
            ),
        )

    def test_recomputed_digest_cannot_admit_present_observation_without_evidence(self) -> None:
        manifest = self.manifest()
        receipt = self.evaluate(
            self.observation("host", identity_ref="entrypoint:ProjectSteward.Host"),
            self.observation("stewardctl", identity_ref="entrypoint:stewardctl"),
            manifest=manifest,
        )
        target = receipt["observed"]["stewardctl"]
        target["evidence_ref"] = None
        target["evidence_digest"] = None
        payload = dict(receipt)
        payload.pop("receipt_digest")
        receipt["receipt_digest"] = MODULE._sha256_document(payload)

        self.assertFalse(verify_artifact_closure_receipt_integrity(receipt))
        self.assertEqual(
            ClosureCurrentness.UNKNOWN,
            classify_artifact_closure_currentness(
                receipt,
                current_source_revision=SOURCE_REVISION,
                current_artifact_ref="oci:project-steward@sha256:111",
                current_artifact_digest=DIGEST_1,
                current_artifact_evidence_ref="artifact-evidence:project-steward-090",
                current_artifact_evidence_digest=receipt["artifact_evidence_digest"],
                current_manifest=manifest,
            ),
        )

    def test_recomputed_digest_cannot_admit_pass_from_wrong_smoke_profile(self) -> None:
        manifest = self.manifest()
        receipt = self.evaluate(
            self.observation("host", identity_ref="entrypoint:ProjectSteward.Host"),
            self.observation("stewardctl", identity_ref="entrypoint:stewardctl"),
            manifest=manifest,
        )
        target = receipt["observed"]["stewardctl"]
        trusted_evidence_digest = receipt["artifact_evidence_digest"]
        target["smoke_profile_ref"] = "smoke:obsolete-stewardctl-check"
        receipt["artifact_evidence_digest"] = MODULE._artifact_evidence_digest(
            receipt["artifact_digest"], receipt["observed"], receipt["unexpected_components"]
        )
        payload = dict(receipt)
        payload.pop("receipt_digest")
        receipt["receipt_digest"] = MODULE._sha256_document(payload)

        self.assertTrue(verify_artifact_closure_receipt_integrity(receipt))
        self.assertFalse(verify_artifact_closure_receipt_semantics(receipt, manifest))
        self.assertEqual(
            ClosureCurrentness.UNKNOWN,
            classify_artifact_closure_currentness(
                receipt,
                current_source_revision=SOURCE_REVISION,
                current_artifact_ref="oci:project-steward@sha256:111",
                current_artifact_digest=DIGEST_1,
                current_artifact_evidence_ref="artifact-evidence:project-steward-090",
                current_artifact_evidence_digest=trusted_evidence_digest,
                current_manifest=manifest,
            ),
        )

    def test_per_deliverable_evidence_change_cannot_remain_current(self) -> None:
        manifest = self.manifest()
        receipt = self.evaluate(
            self.observation("host", identity_ref="entrypoint:ProjectSteward.Host"),
            self.observation("stewardctl", identity_ref="entrypoint:stewardctl"),
            manifest=manifest,
        )
        trusted_evidence_digest = receipt["artifact_evidence_digest"]
        target = receipt["observed"]["stewardctl"]
        target["evidence_digest"] = EVIDENCE_DIGEST_2
        receipt["artifact_evidence_digest"] = MODULE._artifact_evidence_digest(
            receipt["artifact_digest"], receipt["observed"], receipt["unexpected_components"]
        )
        payload = dict(receipt)
        payload.pop("receipt_digest")
        receipt["receipt_digest"] = MODULE._sha256_document(payload)

        self.assertNotEqual(trusted_evidence_digest, receipt["artifact_evidence_digest"])
        self.assertTrue(verify_artifact_closure_receipt_integrity(receipt))
        self.assertTrue(verify_artifact_closure_receipt_semantics(receipt, manifest))
        self.assertEqual(
            ClosureCurrentness.STALE,
            classify_artifact_closure_currentness(
                receipt,
                current_source_revision=SOURCE_REVISION,
                current_artifact_ref="oci:project-steward@sha256:111",
                current_artifact_digest=DIGEST_1,
                current_artifact_evidence_ref="artifact-evidence:project-steward-090",
                current_artifact_evidence_digest=trusted_evidence_digest,
                current_manifest=manifest,
            ),
        )

    def test_recomputed_digest_cannot_forge_complete_from_incomplete_receipt(self) -> None:
        manifest = self.manifest()
        receipt = self.evaluate(
            self.observation("host", identity_ref="entrypoint:ProjectSteward.Host"),
            self.observation(
                "stewardctl",
                presence=Presence.MISSING,
                identity_ref=None,
                smoke_status=SmokeStatus.UNKNOWN,
            ),
            manifest=manifest,
        )
        self.assertEqual("INCOMPLETE", receipt["verdict"])
        receipt["missing_required"] = []
        receipt["verdict"] = "COMPLETE"
        payload = dict(receipt)
        payload.pop("receipt_digest")
        receipt["receipt_digest"] = MODULE._sha256_document(payload)

        self.assertTrue(verify_artifact_closure_receipt_integrity(receipt))
        self.assertFalse(verify_artifact_closure_receipt_semantics(receipt, manifest))
        self.assertEqual(
            ClosureCurrentness.UNKNOWN,
            classify_artifact_closure_currentness(
                receipt,
                current_source_revision=SOURCE_REVISION,
                current_artifact_ref="oci:project-steward@sha256:111",
                current_artifact_digest=DIGEST_1,
                current_artifact_evidence_ref="artifact-evidence:project-steward-090",
                current_artifact_evidence_digest=receipt["artifact_evidence_digest"],
                current_manifest=manifest,
            ),
        )

    def test_mutable_source_revision_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "full immutable"):
            evaluate_artifact_closure(
                self.manifest(),
                (),
                source_revision="main",
                artifact_ref="oci:project-steward@sha256:111",
                artifact_digest=DIGEST_1,
                artifact_evidence_ref="artifact-evidence:project-steward-090",
            )

    def test_forged_semantics_remain_unknown_even_when_bindings_are_stale(self) -> None:
        manifest = self.manifest()
        receipt = self.evaluate(
            self.observation("host", identity_ref="entrypoint:ProjectSteward.Host"),
            self.observation(
                "stewardctl",
                presence=Presence.MISSING,
                identity_ref=None,
                smoke_status=SmokeStatus.UNKNOWN,
            ),
            manifest=manifest,
        )
        receipt["missing_required"] = []
        receipt["verdict"] = "COMPLETE"
        payload = dict(receipt)
        payload.pop("receipt_digest")
        receipt["receipt_digest"] = MODULE._sha256_document(payload)

        self.assertEqual(
            ClosureCurrentness.UNKNOWN,
            classify_artifact_closure_currentness(
                receipt,
                current_source_revision=OTHER_SOURCE_REVISION,
                current_artifact_ref="oci:project-steward@sha256:111",
                current_artifact_digest=DIGEST_2,
                current_artifact_evidence_ref="artifact-evidence:new-profile",
                current_artifact_evidence_digest=EVIDENCE_DIGEST_2,
                current_manifest=manifest,
            ),
        )

    def test_rebuild_or_manifest_change_makes_old_receipt_stale(self) -> None:
        manifest = self.manifest()
        receipt = self.evaluate(
            self.observation("host", identity_ref="entrypoint:ProjectSteward.Host"),
            self.observation("stewardctl", identity_ref="entrypoint:stewardctl"),
            manifest=manifest,
        )
        self.assertEqual(
            ClosureCurrentness.CURRENT,
            classify_artifact_closure_currentness(
                receipt,
                current_source_revision=SOURCE_REVISION,
                current_artifact_ref="oci:project-steward@sha256:111",
                current_artifact_digest=DIGEST_1,
                current_artifact_evidence_ref="artifact-evidence:project-steward-090",
                current_artifact_evidence_digest=receipt["artifact_evidence_digest"],
                current_manifest=manifest,
            ),
        )
        self.assertEqual(
            ClosureCurrentness.STALE,
            classify_artifact_closure_currentness(
                receipt,
                current_source_revision=SOURCE_REVISION,
                current_artifact_ref="oci:project-steward@sha256:111",
                current_artifact_digest=DIGEST_2,
                current_artifact_evidence_ref="artifact-evidence:project-steward-090",
                current_artifact_evidence_digest=receipt["artifact_evidence_digest"],
                current_manifest=manifest,
            ),
        )
        self.assertEqual(
            ClosureCurrentness.STALE,
            classify_artifact_closure_currentness(
                receipt,
                current_source_revision=OTHER_SOURCE_REVISION,
                current_artifact_ref="oci:project-steward@sha256:111",
                current_artifact_digest=DIGEST_1,
                current_artifact_evidence_ref="artifact-evidence:project-steward-090",
                current_artifact_evidence_digest=receipt["artifact_evidence_digest"],
                current_manifest=manifest,
            ),
        )
        self.assertEqual(
            ClosureCurrentness.STALE,
            classify_artifact_closure_currentness(
                receipt,
                current_source_revision=SOURCE_REVISION,
                current_artifact_ref="oci:project-steward@sha256:111",
                current_artifact_digest=DIGEST_1,
                current_artifact_evidence_ref="artifact-evidence:new-profile",
                current_artifact_evidence_digest=receipt["artifact_evidence_digest"],
                current_manifest=manifest,
            ),
        )
        self.assertEqual(
            ClosureCurrentness.STALE,
            classify_artifact_closure_currentness(
                receipt,
                current_source_revision=SOURCE_REVISION,
                current_artifact_ref="oci:project-steward@sha256:111",
                current_artifact_digest=DIGEST_1,
                current_artifact_evidence_ref="artifact-evidence:project-steward-090",
                current_artifact_evidence_digest=EVIDENCE_DIGEST_2,
                current_manifest=manifest,
            ),
        )
        self.assertEqual(
            ClosureCurrentness.UNKNOWN,
            classify_artifact_closure_currentness(
                receipt,
                current_source_revision=None,
                current_artifact_ref="oci:project-steward@sha256:111",
                current_artifact_digest=DIGEST_1,
                current_artifact_evidence_ref="artifact-evidence:project-steward-090",
                current_artifact_evidence_digest=receipt["artifact_evidence_digest"],
                current_manifest=manifest,
            ),
        )
        changed_manifest = ReleaseDeliverableManifest(
            manifest_id=manifest.manifest_id,
            revision="2",
            policy_ref=manifest.policy_ref,
            deliverables=manifest.deliverables,
        )
        self.assertEqual(
            ClosureCurrentness.STALE,
            classify_artifact_closure_currentness(
                receipt,
                current_source_revision=SOURCE_REVISION,
                current_artifact_ref="oci:project-steward@sha256:111",
                current_artifact_digest=DIGEST_1,
                current_artifact_evidence_ref="artifact-evidence:project-steward-090",
                current_artifact_evidence_digest=receipt["artifact_evidence_digest"],
                current_manifest=changed_manifest,
                receipt_manifest=manifest,
            ),
        )

    def test_unexpected_critical_component_requires_policy_disposition(self) -> None:
        unexpected = UnexpectedComponentObservation(
            component_ref="entrypoint:debug-admin",
            artifact_digest=DIGEST_1,
            criticality=UnexpectedCriticality.CRITICAL,
            evidence_ref="evidence:package-inventory",
            evidence_digest=CLAIM_EVIDENCE_DIGEST,
        )
        receipt = self.evaluate(
            self.observation("host", identity_ref="entrypoint:ProjectSteward.Host"),
            self.observation("stewardctl", identity_ref="entrypoint:stewardctl"),
            unexpected=(unexpected,),
        )
        self.assertEqual("INCOMPLETE", receipt["verdict"])
        self.assertEqual(["entrypoint:debug-admin"], receipt["blocking_unexpected"])

        forged = json.loads(json.dumps(receipt))
        forged["unexpected_components"]["entrypoint:debug-admin"]["disposition"] = "allowed"
        forged["blocking_unexpected"] = []
        forged["verdict"] = "COMPLETE"
        payload = dict(forged)
        payload.pop("receipt_digest")
        forged["receipt_digest"] = MODULE._sha256_document(payload)
        self.assertTrue(verify_artifact_closure_receipt_integrity(forged))
        self.assertFalse(verify_artifact_closure_receipt_semantics(forged, self.manifest()))

        base_manifest = self.manifest()
        allowed_manifest = ReleaseDeliverableManifest(
            manifest_id=base_manifest.manifest_id,
            revision=base_manifest.revision,
            policy_ref=base_manifest.policy_ref,
            deliverables=base_manifest.deliverables,
            unexpected_component_dispositions=(
                UnexpectedComponentPolicy("entrypoint:debug-admin", UnexpectedDisposition.ALLOWED),
            ),
        )
        allowed_receipt = self.evaluate(
            self.observation("host", identity_ref="entrypoint:ProjectSteward.Host"),
            self.observation("stewardctl", identity_ref="entrypoint:stewardctl"),
            manifest=allowed_manifest,
            unexpected=(unexpected,),
        )
        self.assertEqual("COMPLETE", allowed_receipt["verdict"])
        self.assertEqual([], allowed_receipt["blocking_unexpected"])

    def test_manifest_digest_is_order_independent_but_semantics_sensitive(self) -> None:
        manifest = self.manifest()
        reordered = ReleaseDeliverableManifest(
            manifest_id=manifest.manifest_id,
            revision=manifest.revision,
            policy_ref=manifest.policy_ref,
            deliverables=tuple(reversed(manifest.deliverables)),
        )
        self.assertEqual(manifest_digest(manifest), manifest_digest(reordered))
        changed = ReleaseDeliverableManifest(
            manifest_id=manifest.manifest_id,
            revision=manifest.revision,
            policy_ref="policy:release/project-steward/0.9.1",
            deliverables=manifest.deliverables,
        )
        self.assertNotEqual(manifest_digest(manifest), manifest_digest(changed))

    def test_lone_surrogate_receipt_fails_closed_without_hash_crash(self) -> None:
        receipt = self.evaluate(
            self.observation("host", identity_ref="entrypoint:ProjectSteward.Host"),
            self.observation("stewardctl", identity_ref="entrypoint:stewardctl"),
        )
        receipt["artifact_ref"] = "\ud800"
        self.assertFalse(verify_artifact_closure_receipt_integrity(receipt))
        self.assertEqual(
            ClosureCurrentness.UNKNOWN,
            classify_artifact_closure_currentness(
                receipt,
                current_source_revision=SOURCE_REVISION,
                current_artifact_ref="oci:project-steward@sha256:111",
                current_artifact_digest=DIGEST_1,
                current_artifact_evidence_ref="artifact-evidence:project-steward-090",
                current_artifact_evidence_digest=receipt["artifact_evidence_digest"],
                current_manifest=self.manifest(),
            ),
        )

    def test_same_smoke_ref_with_wrong_profile_digest_blocks_closure(self) -> None:
        receipt = self.evaluate(
            self.observation("host", identity_ref="entrypoint:ProjectSteward.Host"),
            self.observation(
                "stewardctl",
                identity_ref="entrypoint:stewardctl",
                smoke_profile_ref="smoke:stewardctl-help",
                smoke_profile_digest=SMOKE_PROFILE_DIGEST_OTHER,
            ),
        )
        self.assertEqual("INCOMPLETE", receipt["verdict"])
        self.assertEqual("stewardctl", receipt["smoke_failures"][0]["deliverable_id"])

    def test_artifact_ref_change_cannot_remain_current(self) -> None:
        manifest = self.manifest()
        receipt = self.evaluate(
            self.observation("host", identity_ref="entrypoint:ProjectSteward.Host"),
            self.observation("stewardctl", identity_ref="entrypoint:stewardctl"),
            manifest=manifest,
        )
        receipt["artifact_ref"] = "oci:other@sha256:111"
        payload = dict(receipt)
        payload.pop("receipt_digest")
        receipt["receipt_digest"] = MODULE._sha256_document(payload)
        self.assertTrue(verify_artifact_closure_receipt_integrity(receipt))
        self.assertTrue(verify_artifact_closure_receipt_semantics(receipt, manifest))
        self.assertEqual(
            ClosureCurrentness.STALE,
            classify_artifact_closure_currentness(
                receipt,
                current_source_revision=SOURCE_REVISION,
                current_artifact_ref="oci:project-steward@sha256:111",
                current_artifact_digest=DIGEST_1,
                current_artifact_evidence_ref="artifact-evidence:project-steward-090",
                current_artifact_evidence_digest=receipt["artifact_evidence_digest"],
                current_manifest=manifest,
            ),
        )

    def test_malformed_or_ambiguous_inputs_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "unique"):
            ReleaseDeliverableManifest(
                manifest_id="m",
                revision="1",
                policy_ref="p",
                deliverables=(
                    DeliverableRequirement("dup", DeliverableKind.ASSET),
                    DeliverableRequirement("dup", DeliverableKind.ASSET),
                ),
            )
        with self.assertRaisesRegex(ValueError, "undeclared"):
            self.evaluate(self.observation("not-declared", identity_ref="x"))
        with self.assertRaisesRegex(ValueError, "non-present"):
            self.observation("host", presence=Presence.MISSING, identity_ref="entrypoint:host")


    def test_observations_from_another_artifact_cannot_satisfy_closure(self) -> None:
        wrong = DeliverableObservation(
            deliverable_id="host",
            artifact_digest=DIGEST_2,
            presence=Presence.PRESENT,
            identity_ref="entrypoint:ProjectSteward.Host",
            smoke_profile_ref="smoke:host-version",
            smoke_profile_digest=SMOKE_PROFILE_DIGEST_HOST,
            smoke_status=SmokeStatus.PASS,
            evidence_ref="evidence:wrong-artifact",
            evidence_digest=CLAIM_EVIDENCE_DIGEST,
        )
        with self.assertRaisesRegex(ValueError, "same exact artifact digest"):
            self.evaluate(wrong)

    def test_manifest_and_receipt_surfaces_are_bounded(self) -> None:
        with self.assertRaisesRegex(ValueError, "at most 256"):
            ReleaseDeliverableManifest(
                manifest_id="too-large",
                revision="1",
                policy_ref="policy:bounded",
                deliverables=tuple(
                    DeliverableRequirement(f"asset-{index}", DeliverableKind.ASSET)
                    for index in range(257)
                ),
            )

    def test_generic_migration_and_worker_failure_paths_are_artifact_level(self) -> None:
        manifest = ReleaseDeliverableManifest(
            manifest_id="generic-release",
            revision="1",
            policy_ref="policy:generic",
            deliverables=(
                DeliverableRequirement("migrator", DeliverableKind.MIGRATION_TOOL),
                DeliverableRequirement(
                    "worker",
                    DeliverableKind.WORKER,
                    smoke_profile_ref="smoke:worker-start",
                    smoke_profile_digest=SMOKE_PROFILE_DIGEST_WORKER,
                    smoke_required=True,
                ),
            ),
        )
        receipt = self.evaluate(
            self.observation(
                "migrator", presence=Presence.MISSING, identity_ref=None, smoke_status=SmokeStatus.NOT_REQUIRED
            ),
            self.observation("worker", smoke_status=SmokeStatus.FAIL),
            manifest=manifest,
        )
        self.assertEqual("INCOMPLETE", receipt["verdict"])
        self.assertEqual(["migrator"], receipt["missing_required"])
        self.assertEqual(
            [
                {
                    "deliverable_id": "worker",
                    "smoke_status": "FAIL",
                    "expected_smoke_profile_ref": "smoke:worker-start",
                    "observed_smoke_profile_ref": "smoke:worker-start",
                }
            ],
            receipt["smoke_failures"],
        )

    def test_contract_schemas_are_valid_json_and_match_reference_document_shape(self) -> None:
        manifest_schema = json.loads((ROOT / "contracts" / "release-deliverable-manifest.schema.json").read_text())
        receipt_schema = json.loads((ROOT / "contracts" / "artifact-closure-receipt.schema.json").read_text())
        self.assertEqual(1, manifest_schema["properties"]["schema_version"]["const"])
        self.assertEqual("object", manifest_schema["properties"]["deliverables"]["type"])
        self.assertEqual("artifact_closure", receipt_schema["properties"]["receipt_kind"]["const"])
        self.assertEqual(
            "^(?:[0-9a-f]{40}|[0-9a-f]{64})$",
            receipt_schema["properties"]["source_revision"]["pattern"],
        )
        self.assertIn("artifact_evidence_digest", receipt_schema["required"])
        self.assertEqual("object", receipt_schema["properties"]["observed"]["type"])
        observed_schema = receipt_schema["properties"]["observed"]["additionalProperties"]
        self.assertIn("smoke_profile_ref", observed_schema["required"])
        self.assertIn("smoke_profile_digest", observed_schema["required"])
        self.assertIn("evidence_digest", observed_schema["required"])
        self.assertNotIn("artifact_digest", observed_schema["properties"])
        self.assertNotIn(
            "artifact_digest",
            receipt_schema["properties"]["unexpected_components"]["additionalProperties"]["properties"],
        )
        self.assertIn("allOf", observed_schema)
        self.assertEqual("object", receipt_schema["properties"]["unexpected_components"]["type"])
        manifest_doc = manifest_document(self.manifest())
        self.assertEqual(1, manifest_doc["schema_version"])
        self.assertIsInstance(manifest_doc["deliverables"], dict)
        self.assertEqual({"host", "stewardctl", "dev-helper"}, set(manifest_doc["deliverables"]))
        Draft202012Validator(manifest_schema).validate(manifest_doc)
        self.assertIn("unexpected_component_dispositions", manifest_doc)
        receipt = self.evaluate(
            self.observation("host", identity_ref="entrypoint:ProjectSteward.Host"),
            self.observation("stewardctl", identity_ref="entrypoint:stewardctl"),
        )
        schema_only_invalid = json.loads(json.dumps(receipt))
        invalid_observation = schema_only_invalid["observed"]["stewardctl"]
        invalid_observation["presence"] = "MISSING"
        invalid_observation["identity_ref"] = "entrypoint:stewardctl"
        invalid_observation["smoke_status"] = "PASS"
        self.assertFalse(Draft202012Validator(receipt_schema).is_valid(schema_only_invalid))
        schema_only_cross_artifact = json.loads(json.dumps(receipt))
        schema_only_cross_artifact["observed"]["host"]["artifact_digest"] = DIGEST_2
        self.assertFalse(Draft202012Validator(receipt_schema).is_valid(schema_only_cross_artifact))
        duplicate_prone_observations = json.loads(json.dumps(receipt))
        duplicate_prone_observations["observed"] = [
            receipt["observed"]["host"],
            receipt["observed"]["host"],
        ]
        self.assertFalse(Draft202012Validator(receipt_schema).is_valid(duplicate_prone_observations))
        duplicate_prone_unexpected = json.loads(json.dumps(receipt))
        duplicate_prone_unexpected["unexpected_components"] = [
            {
                "criticality": "critical",
                "disposition": "unresolved",
                "evidence_ref": "evidence:package-inventory",
                "evidence_digest": CLAIM_EVIDENCE_DIGEST,
            },
            {
                "criticality": "non_critical",
                "disposition": "allowed",
                "evidence_ref": "evidence:other-inventory",
                "evidence_digest": EVIDENCE_DIGEST_2,
            },
        ]
        self.assertFalse(Draft202012Validator(receipt_schema).is_valid(duplicate_prone_unexpected))
        duplicate_prone_array_document = dict(manifest_doc)
        duplicate_prone_array_document["deliverables"] = [{"id": "dup"}, {"id": "dup"}]
        self.assertFalse(Draft202012Validator(manifest_schema).is_valid(duplicate_prone_array_document))


if __name__ == "__main__":
    unittest.main()
