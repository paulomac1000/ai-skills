from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from contracts.diagnostic_egress import (  # noqa: E402
    DiagnosticClassification,
    DiagnosticField,
    DiagnosticFieldPolicy,
    DiagnosticPolicy,
    DiagnosticReasonPolicy,
    build_safe_diagnostic,
    classify_and_build,
    validate_diagnostic_egress_semantics,
)


POLICY = DiagnosticPolicy(
    revision="diagnostic-egress/v1",
    reasons={
        "upstream.invalid_request": DiagnosticReasonPolicy(
            category="upstream",
            severity="error",
            fields={
                "status_code": DiagnosticFieldPolicy(
                    provenances=frozenset({"provider_code"}),
                    integer_range=(100, 599),
                ),
                "operation": DiagnosticFieldPolicy(
                    provenances=frozenset({"canonical_identifier"}),
                    allowed_strings=frozenset({"template_validate"}),
                ),
            },
        )
    },
)


class DiagnosticEgressTests(unittest.TestCase):
    def test_known_reason_emits_only_allowlisted_typed_fields(self) -> None:
        record = build_safe_diagnostic(
            DiagnosticClassification(
                category="upstream",
                reason_code="upstream.invalid_request",
                severity="error",
                fields=(
                    DiagnosticField("status_code", 400, "provider_code"),
                    DiagnosticField("operation", "template_validate", "canonical_identifier"),
                ),
            ),
            policy=POLICY,
            raw_detail_ref="forensic://error-42",
        )
        self.assertEqual(record["reason_code"], "upstream.invalid_request")
        self.assertFalse(record["source_payload_included"])
        self.assertEqual(record["raw_detail_ref"], "forensic://error-42")
        self.assertEqual(validate_diagnostic_egress_semantics(record, policy=POLICY), ())
        self.assertNotIn("message", record)
        self.assertNotIn("detail", record)

    def test_unknown_or_classifier_failure_falls_back_without_raw_text(self) -> None:
        payload = "HTTP 400: Template {{ states('sensor.secret') }} is invalid"
        for classifier in (
            lambda _raw: None,
            lambda _raw: DiagnosticClassification("upstream", "provider.wording.changed", "error"),
            lambda _raw: (_ for _ in ()).throw(RuntimeError(payload)),
        ):
            record = classify_and_build(payload, classifier=classifier, policy=POLICY)
            encoded = json.dumps(record, sort_keys=True, ensure_ascii=False)
            self.assertEqual(record["reason_code"], "diagnostic.unclassified")
            self.assertFalse(record["source_payload_included"])
            self.assertNotIn(payload, encoded)
            self.assertNotIn("sensor.secret", encoded)

    def test_adversarial_provider_and_source_text_cannot_cross_protected_sink(self) -> None:
        variants = [
            "Bad template: {{ states('sensor.office') }}",
            'Provider says: "bad \\"quoted\\" template"',
            "New prefix -- rejected source=<payload-tail>",
            "line one\nline two\n{{ dangerous }}",
            "unicode Ω snowman ☃ control\x01tail",
            "x" * 20_000 + "<LONG-SENTINEL>",
            "WrapperError(InnerError(template='{{ nested }}'))",
            "api_key=sk-live-looking-but-test-only",
            "ordinary-user-value-with-description text",
            "SENSITIVE_TEMPLATE_TAIL",
            b"\xff\xfe\x80malformed",
        ]
        for raw in variants:
            raw_repr = raw if isinstance(raw, str) else repr(raw)
            with self.subTest(raw=raw_repr[:80]):
                def hostile_classifier(value: object) -> DiagnosticClassification:
                    return DiagnosticClassification(
                        category="upstream",
                        reason_code="upstream.invalid_request",
                        severity="error",
                        fields=(DiagnosticField("operation", str(value), "canonical_identifier"),),
                    )

                record = classify_and_build(raw, classifier=hostile_classifier, policy=POLICY)
                serialized = json.dumps(record, ensure_ascii=False, sort_keys=True)
                self.assertEqual(record["reason_code"], "diagnostic.unclassified")
                self.assertEqual(record["safe_fields"], [])
                self.assertFalse(record["source_payload_included"])
                self.assertNotIn(raw_repr, serialized)

    def test_apostrophe_and_alternate_wording_regression_does_not_leak_template_tail(self) -> None:
        raw = "HTTP 400 alternate wording: couldn't parse '{{ states('sensor.kitchen') }}' tail=SENSITIVE_TEMPLATE_TAIL"

        def historical_shape_classifier(value: object) -> DiagnosticClassification:
            return DiagnosticClassification(
                category="upstream",
                reason_code="upstream.invalid_request",
                severity="error",
                fields=(DiagnosticField("operation", str(value).split("couldn't", 1)[-1], "canonical_identifier"),),
            )

        record = classify_and_build(raw, classifier=historical_shape_classifier, policy=POLICY)
        for sink in ("stderr", "receipt", "summary"):
            persisted = f"{sink}:{json.dumps(record, ensure_ascii=False, sort_keys=True)}"
            self.assertNotIn("SENSITIVE_TEMPLATE_TAIL", persisted)
            self.assertNotIn("sensor.kitchen", persisted)
            self.assertNotIn("couldn't", persisted)
        self.assertEqual(record["reason_code"], "diagnostic.unclassified")

    def test_raw_detail_is_only_an_opaque_reference(self) -> None:
        for unsafe in ("raw error body with spaces", "SENSITIVE_TEMPLATE_TAIL", "template/tail"):
            with self.subTest(unsafe=unsafe):
                record = build_safe_diagnostic(None, policy=POLICY, raw_detail_ref=unsafe)
                self.assertIsNone(record["raw_detail_ref"])
        safe = build_safe_diagnostic(None, policy=POLICY, raw_detail_ref="vault://diag/abc-123")
        self.assertEqual(safe["raw_detail_ref"], "vault://diag/abc-123")

    def test_policy_snapshot_is_immutable_after_construction(self) -> None:
        mutable_fields = {
            "operation": DiagnosticFieldPolicy(
                provenances=frozenset({"canonical_identifier"}),
                allowed_strings=frozenset({"template_validate"}),
            )
        }
        mutable_reasons = {
            "upstream.invalid_request": DiagnosticReasonPolicy("upstream", "error", mutable_fields)
        }
        policy = DiagnosticPolicy("snapshot/v1", mutable_reasons)
        mutable_fields["payload"] = DiagnosticFieldPolicy(
            provenances=frozenset({"canonical_identifier"}),
            allowed_strings=frozenset({"SENSITIVE_TEMPLATE_TAIL"}),
        )
        mutable_reasons["new.reason"] = DiagnosticReasonPolicy("upstream", "error", {})
        record = build_safe_diagnostic(
            DiagnosticClassification(
                "upstream",
                "upstream.invalid_request",
                "error",
                (DiagnosticField("payload", "SENSITIVE_TEMPLATE_TAIL", "canonical_identifier"),),
            ),
            policy=policy,
        )
        self.assertEqual(record["reason_code"], "diagnostic.unclassified")
        self.assertNotIn("new.reason", policy.reasons)

    def test_policy_blocks_wrong_provenance_unknown_fields_and_duplicates(self) -> None:
        bad = [
            (DiagnosticField("operation", "validate", "provider_code"),),
            (DiagnosticField("message", "validate", "canonical_identifier"),),
            (
                DiagnosticField("operation", "validate", "canonical_identifier"),
                DiagnosticField("operation", "again", "canonical_identifier"),
            ),
        ]
        for fields in bad:
            record = build_safe_diagnostic(
                DiagnosticClassification("upstream", "upstream.invalid_request", "error", fields),
                policy=POLICY,
            )
            self.assertEqual(record["reason_code"], "diagnostic.unclassified")
            self.assertEqual(record["safe_fields"], [])

    def test_semantic_validator_requires_current_policy(self) -> None:
        valid = build_safe_diagnostic(None, policy=POLICY)
        self.assertEqual(
            validate_diagnostic_egress_semantics(valid),
            ("current diagnostic policy is required for semantic validation",),
        )

    def test_semantic_validator_rejects_freeform_or_payload_bearing_records(self) -> None:
        valid = build_safe_diagnostic(None, policy=POLICY)
        payload_bearing = {**valid, "source_payload_included": True}
        self.assertTrue(validate_diagnostic_egress_semantics(payload_bearing, policy=POLICY))

        freeform = {
            **valid,
            "reason_code": "upstream.invalid_request",
            "category": "upstream",
            "safe_fields": [
                {"name": "operation", "value": "raw provider prose here", "provenance": "canonical_identifier"}
            ],
        }
        findings = validate_diagnostic_egress_semantics(freeform, policy=POLICY)
        self.assertTrue(any("safe scalar" in item for item in findings))

        extra_message = {**valid, "message": "copied source payload"}
        findings = validate_diagnostic_egress_semantics(extra_message, policy=POLICY)
        self.assertTrue(any("unknown diagnostic fields" in item for item in findings))

        forged_fallback = {**valid, "category": "upstream", "severity": "info"}
        findings = validate_diagnostic_egress_semantics(forged_fallback, policy=POLICY)
        self.assertTrue(any("fallback category/severity" in item for item in findings))

        missing_field = dict(valid)
        missing_field.pop("raw_detail_ref")
        findings = validate_diagnostic_egress_semantics(missing_field, policy=POLICY)
        self.assertTrue(any("missing diagnostic fields" in item for item in findings))

    def test_schema_structurally_forbids_freeform_diagnostic_members(self) -> None:
        schema = json.loads((ROOT / "contracts/diagnostic-egress.schema.json").read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["source_payload_included"], {"const": False})
        self.assertNotIn("message", schema["properties"])
        self.assertNotIn("detail", schema["properties"])
        self.assertLessEqual(schema["properties"]["safe_fields"]["maxItems"], 16)


if __name__ == "__main__":
    unittest.main()
