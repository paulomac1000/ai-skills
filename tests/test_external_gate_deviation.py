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
            "2026-10-08T10:00:00Z", "provider-run:green", D3,
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
                    state, verdict, executed, "2026-10-08T10:00:00Z",
                    "provider-run:blocked", D3,
                    FailureClass.BILLING if state is not GateExecutionState.EXECUTED else FailureClass.NONE,
                )
                with self.assertRaisesRegex(ValueError, "requires executed original gate PASS"):
                    satisfy_catchup(receipt, observed_subject_ref="sha:integrated", provider=provider, gate_id=gate_id, provider_observation=blocked)
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


if __name__ == "__main__":
    unittest.main()
