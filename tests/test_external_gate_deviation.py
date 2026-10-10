from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "contracts" / "external_gate_deviation.py"
SPEC = importlib.util.spec_from_file_location("external_gate_deviation", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

CatchupObligation = MODULE.CatchupObligation
CatchupState = MODULE.CatchupState
FailureClass = MODULE.FailureClass
GateExecutionState = MODULE.GateExecutionState
GateIncident = MODULE.GateIncident
GateObservation = MODULE.GateObservation
GateVerdict = MODULE.GateVerdict
IncidentScope = MODULE.IncidentScope
RetryMode = MODULE.RetryMode
SubstituteEvidence = MODULE.SubstituteEvidence
SubstituteReproduction = MODULE.SubstituteReproduction
build_external_gate_receipt = MODULE.build_external_gate_receipt
derive_external_gate_decision = MODULE.derive_external_gate_decision
satisfy_catchup = MODULE.satisfy_catchup
verify_external_gate_receipt_integrity = MODULE.verify_external_gate_receipt_integrity

D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64
D3 = "sha256:" + "3" * 64
D4 = "sha256:" + "4" * 64
D5 = "sha256:" + "5" * 64
NOW = datetime(2026, 10, 8, 14, 30, tzinfo=timezone.utc)


class ExternalGateDeviationTests(unittest.TestCase):
    def outage_observation(self) -> GateObservation:
        return GateObservation(
            state=GateExecutionState.NOT_EXECUTED,
            product_verdict=GateVerdict.UNKNOWN,
            repository_steps_executed=False,
            observed_at="2026-10-08T14:00:00Z",
            evidence_ref="provider-run:42",
            evidence_digest=D1,
            failure_class=FailureClass.QUOTA,
        )

    def incident(self) -> GateIncident:
        return GateIncident(
            fingerprint=D2,
            scope=IncidentScope.ACCOUNT,
            scope_ref="provider-account:owner",
            first_observed_at="2026-10-08T13:00:00Z",
            last_observed_at="2026-10-08T14:00:00Z",
            fresh_until="2026-10-08T16:00:00Z",
        )

    def receipt(self, subject: str = "sha:aaa", **kwargs):
        values = {
            "gate_id": "external/ci",
            "provider": "external-provider",
            "expected_subject_ref": subject,
            "policy_revision": "policy:delivery/v7",
            "observation": self.outage_observation(),
            "retry_mode": RetryMode.SUPPRESS_UNTIL_CHANGE,
            "incident": self.incident(),
        }
        values.update(kwargs)
        return build_external_gate_receipt(**values)

    def reproduction(self, subject: str) -> SubstituteReproduction:
        return SubstituteReproduction(
            original_workflow_digest=D1,
            exact_subject_ref=subject,
            source_checkout="clean_detached_or_equivalent",
            environment_digest=D2,
            inherited_workspace_state=False,
            isolation_ref="isolation:clean-room",
            command_ref="command:full-gate",
            report_digest=D3,
        )

    def test_zero_runner_zero_step_is_unavailable_not_product_result(self) -> None:
        receipt = self.receipt()
        self.assertEqual("NOT_EXECUTED", receipt["observation"]["state"])
        self.assertEqual("UNKNOWN", receipt["observation"]["product_verdict"])
        decision = derive_external_gate_decision(receipt, now=NOW)
        self.assertEqual("BLOCKED_UNAVAILABLE", decision["gate_disposition"])
        self.assertEqual("SUPPRESSED", decision["retry_disposition"])

    def test_incident_reuse_is_candidate_independent_and_reopens_on_signal(self) -> None:
        first = self.receipt("sha:first")
        second = self.receipt("sha:second")
        self.assertEqual(first["incident"]["fingerprint"], second["incident"]["fingerprint"])
        self.assertEqual("SUPPRESSED", derive_external_gate_decision(second, now=NOW)["retry_disposition"])
        changed = derive_external_gate_decision(
            second,
            now=NOW,
            changed_signals=("provider_generation_change",),
        )
        self.assertEqual("ELIGIBLE", changed["retry_disposition"])

    def test_authorized_substitute_stays_distinct_and_requires_clean_exact_subject(self) -> None:
        subject = "sha:aaa"
        substitute = SubstituteEvidence(
            allowed=True,
            authority_ref="policy:path-b",
            profile_ref="substitute:clean-room/v1",
            exact_subject_ref=subject,
            evidence_ref="report:clean-room",
            evidence_digest=D4,
            verdict=GateVerdict.PASS,
            reproduction=self.reproduction(subject),
        )
        receipt = self.receipt(
            subject,
            substitute=substitute,
            catchup=CatchupObligation(True, "sha:integrated", CatchupState.PENDING),
        )
        self.assertEqual("UNKNOWN", receipt["observation"]["product_verdict"])
        self.assertEqual("PASS_SUBSTITUTE", derive_external_gate_decision(receipt, now=NOW)["gate_disposition"])
        self.assertEqual("PENDING", receipt["catchup"]["state"])

        with self.assertRaisesRegex(ValueError, "exact current subject"):
            self.receipt(
                "sha:new",
                substitute=SubstituteEvidence(
                    allowed=True,
                    authority_ref="policy:path-b",
                    profile_ref="substitute:clean-room/v1",
                    exact_subject_ref="sha:old",
                    evidence_ref="report:old",
                    evidence_digest=D4,
                    verdict=GateVerdict.PASS,
                    reproduction=self.reproduction("sha:old"),
                ),
            )

    def test_catchup_requires_exact_original_executed_pass(self) -> None:
        receipt = self.receipt(catchup=CatchupObligation(True, "sha:integrated", CatchupState.PENDING))
        passed = GateObservation(
            GateExecutionState.EXECUTED, GateVerdict.PASS, True,
            "2026-10-08T15:00:00Z", "provider-run:green", D3,
        )
        provider = receipt["gate"]["provider"]
        gate_id = receipt["gate"]["gate_id"]
        kwargs = dict(provider=provider, gate_id=gate_id, provider_observation=passed)
        with self.assertRaisesRegex(ValueError, "unrelated provider run"):
            satisfy_catchup(receipt, observed_subject_ref="sha:other", **kwargs)
        with self.assertRaisesRegex(ValueError, "original provider gate"):
            satisfy_catchup(receipt, observed_subject_ref="sha:integrated", provider="other", gate_id=gate_id, provider_observation=passed)
        for state, verdict, executed in [
            (GateExecutionState.NOT_EXECUTED, GateVerdict.UNKNOWN, False),
            (GateExecutionState.UNKNOWN, GateVerdict.UNKNOWN, None),
            (GateExecutionState.EXECUTED, GateVerdict.FAIL, True),
        ]:
            with self.subTest(state=state, verdict=verdict):
                blocked = GateObservation(
                    state, verdict, executed, "2026-10-08T15:00:00Z",
                    "provider-run:blocked", D3,
                    FailureClass.BILLING if state is not GateExecutionState.EXECUTED else FailureClass.NONE,
                )
                with self.assertRaisesRegex(ValueError, "requires executed original gate PASS"):
                    satisfy_catchup(receipt, observed_subject_ref="sha:integrated", provider=provider, gate_id=gate_id, provider_observation=blocked)
        # Historical PASS, simultaneous PASS, and offset-equivalent timestamp must not
        # close an obligation created by the 14:00Z original-gate non-execution.
        for earlier_or_equal in (
            "2026-10-08T13:59:59Z",
            "2026-10-08T14:00:00Z",
            "2026-10-08T16:00:00+02:00",
        ):
            with self.subTest(observed_at=earlier_or_equal):
                replayed = GateObservation(
                    GateExecutionState.EXECUTED, GateVerdict.PASS, True,
                    earlier_or_equal, "provider-run:historical", D4,
                )
                with self.assertRaisesRegex(ValueError, "postdate the deviation observation"):
                    satisfy_catchup(
                        receipt, observed_subject_ref="sha:integrated",
                        provider=provider, gate_id=gate_id, provider_observation=replayed,
                    )
        just_after = GateObservation(
            GateExecutionState.EXECUTED, GateVerdict.PASS, True,
            "2026-10-08T16:00:01+02:00", "provider-run:just-after", D4,
        )
        self.assertEqual(
            "SATISFIED",
            satisfy_catchup(
                receipt, observed_subject_ref="sha:integrated",
                provider=provider, gate_id=gate_id, provider_observation=just_after,
            )["catchup"]["state"],
        )
        satisfied = satisfy_catchup(receipt, observed_subject_ref="sha:integrated", **kwargs)
        self.assertEqual("SATISFIED", satisfied["catchup"]["state"])
        self.assertTrue(verify_external_gate_receipt_integrity(satisfied))
        with self.assertRaisesRegex(ValueError, "not pending"):
            satisfy_catchup(satisfied, observed_subject_ref="sha:integrated", **kwargs)

    def test_three_historical_products_share_one_generic_contract(self) -> None:
        fixtures = (
            ("opencode-stack-guides/pr-199", "sha:osg", "policy:osg/path-b"),
            ("project-steward/0.9.0", "sha:project-steward", "policy:project-steward/path-b"),
            ("blog-steward/release", "sha:blog", "policy:blog-steward/path-b"),
        )
        for gate_id, subject, authority in fixtures:
            with self.subTest(gate_id=gate_id):
                substitute = SubstituteEvidence(
                    allowed=True,
                    authority_ref=authority,
                    profile_ref="substitute:clean-room/v1",
                    exact_subject_ref=subject,
                    evidence_ref=f"report:{gate_id}",
                    evidence_digest=D4,
                    verdict=GateVerdict.PASS,
                    reproduction=self.reproduction(subject),
                )
                receipt = build_external_gate_receipt(
                    gate_id=gate_id,
                    provider="external-provider",
                    expected_subject_ref=subject,
                    policy_revision="policy:delivery/v7",
                    observation=self.outage_observation(),
                    retry_mode=RetryMode.SUPPRESS_UNTIL_CHANGE,
                    incident=self.incident(),
                    substitute=substitute,
                    catchup=CatchupObligation(True, None, CatchupState.PENDING),
                )
                self.assertEqual(
                    "PASS_SUBSTITUTE",
                    derive_external_gate_decision(receipt, now=NOW)["gate_disposition"],
                )

    def test_recomputed_digest_cannot_admit_semantic_forgery(self) -> None:
        receipt = self.receipt()
        receipt["observation"].update(
            state="EXECUTED",
            product_verdict="PASS",
            repository_steps_executed=False,
            failure_class="none",
        )
        receipt.pop("receipt_digest")
        receipt["receipt_digest"] = MODULE._doc_digest(receipt)
        self.assertFalse(verify_external_gate_receipt_integrity(receipt))
        self.assertEqual("UNKNOWN", derive_external_gate_decision(receipt, now=NOW)["gate_disposition"])

    def test_unknown_fields_and_wrong_boolean_types_fail_closed(self) -> None:
        receipt = self.receipt()
        receipt["candidate_can_override"] = True
        receipt.pop("receipt_digest")
        receipt["receipt_digest"] = MODULE._doc_digest(receipt)
        self.assertFalse(verify_external_gate_receipt_integrity(receipt))

        receipt = self.receipt()
        receipt["substitute"]["allowed"] = 1
        receipt.pop("receipt_digest")
        receipt["receipt_digest"] = MODULE._doc_digest(receipt)
        self.assertFalse(verify_external_gate_receipt_integrity(receipt))

    def test_schema_rejects_core_semantic_forgery_and_unknown_fields(self) -> None:
        schema = json.loads(
            (ROOT / "contracts" / "external-gate-deviation.schema.json").read_text(
                encoding="utf-8"
            )
        )
        validator = Draft202012Validator(schema)
        receipt = self.receipt()
        self.assertTrue(validator.is_valid(receipt), list(validator.iter_errors(receipt)))

        forged = json.loads(json.dumps(receipt))
        forged["observation"].update(
            state="EXECUTED",
            product_verdict="PASS",
            repository_steps_executed=False,
            failure_class="none",
        )
        self.assertFalse(validator.is_valid(forged))

        unknown = json.loads(json.dumps(receipt))
        unknown["candidate_can_override"] = True
        self.assertFalse(validator.is_valid(unknown))


class CanonicalSchemaParityTests(unittest.TestCase):
    """ai-skills #166: the canonical owner enforces the same input domain and exact JSON
    types as the published schema, at construction and integrity boundaries."""

    def base_receipt(self, **kwargs):
        values = {
            "gate_id": "external/ci",
            "provider": "external-provider",
            "expected_subject_ref": "sha:candidate-a",
            "policy_revision": "policy:delivery/v7",
            "observation": GateObservation(
                state=GateExecutionState.NOT_EXECUTED,
                product_verdict=GateVerdict.UNKNOWN,
                repository_steps_executed=False,
                observed_at="2026-10-08T14:00:00Z",
                evidence_ref="provider-run:42",
                evidence_digest=D1,
                failure_class=FailureClass.QUOTA,
            ),
            "retry_mode": RetryMode.SUPPRESS_UNTIL_CHANGE,
            "incident": GateIncident(
                fingerprint=D2,
                scope=IncidentScope.ACCOUNT,
                scope_ref="provider-account:owner",
                first_observed_at="2026-10-08T13:00:00Z",
                last_observed_at="2026-10-08T14:00:00Z",
                fresh_until="2026-10-08T16:00:00Z",
            ),
        }
        values.update(kwargs)
        return build_external_gate_receipt(**values)

    def _tampered(self, receipt, mutate):
        document = json.loads(json.dumps(receipt))
        mutate(document)
        document.pop("receipt_digest")
        document["receipt_digest"] = MODULE._doc_digest(document)
        return document

    def _schema_validator(self):
        schema = json.loads(
            (ROOT / "contracts" / "external-gate-deviation.schema.json").read_text(encoding="utf-8")
        )
        return Draft202012Validator(schema)

    def test_reopen_cardinality_is_enforced_at_construction(self) -> None:
        for count in (33, 40, 200):
            with self.subTest(count=count):
                with self.assertRaisesRegex(ValueError, "schema limit of 32"):
                    self.base_receipt(
                        incident=GateIncident(
                            fingerprint=D2,
                            scope=IncidentScope.ACCOUNT,
                            scope_ref="provider-account:owner",
                            first_observed_at="2026-10-08T13:00:00Z",
                            last_observed_at="2026-10-08T14:00:00Z",
                            fresh_until=None,
                            reopen_on=tuple(f"signal_{i}" for i in range(count)),
                        )
                    )
        accepted = self.base_receipt(
            incident=GateIncident(
                fingerprint=D2,
                scope=IncidentScope.ACCOUNT,
                scope_ref="provider-account:owner",
                first_observed_at="2026-10-08T13:00:00Z",
                last_observed_at="2026-10-08T14:00:00Z",
                fresh_until=None,
                reopen_on=tuple(f"signal_{i}" for i in range(32)),
            )
        )
        self.assertEqual(32, len(accepted["incident"]["reopen_on"]))
        self.assertTrue(verify_external_gate_receipt_integrity(accepted))

    def test_empty_and_duplicate_signals_remain_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty and unique"):
            self.base_receipt(
                incident=GateIncident(
                    fingerprint=D2,
                    scope=IncidentScope.ACCOUNT,
                    scope_ref="provider-account:owner",
                    first_observed_at="2026-10-08T13:00:00Z",
                    last_observed_at="2026-10-08T14:00:00Z",
                    fresh_until=None,
                    reopen_on=(),
                )
            )
        with self.assertRaisesRegex(ValueError, "non-empty and unique"):
            self.base_receipt(
                incident=GateIncident(
                    fingerprint=D2,
                    scope=IncidentScope.ACCOUNT,
                    scope_ref="provider-account:owner",
                    first_observed_at="2026-10-08T13:00:00Z",
                    last_observed_at="2026-10-08T14:00:00Z",
                    fresh_until=None,
                    reopen_on=("provider_generation_change", "provider_generation_change"),
                )
            )

    def test_schema_version_requires_the_exact_integer(self) -> None:
        receipt = self.base_receipt()
        version = receipt["schema_version"]
        self.assertIs(type(version), int)
        self.assertNotIsInstance(version, bool)
        # The canonical owner rejects every non-integer representation; ``True == 1.0 ==
        # 1`` under Python equality is exactly the hole being closed.
        for bad in (True, False, 1.0, "1"):
            with self.subTest(schema_version=bad):
                tampered = self._tampered(receipt, lambda d, v=bad: d.__setitem__("schema_version", v))
                self.assertFalse(verify_external_gate_receipt_integrity(tampered))
        # Type-distinct representations are also schema-invalid. (JSON Schema compares
        # ``const: 1`` with numeric equality, so 1.0 is schema-accepted and only the
        # evaluator rejects it -- recorded behavior, not a parity gap.)
        for bad in (True, False, "1"):
            with self.subTest(schema_level=bad):
                tampered = self._tampered(receipt, lambda d, v=bad: d.__setitem__("schema_version", v))
                self.assertFalse(self._schema_validator().is_valid(tampered))

    def test_oversized_reopen_signals_survive_integrity_verification(self) -> None:
        # A digest-consistent tampering cannot resurrect an over-cardinality receipt.
        receipt = self.base_receipt()
        tampered = self._tampered(
            receipt,
            lambda d: d["incident"].__setitem__(
                "reopen_on", [*d["incident"]["reopen_on"], *[f"extra_{i}" for i in range(40)]]
            ),
        )
        self.assertEqual(43, len(tampered["incident"]["reopen_on"]))
        self.assertFalse(verify_external_gate_receipt_integrity(tampered))
        self.assertFalse(self._schema_validator().is_valid(tampered))

    def test_cross_validation_proves_evaluator_and_schema_agree(self) -> None:
        validator = self._schema_validator()
        receipts = [
            self.base_receipt(),
            self.base_receipt(
                expected_subject_ref="sha:candidate-a",
                substitute=SubstituteEvidence(
                    allowed=True,
                    authority_ref="policy:path-b",
                    profile_ref="substitute:clean-room/v1",
                    exact_subject_ref="sha:candidate-a",
                    evidence_ref="report:clean-room",
                    evidence_digest=D4,
                    verdict=GateVerdict.PASS,
                    reproduction=SubstituteReproduction(
                        original_workflow_digest=D1,
                        exact_subject_ref="sha:candidate-a",
                        source_checkout="clean_detached_or_equivalent",
                        environment_digest=D2,
                        inherited_workspace_state=False,
                        isolation_ref="isolation:clean-room",
                        command_ref="command:full-gate",
                        report_digest=D3,
                    ),
                ),
                catchup=CatchupObligation(True, "sha:integrated", CatchupState.PENDING),
            ),
            self.base_receipt(
                observation=GateObservation(
                    state=GateExecutionState.EXECUTED,
                    product_verdict=GateVerdict.FAIL,
                    repository_steps_executed=True,
                    observed_at="2026-10-08T20:00:00Z",
                    evidence_ref="provider-run:51",
                    evidence_digest=D5,
                    failure_class=FailureClass.NONE,
                ),
                retry_mode=RetryMode.NORMAL,
                incident=None,
            ),
        ]
        for index, receipt in enumerate(receipts):
            with self.subTest(receipt=index):
                self.assertTrue(verify_external_gate_receipt_integrity(receipt))
                self.assertTrue(validator.is_valid(receipt), list(validator.iter_errors(receipt)))

    def test_integrated_subject_catchup_semantics_are_preserved(self) -> None:
        # candidate A's obligation may name the legitimate integrated revision B; an
        # unrelated or replayed PASS must still fail.
        receipt = self.base_receipt(catchup=CatchupObligation(True, "sha:integrated", CatchupState.PENDING))
        passed = GateObservation(
            state=GateExecutionState.EXECUTED,
            product_verdict=GateVerdict.PASS,
            repository_steps_executed=True,
            observed_at="2026-10-08T18:00:00Z",
            evidence_ref="provider-run:77",
            evidence_digest=D5,
            failure_class=FailureClass.NONE,
        )
        satisfied = satisfy_catchup(
            receipt,
            observed_subject_ref="sha:integrated",
            provider="external-provider",
            gate_id="external/ci",
            provider_observation=passed,
        )
        self.assertEqual("SATISFIED", satisfied["catchup"]["state"])
        with self.assertRaisesRegex(ValueError, "unrelated provider run"):
            satisfy_catchup(
                receipt,
                observed_subject_ref="sha:untrusted-c",
                provider="external-provider",
                gate_id="external/ci",
                provider_observation=passed,
            )



if __name__ == "__main__":
    unittest.main()
