from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

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
UnexpectedCriticality = MODULE.UnexpectedCriticality
UnexpectedDisposition = MODULE.UnexpectedDisposition
classify_artifact_closure_currentness = MODULE.classify_artifact_closure_currentness
evaluate_artifact_closure = MODULE.evaluate_artifact_closure
manifest_digest = MODULE.manifest_digest
manifest_document = MODULE.manifest_document
verify_artifact_closure_receipt_integrity = MODULE.verify_artifact_closure_receipt_integrity

DIGEST_1 = "sha256:" + "1" * 64
DIGEST_2 = "sha256:" + "2" * 64


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
                    smoke_required=True,
                ),
                DeliverableRequirement(
                    "stewardctl",
                    DeliverableKind.OPERATOR_ENTRYPOINT,
                    expected_identity_ref="entrypoint:stewardctl",
                    smoke_profile_ref="smoke:stewardctl-help",
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
        smoke_status: SmokeStatus = SmokeStatus.PASS,
    ) -> DeliverableObservation:
        return DeliverableObservation(
            deliverable_id=deliverable_id,
            artifact_digest=DIGEST_1,
            presence=presence,
            identity_ref=identity_ref,
            smoke_status=smoke_status,
            evidence_ref=f"evidence:{deliverable_id}",
        )

    def evaluate(self, *observations: DeliverableObservation, manifest=None, unexpected=()):
        return evaluate_artifact_closure(
            manifest or self.manifest(),
            tuple(observations),
            source_revision="integrated-sha-090",
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
                current_source_revision="integrated-sha-090",
                current_artifact_digest=DIGEST_1,
                current_artifact_evidence_ref="artifact-evidence:project-steward-090",
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
                current_source_revision="integrated-sha-090",
                current_artifact_digest=DIGEST_1,
                current_artifact_evidence_ref="artifact-evidence:project-steward-090",
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
                current_source_revision="integrated-sha-090",
                current_artifact_digest=DIGEST_1,
                current_artifact_evidence_ref="artifact-evidence:project-steward-090",
                current_manifest=manifest,
            ),
        )
        self.assertEqual(
            ClosureCurrentness.STALE,
            classify_artifact_closure_currentness(
                receipt,
                current_source_revision="integrated-sha-090",
                current_artifact_digest=DIGEST_2,
                current_artifact_evidence_ref="artifact-evidence:project-steward-090",
                current_manifest=manifest,
            ),
        )
        self.assertEqual(
            ClosureCurrentness.STALE,
            classify_artifact_closure_currentness(
                receipt,
                current_source_revision="different-source-sha",
                current_artifact_digest=DIGEST_1,
                current_artifact_evidence_ref="artifact-evidence:project-steward-090",
                current_manifest=manifest,
            ),
        )
        self.assertEqual(
            ClosureCurrentness.STALE,
            classify_artifact_closure_currentness(
                receipt,
                current_source_revision="integrated-sha-090",
                current_artifact_digest=DIGEST_1,
                current_artifact_evidence_ref="artifact-evidence:new-profile",
                current_manifest=manifest,
            ),
        )
        self.assertEqual(
            ClosureCurrentness.UNKNOWN,
            classify_artifact_closure_currentness(
                receipt,
                current_source_revision=None,
                current_artifact_digest=DIGEST_1,
                current_artifact_evidence_ref="artifact-evidence:project-steward-090",
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
                current_source_revision="integrated-sha-090",
                current_artifact_digest=DIGEST_1,
                current_artifact_evidence_ref="artifact-evidence:project-steward-090",
                current_manifest=changed_manifest,
            ),
        )

    def test_unexpected_critical_component_requires_policy_disposition(self) -> None:
        unexpected = UnexpectedComponentObservation(
            component_ref="entrypoint:debug-admin",
            artifact_digest=DIGEST_1,
            criticality=UnexpectedCriticality.CRITICAL,
            disposition=UnexpectedDisposition.UNRESOLVED,
            evidence_ref="evidence:package-inventory",
        )
        receipt = self.evaluate(
            self.observation("host", identity_ref="entrypoint:ProjectSteward.Host"),
            self.observation("stewardctl", identity_ref="entrypoint:stewardctl"),
            unexpected=(unexpected,),
        )
        self.assertEqual("INCOMPLETE", receipt["verdict"])
        self.assertEqual(["entrypoint:debug-admin"], receipt["blocking_unexpected"])

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
            smoke_status=SmokeStatus.PASS,
            evidence_ref="evidence:wrong-artifact",
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
        self.assertEqual([{"deliverable_id": "worker", "smoke_status": "FAIL"}], receipt["smoke_failures"])

    def test_contract_schemas_are_valid_json_and_match_reference_document_shape(self) -> None:
        manifest_schema = json.loads((ROOT / "contracts" / "release-deliverable-manifest.schema.json").read_text())
        receipt_schema = json.loads((ROOT / "contracts" / "artifact-closure-receipt.schema.json").read_text())
        self.assertEqual(1, manifest_schema["properties"]["schema_version"]["const"])
        self.assertEqual("artifact_closure", receipt_schema["properties"]["receipt_kind"]["const"])
        self.assertEqual(1, manifest_document(self.manifest())["schema_version"])


if __name__ == "__main__":
    unittest.main()
