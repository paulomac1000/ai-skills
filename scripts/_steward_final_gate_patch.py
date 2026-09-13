from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str, label: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def update_json(path: str, mutate) -> None:
    target = ROOT / path
    value = json.loads(target.read_text(encoding="utf-8"))
    mutate(value)
    target.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


# Contract schemas: make the fields already used by the runtimes part of the governed contract.
def patch_job_schema(value: dict) -> None:
    required = value["required"]
    if "requestDigest" not in required:
        required.insert(required.index("status"), "requestDigest")
    value["properties"]["requestDigest"] = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}


def patch_receipt_schema(value: dict) -> None:
    required = value["required"]
    if "jobVersion" not in required:
        required.insert(required.index("capabilityIdentity"), "jobVersion")
    value["properties"]["jobVersion"] = {"type": "integer", "minimum": 0}


def patch_mutation_schema(value: dict) -> None:
    effect = value["$defs"]["effect"]
    required = effect["required"]
    for field, after in (
        ("operation_kind", "id"),
        ("capability_contract", "capability_ref"),
        ("finalization_reserve_ms", "minimum_budget_ms"),
    ):
        if field not in required:
            required.insert(required.index(after) + 1, field)
    props = effect["properties"]
    props["operation_kind"] = {"enum": ["submit", "cancel", "publication", "mutation"]}
    props["capability_contract"] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["source", "id", "revision", "digest"],
        "properties": {
            "source": {"type": "string", "minLength": 1},
            "id": {"type": "string", "minLength": 1},
            "revision": {"type": "string", "minLength": 1},
            "digest": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
        },
    }
    props["finalization_reserve_ms"] = {"type": "integer", "minimum": 0}


update_json("contracts/steward-job.schema.json", patch_job_schema)
update_json("contracts/external-operation-receipt.schema.json", patch_receipt_schema)
update_json("contracts/steward-mutation-policy.schema.json", patch_mutation_schema)

# Human-facing mutation policy template mirrors the governed schema.
replace_once(
    "skills/mcp-steward-architect/templates/mutation-policy.yaml.template",
    "    transition: dispatch-start\n    authority_source: steward-runtime",
    "    operation_kind: submit\n    transition: dispatch-start\n    authority_source: steward-runtime",
    "template submit operation kind",
)
replace_once(
    "skills/mcp-steward-architect/templates/mutation-policy.yaml.template",
    "    capability_ref: __CAPABILITY_ID__\n    durable_operation_required: true",
    "    capability_ref: __CAPABILITY_ID__\n    capability_contract:\n      source: __CAPABILITY_SOURCE__\n      id: __CAPABILITY_ID__\n      revision: __CAPABILITY_REVISION__\n      digest: __CAPABILITY_DIGEST__\n    durable_operation_required: true",
    "template submit capability contract",
)
replace_once(
    "skills/mcp-steward-architect/templates/mutation-policy.yaml.template",
    "    minimum_budget_ms: 1000\n    ambiguity_disposition: reconcile",
    "    minimum_budget_ms: 1000\n    finalization_reserve_ms: 500\n    ambiguity_disposition: reconcile",
    "template submit finalization reserve",
)
replace_once(
    "skills/mcp-steward-architect/templates/mutation-policy.yaml.template",
    "    transition: cancel-start\n    authority_source: steward-runtime",
    "    operation_kind: cancel\n    transition: cancel-start\n    authority_source: steward-runtime",
    "template cancel operation kind",
)
# Second capability occurrence and budget occurrence now remain unique after first replacements.
replace_once(
    "skills/mcp-steward-architect/templates/mutation-policy.yaml.template",
    "    capability_ref: __CAPABILITY_ID__\n    durable_operation_required: true",
    "    capability_ref: __CAPABILITY_ID__\n    capability_contract:\n      source: __CAPABILITY_SOURCE__\n      id: __CAPABILITY_ID__\n      revision: __CAPABILITY_REVISION__\n      digest: __CAPABILITY_DIGEST__\n    durable_operation_required: true",
    "template cancel capability contract",
)
replace_once(
    "skills/mcp-steward-architect/templates/mutation-policy.yaml.template",
    "    minimum_budget_ms: 1000\n    ambiguity_disposition: reconcile",
    "    minimum_budget_ms: 1000\n    finalization_reserve_ms: 500\n    ambiguity_disposition: reconcile",
    "template cancel finalization reserve",
)
replace_once(
    "skills/mcp-steward-architect/templates/mutation-policy.yaml.template",
    "    transition: completion-publish\n    authority_source: completion-gate",
    "    operation_kind: publication\n    transition: completion-publish\n    authority_source: completion-gate",
    "template publication operation kind",
)
replace_once(
    "skills/mcp-steward-architect/templates/mutation-policy.yaml.template",
    "    capability_ref: local:handoff@1\n    durable_operation_required: false",
    "    capability_ref: local:handoff@1\n    capability_contract:\n      source: local\n      id: local:handoff@1\n      revision: \"1\"\n      digest: __LOCAL_HANDOFF_CAPABILITY_DIGEST__\n    durable_operation_required: false",
    "template publication capability contract",
)
replace_once(
    "skills/mcp-steward-architect/templates/mutation-policy.yaml.template",
    "    minimum_budget_ms: 100\n    ambiguity_disposition: block",
    "    minimum_budget_ms: 100\n    finalization_reserve_ms: 100\n    ambiguity_disposition: block",
    "template publication finalization reserve",
)

# Generator: every effect pins the exact reviewed capability contract and an explicit finalization reserve.
gen = "skills/mcp-steward-architect/tools/generate_steward.py"
replace_once(
    gen,
    "def _mutation_policy_document(steward_id: str, capability_id: str) -> dict[str, Any]:\n    return {",
    "def _mutation_policy_document(steward_id: str, capability: dict[str, Any]) -> dict[str, Any]:\n    capability_id = str(capability[\"capability_id\"])\n    capability_contract = dict(capability[\"contract\"])\n    local_identity = {\"source\": \"local\", \"id\": \"local:handoff@1\", \"revision\": \"1\"}\n    local_contract = {**local_identity, \"digest\": _sha256(local_identity)}\n    return {",
    "generator mutation policy signature",
)
replace_once(gen, '                "id": "external-dispatch",\n                "transition": "dispatch-start",', '                "id": "external-dispatch",\n                "operation_kind": "submit",\n                "transition": "dispatch-start",', "generator submit operation kind")
replace_once(gen, '                "capability_ref": capability_id,\n                "durable_operation_required": True,', '                "capability_ref": capability_id,\n                "capability_contract": capability_contract,\n                "durable_operation_required": True,', "generator submit contract")
replace_once(gen, '                "minimum_budget_ms": 1000,\n                "ambiguity_disposition": "reconcile",', '                "minimum_budget_ms": 1000,\n                "finalization_reserve_ms": 500,\n                "ambiguity_disposition": "reconcile",', "generator submit reserve")
replace_once(gen, '                "id": "cancellation-dispatch",\n                "transition": "cancel-start",', '                "id": "cancellation-dispatch",\n                "operation_kind": "cancel",\n                "transition": "cancel-start",', "generator cancel operation kind")
replace_once(gen, '                "capability_ref": capability_id,\n                "durable_operation_required": True,', '                "capability_ref": capability_id,\n                "capability_contract": capability_contract,\n                "durable_operation_required": True,', "generator cancel contract")
replace_once(gen, '                "minimum_budget_ms": 1000,\n                "ambiguity_disposition": "reconcile",', '                "minimum_budget_ms": 1000,\n                "finalization_reserve_ms": 500,\n                "ambiguity_disposition": "reconcile",', "generator cancel reserve")
replace_once(gen, '                "id": "terminal-publication",\n                "transition": "completion-publish",', '                "id": "terminal-publication",\n                "operation_kind": "publication",\n                "transition": "completion-publish",', "generator publication operation kind")
replace_once(gen, '                "capability_ref": "local:handoff@1",\n                "durable_operation_required": False,', '                "capability_ref": "local:handoff@1",\n                "capability_contract": local_contract,\n                "durable_operation_required": False,', "generator publication contract")
replace_once(gen, '                "minimum_budget_ms": 100,\n                "ambiguity_disposition": "block",', '                "minimum_budget_ms": 100,\n                "finalization_reserve_ms": 100,\n                "ambiguity_disposition": "block",', "generator publication reserve")
replace_once(
    gen,
    '        "steward_mutation_policy": _mutation_policy_document(steward_id, upstream["capability_id"]),',
    '        "steward_mutation_policy": _mutation_policy_document(steward_id, upstream),',
    "generator embedded policy exact contract",
)

# Validator: one compositional gate, including subject, full receipt, exact capability contract, cancellation and finalization budget.
validator = "skills/mcp-steward-architect/tools/validate_steward.py"
replace_once(
    validator,
    '        if effect["durable_operation_required"] and not effect["budget_reservation_required"]:\n            findings.append(f"{location} must reserve budget before start")',
    '        if effect["durable_operation_required"] and not effect["budget_reservation_required"]:\n            findings.append(f"{location} must reserve budget before start")\n        if effect["budget_reservation_required"] and int(effect["finalization_reserve_ms"]) <= 0:\n            findings.append(f"{location} must reserve deterministic finalization budget")\n        contract = effect["capability_contract"]\n        identity = {"source": contract["source"], "id": contract["id"], "revision": contract["revision"]}\n        expected = "sha256:" + hashlib.sha256(\n            json.dumps(identity, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")\n        ).hexdigest()\n        if contract["id"] != effect["capability_ref"] or contract["digest"] != expected:\n            findings.append(f"{location} capability contract must exactly bind source/id/revision/digest")',
    "validator mutation policy contract semantics",
)
replace_once(
    validator,
    '            approved = set(criterion["approved_producers"])\n            if approved and selected_evidence["producerId"] not in approved:\n                reasons.append("producer not approved")\n            if (',
    '            approved = set(criterion["approved_producers"])\n            producer_by_id = {str(item["producer_id"]): item for item in proof_recipe["producers"]}\n            selected_producer = producer_by_id.get(str(selected_evidence["producerId"]))\n            if approved and selected_evidence["producerId"] not in approved:\n                reasons.append("producer not approved")\n            if selected_producer is None:\n                reasons.append("producer contract missing")\n            elif _AUTHORITY_RANK.get(selected_evidence["authorityClass"], -1) > _AUTHORITY_RANK[selected_producer["authority_ceiling"]]:\n                reasons.append("authority exceeds producer ceiling")\n            if (',
    "validator persisted evidence authority ceiling",
)
replace_once(
    validator,
    '    current_attempt_id: str,\n    current_version: int,\n    effective_authority: dict[str, Any] | None,\n    remaining_budget_ms: int,\n    receipt: dict[str, Any] | None = None,\n    candidate: dict[str, Any] | None = None,',
    '    current_attempt_id: str,\n    current_version: int,\n    current_subject: dict[str, Any],\n    effective_authority: dict[str, Any] | None,\n    remaining_budget_ms: int,\n    expected_request_digest: str | None = None,\n    receipt: dict[str, Any] | None = None,\n    candidate: dict[str, Any] | None = None,',
    "validator gate signature",
)
replace_once(
    validator,
    '    if job["status"] in _TERMINAL or job["cancellation"] in {"requested", "fenced", "reconciling"}:\n        reasons.append(("LostAuthority", "job is terminal or cancellation-fenced"))',
    '    cancellation_dispatch = effect_id == "cancellation-dispatch"\n    cancellation_fenced = job["cancellation"] in {"requested", "fenced", "reconciling"}\n    if job["status"] in _TERMINAL or (not cancellation_dispatch and cancellation_fenced):\n        reasons.append(("LostAuthority", "job is terminal or cancellation-fenced"))\n    if cancellation_dispatch and job["cancellation"] not in {"requested", "reconciling"}:\n        reasons.append(("LostAuthority", "cancellation dispatch requires an active cancellation request"))\n    if job["subject"] != current_subject:\n        reasons.append(("LostAuthority", "subject identity differs from current authoritative subject"))',
    "validator cancellation and subject gate",
)
replace_once(
    validator,
    '    expected_contract_digest = _capability_contract_digest(capability)\n    contract = capability.get("contract") if isinstance(capability.get("contract"), dict) else {}\n    if capability.get("capability_id") != effect["capability_ref"]:\n        reasons.append(("CapabilityUnavailable", "capability identity does not match mutation policy"))\n    if contract.get("id") != capability.get("capability_id") or expected_contract_digest != contract.get("digest"):\n        reasons.append(("CapabilityUnavailable", "capability contract provenance/digest is invalid"))\n\n    if remaining_budget_ms < int(effect["minimum_budget_ms"]):\n        reasons.append(("BudgetUnavailable", "remaining budget is below mutation minimum"))',
    '    expected_contract_digest = _capability_contract_digest(capability)\n    contract = capability.get("contract") if isinstance(capability.get("contract"), dict) else {}\n    reviewed_contract = effect["capability_contract"]\n    if capability.get("capability_id") != effect["capability_ref"]:\n        reasons.append(("CapabilityUnavailable", "capability identity does not match mutation policy"))\n    if contract.get("id") != capability.get("capability_id") or expected_contract_digest != contract.get("digest"):\n        reasons.append(("CapabilityUnavailable", "capability contract provenance/digest is invalid"))\n    if contract != reviewed_contract:\n        reasons.append(("CapabilityUnavailable", "capability does not match the exact reviewed mutation contract"))\n\n    required_budget_ms = int(effect["minimum_budget_ms"]) + int(effect["finalization_reserve_ms"])\n    if remaining_budget_ms < required_budget_ms:\n        reasons.append(("BudgetUnavailable", "remaining budget cannot cover operation plus deterministic finalization reserve"))',
    "validator exact capability and finalization budget",
)
replace_once(
    validator,
    '            if (\n                receipt.get("jobId") != current_job_id\n                or receipt.get("generation") != current_generation\n                or receipt.get("attemptId") != current_attempt_id\n            ):\n                reasons.append(("LostAuthority", "operation receipt belongs to stale job/generation/attempt"))\n            if receipt.get("targetIdentity") != target_identity:',
    '            if (\n                receipt.get("jobId") != current_job_id\n                or receipt.get("lineageId") != job["lineageId"]\n                or receipt.get("generation") != current_generation\n                or receipt.get("attemptId") != current_attempt_id\n                or int(receipt.get("jobVersion", -1)) != int(current_version)\n            ):\n                reasons.append(("LostAuthority", "operation receipt belongs to stale job/lineage/generation/attempt/version"))\n            if receipt.get("operationKind") != effect["operation_kind"]:\n                reasons.append(("LostAuthority", "operation receipt kind differs from mutation effect"))\n            if expected_request_digest is None or receipt.get("requestDigest") != expected_request_digest:\n                reasons.append(("LostAuthority", "operation receipt request digest differs from exact admitted mutation"))\n            if receipt.get("targetIdentity") != target_identity:',
    "validator exact receipt bindings",
)
replace_once(
    validator,
    '        if effect["durable_operation_required"] and len(upstream_by_id.get(str(effect["capability_ref"]), [])) != 1:\n            findings.append(\n                f"design-pack: mutation effect {effect[\'id\']} capability_ref must resolve to exactly one reviewed upstream contract"\n            )',
    '        if effect["durable_operation_required"] and len(upstream_by_id.get(str(effect["capability_ref"]), [])) != 1:\n            findings.append(\n                f"design-pack: mutation effect {effect[\'id\']} capability_ref must resolve to exactly one reviewed upstream contract"\n            )\n        if effect["durable_operation_required"]:\n            matches = upstream_by_id.get(str(effect["capability_ref"]), [])\n            if len(matches) == 1 and effect["capability_contract"] != matches[0]["contract"]:\n                findings.append(\n                    f"design-pack: mutation effect {effect[\'id\']} capability contract must equal the reviewed upstream source/id/revision/digest"\n                )',
    "validator design pack exact capability",
)

# Python runtime: use the same semantic gate at the atomic reserved->dispatching boundary.
py_runtime = "skills/mcp-steward-architect/tools/steward-templates/python/steward_runtime.py.template"
replace_once(
    py_runtime,
    '_RUNNABLE = {"queued", "reconciling", "waiting-external", "cancelling", "finalizing"}\n',
    '_RUNNABLE = {"queued", "reconciling", "waiting-external", "cancelling", "finalizing"}\n_PLACEHOLDER_AUTHORITY = {"", "unknown", "head", "latest", "default", "unset", "none"}\n',
    "python authority placeholders",
)
replace_once(
    py_runtime,
    'def _target_identity(job: dict[str, Any]) -> str:\n    subject = job["subject"]\n    return f"{subject[\'type\']}:{subject[\'id\']}:{subject.get(\'revision\') or \'none\'}"\n\n\ndef _evaluate_mutation(',
    'def _target_identity(job: dict[str, Any]) -> str:\n    subject = job["subject"]\n    return f"{subject[\'type\']}:{subject[\'id\']}:{subject.get(\'revision\') or \'none\'}"\n\n\ndef _operation_request_digest(job: dict[str, Any], kind: str) -> str:\n    return _digest({"kind": kind, "subject": job["subject"], "candidate": job["candidate"]})\n\n\ndef _evaluate_mutation(',
    "python operation digest helper",
)
replace_once(
    py_runtime,
    '    *, current_job_id: str, current_generation: int, current_attempt_id: str, current_version: int,\n    remaining_budget_ms: int, receipt: dict[str, Any] | None, candidate: dict[str, Any] | None,\n    now: datetime,',
    '    *, current_job_id: str, current_generation: int, current_attempt_id: str, current_version: int,\n    current_subject: dict[str, Any], remaining_budget_ms: int, expected_request_digest: str | None,\n    receipt: dict[str, Any] | None, candidate: dict[str, Any] | None, now: datetime,',
    "python gate signature",
)
replace_once(
    py_runtime,
    '    if cancellation_dispatch and job["cancellation"] not in {"requested", "reconciling"}:\n        reasons.append(("LostAuthority", "cancellation dispatch requires an active cancellation request"))\n    target = _target_identity(job)',
    '    if cancellation_dispatch and job["cancellation"] not in {"requested", "reconciling"}:\n        reasons.append(("LostAuthority", "cancellation dispatch requires an active cancellation request"))\n    if job["subject"] != current_subject:\n        reasons.append(("LostAuthority", "subject identity differs from current authoritative subject"))\n    target = _target_identity(job)',
    "python current subject binding",
)
replace_once(
    py_runtime,
    '    if not authority.get("principal") or authority.get("scope") != effect["id"] or authority.get("target") != target:\n        reasons.append(("LostAuthority", "authority principal/scope/target mismatch"))',
    '    principal = str(authority.get("principal", ""))\n    if principal.casefold() in _PLACEHOLDER_AUTHORITY or authority.get("scope") != effect["id"] or authority.get("target") != target:\n        reasons.append(("LostAuthority", "authority principal/scope/target mismatch"))',
    "python authority principal fail closed",
)
replace_once(
    py_runtime,
    '    contract = capability.get("contract") if isinstance(capability.get("contract"), dict) else {}\n    if capability.get("capability_id") != effect["capability_ref"] or contract.get("id") != capability.get("capability_id"):\n        reasons.append(("CapabilityUnavailable", "capability identity mismatch"))\n    if _capability_digest(capability) != contract.get("digest"):\n        reasons.append(("CapabilityUnavailable", "capability contract provenance/digest mismatch"))\n    if remaining_budget_ms < int(effect["minimum_budget_ms"]):\n        reasons.append(("BudgetUnavailable", "remaining budget below mutation minimum"))',
    '    contract = capability.get("contract") if isinstance(capability.get("contract"), dict) else {}\n    if capability.get("capability_id") != effect["capability_ref"] or contract.get("id") != capability.get("capability_id"):\n        reasons.append(("CapabilityUnavailable", "capability identity mismatch"))\n    if _capability_digest(capability) != contract.get("digest") or contract != effect["capability_contract"]:\n        reasons.append(("CapabilityUnavailable", "capability contract differs from exact reviewed source/id/revision/digest"))\n    required_budget_ms = int(effect["minimum_budget_ms"]) + int(effect["finalization_reserve_ms"])\n    if remaining_budget_ms < required_budget_ms:\n        reasons.append(("BudgetUnavailable", "remaining budget cannot cover operation plus deterministic finalization reserve"))',
    "python exact capability and budget",
)
replace_once(
    py_runtime,
    '            if receipt.get("jobId") != current_job_id or receipt.get("generation") != current_generation or receipt.get("attemptId") != current_attempt_id:\n                reasons.append(("LostAuthority", "receipt stale job/generation/attempt"))\n            if int(receipt.get("jobVersion", -1)) != int(current_version):\n                reasons.append(("LostAuthority", "receipt stale optimistic version"))',
    '            if (receipt.get("jobId") != current_job_id or receipt.get("lineageId") != job["lineageId"]\n                    or receipt.get("generation") != current_generation or receipt.get("attemptId") != current_attempt_id):\n                reasons.append(("LostAuthority", "receipt stale job/lineage/generation/attempt"))\n            if int(receipt.get("jobVersion", -1)) != int(current_version):\n                reasons.append(("LostAuthority", "receipt stale optimistic version"))\n            if receipt.get("operationKind") != effect["operation_kind"]:\n                reasons.append(("LostAuthority", "receipt operation kind mismatch"))\n            if expected_request_digest is None or receipt.get("requestDigest") != expected_request_digest:\n                reasons.append(("LostAuthority", "receipt request digest mismatch"))',
    "python full receipt binding",
)
replace_once(
    py_runtime,
    '              job_id TEXT PRIMARY KEY,lineage_id TEXT,generation INTEGER,attempt_id TEXT,version INTEGER,\n              subject_json TEXT,candidate_json TEXT,request_digest TEXT,status TEXT,stage TEXT,cancellation TEXT,\n              blocked_reason TEXT,created_at TEXT,updated_at TEXT,heartbeat_at TEXT,progress_at TEXT,progress_revision INTEGER,\n              progress_marker TEXT,deadline_at TEXT,finalization_starts_at TEXT);',
    '              job_id TEXT PRIMARY KEY,lineage_id TEXT,generation INTEGER,attempt_id TEXT,version INTEGER,\n              subject_json TEXT,candidate_json TEXT,request_digest TEXT,status TEXT,stage TEXT,cancellation TEXT,\n              blocked_reason TEXT,created_at TEXT,updated_at TEXT,heartbeat_at TEXT,progress_at TEXT,progress_revision INTEGER,\n              progress_marker TEXT,deadline_at TEXT,finalization_starts_at TEXT,lease_owner TEXT,lease_fencing_token INTEGER,lease_expires_at TEXT);',
    "python durable lease columns",
)
replace_once(
    py_runtime,
    '                "INSERT INTO steward_jobs VALUES(?,?,?,?,0,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",\n                (job_id, lineage_id, generation, attempt_id, _canonical(subject), _canonical(candidate), request_digest,\n                 "queued", "admitted", "none", None, now, now, now, now, 1, "admitted", deadline, None),',
    '                "INSERT INTO steward_jobs VALUES(?,?,?,?,0,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",\n                (job_id, lineage_id, generation, attempt_id, _canonical(subject), _canonical(candidate), request_digest,\n                 "queued", "admitted", "none", None, now, now, now, now, 1, "admitted", deadline, None,\n                 f"steward-runtime:{attempt_id}", generation, deadline),',
    "python persist lease",
)
replace_once(
    py_runtime,
    '        lease = None if row["status"] in _TERMINAL else {\n            "owner": f"steward-runtime:{row[\'attempt_id\']}", "fencingToken": row["generation"], "expiresAt": row["deadline_at"]\n        }',
    '        lease = None if row["status"] in _TERMINAL or row["lease_owner"] is None else {\n            "owner": row["lease_owner"], "fencingToken": row["lease_fencing_token"], "expiresAt": row["lease_expires_at"]\n        }',
    "python read durable lease",
)
replace_once(
    py_runtime,
    '        request = {"kind": kind, "subject": job["subject"], "candidate": job["candidate"]}',
    '        request_digest = _operation_request_digest(job, kind)',
    "python reserve request digest helper",
)
replace_once(
    py_runtime,
    '                 capability["capability_id"], capability["contract"]["digest"], target, job["candidate"]["digest"],\n                 _digest(request), "reserved",',
    '                 capability["capability_id"], capability["contract"]["digest"], target, job["candidate"]["digest"],\n                 request_digest, "reserved",',
    "python persist exact request digest",
)
replace_once(
    py_runtime,
    '            "jobId": op["job_id"], "generation": op["generation"], "attemptId": op["attempt_id"],\n            "jobVersion": op["job_version"], "capabilityIdentity": op["capability_identity"],',
    '            "jobId": op["job_id"], "lineageId": op["lineage_id"], "generation": op["generation"],\n            "attemptId": op["attempt_id"], "jobVersion": op["job_version"], "operationKind": op["operation_kind"],\n            "requestDigest": op["request_digest"], "capabilityIdentity": op["capability_identity"],',
    "python receipt view complete identity",
)
replace_once(
    py_runtime,
    '            lineage = db.execute("SELECT * FROM steward_lineages WHERE lineage_id=?", (op["lineage_id"],)).fetchone()',
    '            lineage = db.execute("SELECT * FROM steward_lineages WHERE lineage_id=?", (row["lineage_id"],)).fetchone()',
    "python canonical lineage lookup",
)
replace_once(
    py_runtime,
    '            lease = None if row["status"] in _TERMINAL else {\n                "owner": f"steward-runtime:{row[\'attempt_id\']}", "fencingToken": row["generation"], "expiresAt": row["deadline_at"]\n            }',
    '            lease = None if row["status"] in _TERMINAL or row["lease_owner"] is None else {\n                "owner": row["lease_owner"], "fencingToken": row["lease_fencing_token"], "expiresAt": row["lease_expires_at"]\n            }',
    "python begin dispatch durable lease",
)
replace_once(
    py_runtime,
    '                current_attempt_id=str(row["attempt_id"]), current_version=int(row["version"]),\n                remaining_budget_ms=budget_ms, receipt=self._receipt_view(op), candidate=job["candidate"], now=now,',
    '                current_attempt_id=str(row["attempt_id"]), current_version=int(row["version"]),\n                current_subject=json.loads(lineage["subject_json"]), remaining_budget_ms=budget_ms,\n                expected_request_digest=_operation_request_digest(job, str(op["operation_kind"])),\n                receipt=self._receipt_view(op), candidate=job["candidate"], now=now,',
    "python begin dispatch full gate context",
)
replace_once(
    py_runtime,
    '                    and (not criterion["approved_producers"] or item["producerId"] in criterion["approved_producers"])\n                    and _AUTHORITY_RANK[item["authorityClass"]] >= _AUTHORITY_RANK[criterion["required_authority"]]',
    '                    and (not criterion["approved_producers"] or item["producerId"] in criterion["approved_producers"])\n                    and self._producer(item["producerId"]) is not None\n                    and _AUTHORITY_RANK[item["authorityClass"]] <= _AUTHORITY_RANK[self._producer(item["producerId"])["authority_ceiling"]]\n                    and _AUTHORITY_RANK[item["authorityClass"]] >= _AUTHORITY_RANK[criterion["required_authority"]]',
    "python completion authority ceiling",
)
replace_once(
    py_runtime,
    '            current_job_id=job_id, current_generation=int(job["generation"]), current_attempt_id=str(job["attemptId"]),\n            current_version=int(job["version"]), remaining_budget_ms=budget_ms, receipt=None,\n            candidate=job["candidate"], now=self.store.clock.now(),',
    '            current_job_id=job_id, current_generation=int(job["generation"]), current_attempt_id=str(job["attemptId"]),\n            current_version=int(job["version"]), current_subject=self.store.current_lineage(job["lineageId"])["subject"],\n            remaining_budget_ms=budget_ms, expected_request_digest=None, receipt=None,\n            candidate=job["candidate"], now=self.store.clock.now(),',
    "python publication gate context",
)

# .NET runtime: same gate semantics, including authority, subject, exact contract/request receipt, reserve and producer ceiling.
cs = "skills/mcp-steward-architect/tools/steward-templates/dotnet/StewardSeedRuntime.cs.template"
replace_once(
    cs,
    'internal sealed record SeedMutationEffect(string Id, string AuthoritySource, bool LeaseRequired, bool CandidateRequired, string CapabilityRef, bool DurableOperationRequired, int MinimumBudgetMs);\ninternal sealed record SeedCapability(string Id, string Source, string Revision, string Digest);',
    'internal sealed record SeedCapability(string Id, string Source, string Revision, string Digest);\ninternal sealed record SeedMutationEffect(string Id, string OperationKind, string AuthoritySource, bool LeaseRequired, bool CandidateRequired, string CapabilityRef, SeedCapability CapabilityContract, bool DurableOperationRequired, int MinimumBudgetMs, int FinalizationReserveMs);\ninternal sealed record SeedAuthority(string Source, string Principal, string Scope, string Target, string AttemptId, long JobVersion, string? LeaseOwner, long? LeaseFencingToken);',
    "dotnet mutation records",
)
replace_once(
    cs,
    '            item => new SeedMutationEffect(\n                item.GetProperty("id").GetString()!, item.GetProperty("authority_source").GetString()!,\n                item.GetProperty("lease_required").GetBoolean(), item.GetProperty("candidate_required").GetBoolean(),\n                item.GetProperty("capability_ref").GetString()!, item.GetProperty("durable_operation_required").GetBoolean(),\n                item.GetProperty("minimum_budget_ms").GetInt32()), StringComparer.Ordinal);',
    '            item => {\n                var effectContract = item.GetProperty("capability_contract");\n                var pinned = new SeedCapability(\n                    effectContract.GetProperty("id").GetString()!, effectContract.GetProperty("source").GetString()!,\n                    effectContract.GetProperty("revision").GetString()!, effectContract.GetProperty("digest").GetString()!);\n                if (!string.Equals(CapabilityDigest(pinned.Source, pinned.Id, pinned.Revision), pinned.Digest, StringComparison.Ordinal))\n                    throw new InvalidOperationException("mutation effect capability contract identity/digest is invalid");\n                return new SeedMutationEffect(\n                    item.GetProperty("id").GetString()!, item.GetProperty("operation_kind").GetString()!,\n                    item.GetProperty("authority_source").GetString()!, item.GetProperty("lease_required").GetBoolean(),\n                    item.GetProperty("candidate_required").GetBoolean(), item.GetProperty("capability_ref").GetString()!, pinned,\n                    item.GetProperty("durable_operation_required").GetBoolean(), item.GetProperty("minimum_budget_ms").GetInt32(),\n                    item.GetProperty("finalization_reserve_ms").GetInt32());\n            }, StringComparer.Ordinal);',
    "dotnet parse exact mutation contracts",
)
replace_once(
    cs,
    '            var submit = OperationById(action.Operation.RequestDigest);\n            var handle = _provider.Cancel(action.Operation.OperationId, submit.RemoteHandle ?? throw new InvalidOperationException("submit handle missing"), action.Job.Subject);',
    '            var submit = OperationLocked(action.Job.JobId, "submit") ?? throw new InvalidOperationException("submit operation missing");\n            var handle = _provider.Cancel(action.Operation.OperationId, submit.RemoteHandle ?? throw new InvalidOperationException("submit handle missing"), action.Job.Subject);',
    "dotnet cancellation request digest semantics",
)
replace_once(
    cs,
    '            var submit = OperationById(action.Operation.RequestDigest);\n            var handle = _provider.ReconcileCancel(action.Operation.OperationId, submit.RemoteHandle ?? throw new InvalidOperationException("submit handle missing"), action.Job.Subject);',
    '            var submit = OperationLocked(action.Job.JobId, "submit") ?? throw new InvalidOperationException("submit operation missing");\n            var handle = _provider.ReconcileCancel(action.Operation.OperationId, submit.RemoteHandle ?? throw new InvalidOperationException("submit handle missing"), action.Job.Subject);',
    "dotnet cancellation reconcile request digest semantics",
)
replace_once(
    cs,
    '        var requestDigest = submitOperationId ?? job.RequestDigest;\n        var op = new StewardOperation(',
    '        _ = submitOperationId;\n        var requestDigest = OperationRequestDigest(job, kind);\n        var op = new StewardOperation(',
    "dotnet operation request digest",
)
replace_once(
    cs,
    '        var op = _state.Operations[operationId]; var job = CurrentJobLocked(op.JobId);\n        var decision = EvaluateMutationLocked(effectId, job, op, "steward-runtime");',
    '        var op = _state.Operations[operationId]; var job = CurrentJobLocked(op.JobId);\n        var effect = _policy.Effects.GetValueOrDefault(effectId) ?? throw new InvalidOperationException($"mutation policy has no effect {effectId}");\n        var decision = EvaluateMutationLocked(effectId, job, op, effect.CapabilityContract, AuthorityFor(effectId, job, effect.AuthoritySource));',
    "dotnet dispatch full gate call",
)
start_old = '''    private string EvaluateMutationLocked(string effectId, StewardSeedJob job, StewardOperation? operation, string actualSource)\n    {\n        if (!_policy.Effects.TryGetValue(effectId, out var effect)) return "CapabilityUnavailable";\n        if (!IsCurrentLocked(job)) return "LostAuthority";\n        var cancellationDispatch = effectId == "cancellation-dispatch";\n        var cancellationFenced = job.Cancellation is "requested" or "fenced" or "reconciling";\n        if (Terminal.Contains(job.Status) || (!cancellationDispatch && cancellationFenced)) return "LostAuthority";\n        if (cancellationDispatch && job.Cancellation is not ("requested" or "reconciling")) return "LostAuthority";\n        if (!string.Equals(actualSource, effect.AuthoritySource, StringComparison.Ordinal)) return "LostAuthority";\n        if (effect.LeaseRequired)\n        {\n            var expectedOwner = $"steward-runtime:{job.AttemptId}";\n            if (job.Lease is null || job.Lease.Owner != expectedOwner || job.Lease.FencingToken != job.Generation || job.Lease.ExpiresAt <= _clock.UtcNow)\n                return "LostAuthority";\n        }\n        if (effect.CandidateRequired && string.IsNullOrWhiteSpace(job.Candidate.Digest)) return "StaleCandidate";\n        if (job.DeadlineAt - _clock.UtcNow < TimeSpan.FromMilliseconds(effect.MinimumBudgetMs)) return "BudgetUnavailable";\n        if (effect.DurableOperationRequired)\n        {\n            if (operation is null || operation.State != "reserved" || operation.Delivery != "not-delivered") return "ReconciliationRequired";\n            if (operation.JobId != job.JobId || operation.Generation != job.Generation || operation.AttemptId != job.AttemptId || operation.JobVersion != job.Version)\n                return "LostAuthority";\n            if (operation.CandidateDigest != job.Candidate.Digest) return "StaleCandidate";\n            if (operation.CapabilityIdentity != effect.CapabilityRef || operation.CapabilityIdentity != _policy.Capability.Id\n                || operation.CapabilityContractDigest != _policy.Capability.Digest) return "CapabilityUnavailable";\n            var target = $"target:{job.Subject.Id}:{job.Subject.Revision ?? "none"}";\n            if (operation.TargetIdentity != target) return "LostAuthority";\n        }\n        return "Admitted";\n    }'''
start_new = '''    private SeedAuthority AuthorityFor(string effectId, StewardSeedJob job, string source)\n    {\n        var target = $"target:{job.Subject.Id}:{job.Subject.Revision ?? "none"}";\n        var principal = job.Lease?.Owner ?? $"{source}:{job.AttemptId}";\n        return new(source, principal, effectId, target, job.AttemptId, job.Version, job.Lease?.Owner, job.Lease?.FencingToken);\n    }\n\n    private static string OperationRequestDigest(StewardSeedJob job, string kind) => Digest(new { kind, subject = job.Subject, candidate = job.Candidate });\n\n    private string EvaluateMutationLocked(string effectId, StewardSeedJob job, StewardOperation? operation, SeedCapability actualCapability, SeedAuthority authority)\n    {\n        if (!_policy.Effects.TryGetValue(effectId, out var effect)) return "CapabilityUnavailable";\n        if (!IsCurrentLocked(job)) return "LostAuthority";\n        var lineage = _state.Lineages[job.LineageId];\n        if (lineage.Subject != job.Subject) return "LostAuthority";\n        var cancellationDispatch = effectId == "cancellation-dispatch";\n        var cancellationFenced = job.Cancellation is "requested" or "fenced" or "reconciling";\n        if (Terminal.Contains(job.Status) || (!cancellationDispatch && cancellationFenced)) return "LostAuthority";\n        if (cancellationDispatch && job.Cancellation is not ("requested" or "reconciling")) return "LostAuthority";\n        var target = $"target:{job.Subject.Id}:{job.Subject.Revision ?? "none"}";\n        if (!string.Equals(authority.Source, effect.AuthoritySource, StringComparison.Ordinal)\n            || string.IsNullOrWhiteSpace(authority.Principal) || authority.Principal is "unknown" or "HEAD" or "latest"\n            || authority.Scope != effectId || authority.Target != target || authority.AttemptId != job.AttemptId || authority.JobVersion != job.Version)\n            return "LostAuthority";\n        if (effect.LeaseRequired)\n        {\n            if (job.Lease is null || job.Lease.Owner != authority.Principal || authority.LeaseOwner != job.Lease.Owner\n                || authority.LeaseFencingToken != job.Lease.FencingToken || job.Lease.ExpiresAt <= _clock.UtcNow) return "LostAuthority";\n        }\n        if (effect.CandidateRequired && string.IsNullOrWhiteSpace(job.Candidate.Digest)) return "StaleCandidate";\n        if (actualCapability != effect.CapabilityContract || actualCapability.Id != effect.CapabilityRef) return "CapabilityUnavailable";\n        if (job.DeadlineAt - _clock.UtcNow < TimeSpan.FromMilliseconds(effect.MinimumBudgetMs + effect.FinalizationReserveMs)) return "BudgetUnavailable";\n        if (effect.DurableOperationRequired)\n        {\n            if (operation is null || operation.State != "reserved" || operation.Delivery != "not-delivered") return "ReconciliationRequired";\n            if (operation.OperationKind != effect.OperationKind || operation.JobId != job.JobId || operation.LineageId != job.LineageId\n                || operation.Generation != job.Generation || operation.AttemptId != job.AttemptId || operation.JobVersion != job.Version) return "LostAuthority";\n            if (operation.RequestDigest != OperationRequestDigest(job, operation.OperationKind)) return "LostAuthority";\n            if (operation.CandidateDigest != job.Candidate.Digest) return "StaleCandidate";\n            if (operation.CapabilityIdentity != actualCapability.Id || operation.CapabilityContractDigest != actualCapability.Digest) return "CapabilityUnavailable";\n            if (operation.TargetIdentity != target) return "LostAuthority";\n        }\n        return "Admitted";\n    }'''
replace_once(cs, start_old, start_new, "dotnet full mutation gate")
replace_once(
    cs,
    '        var publicationAdmission = EvaluateMutationLocked("terminal-publication", job, null, "completion-gate");',
    '        var publicationEffect = _policy.Effects["terminal-publication"];\n        var publicationAdmission = EvaluateMutationLocked("terminal-publication", job, null, publicationEffect.CapabilityContract,\n            AuthorityFor("terminal-publication", job, "completion-gate"));',
    "dotnet publication gate",
)
replace_once(
    cs,
    '        if (req.ApprovedProducers.Count > 0 && !req.ApprovedProducers.Contains(ev.ProducerId)) return false;\n        if (AuthorityRank.GetValueOrDefault(ev.AuthorityClass, -1) < AuthorityRank.GetValueOrDefault(req.RequiredAuthority, int.MaxValue)) return false;',
    '        if (req.ApprovedProducers.Count > 0 && !req.ApprovedProducers.Contains(ev.ProducerId)) return false;\n        if (!_policy.Producers.TryGetValue(ev.ProducerId, out var producer)) return false;\n        var evidenceRank = AuthorityRank.GetValueOrDefault(ev.AuthorityClass, -1);\n        if (evidenceRank > AuthorityRank.GetValueOrDefault(producer.AuthorityCeiling, -1)) return false;\n        if (evidenceRank < AuthorityRank.GetValueOrDefault(req.RequiredAuthority, int.MaxValue)) return false;',
    "dotnet persisted evidence ceiling",
)
replace_once(
    cs,
    '    private bool IsCurrentLocked(StewardSeedJob job) => _state.Lineages.TryGetValue(job.LineageId, out var lineage) && lineage.CurrentJobId == job.JobId && lineage.CurrentGeneration == job.Generation && lineage.Candidate == job.Candidate && CurrentJobLocked(job.JobId).AttemptId == job.AttemptId;',
    '    private bool IsCurrentLocked(StewardSeedJob job)\n    {\n        if (!_state.Lineages.TryGetValue(job.LineageId, out var lineage) || lineage.CurrentJobId != job.JobId\n            || lineage.CurrentGeneration != job.Generation || lineage.Subject != job.Subject || lineage.Candidate != job.Candidate) return false;\n        var current = CurrentJobLocked(job.JobId);\n        return current.AttemptId == job.AttemptId && current.Version == job.Version;\n    }',
    "dotnet current subject and version fence",
)
# Remove no-longer-used helper only if present.
replace_once(cs, '    private StewardOperation OperationById(string id) => _state.Operations.TryGetValue(id, out var op) ? op : throw new KeyNotFoundException(id);\n', '', "dotnet obsolete operation id helper")

# Repository tests: make the contract test exercise the full cross-product.
arch = "tests/test_mcp_steward_architect.py"
replace_once(
    arch,
    '        "candidate": candidate,\n        "status": "queued",',
    '        "candidate": candidate,\n        "requestDigest": "sha256:" + "4" * 64,\n        "status": "queued",',
    "test job request digest",
)
replace_once(
    arch,
    '        "attemptId": "a1",\n        "capabilityIdentity": upstream["capability_id"],',
    '        "attemptId": "a1",\n        "jobVersion": 1,\n        "capabilityIdentity": upstream["capability_id"],',
    "test receipt job version",
)
replace_once(
    arch,
    '        current_attempt_id="a1",\n        current_version=1,\n        effective_authority=authority,\n        remaining_budget_ms=5000,',
    '        current_attempt_id="a1",\n        current_version=1,\n        current_subject=job["subject"],\n        effective_authority=authority,\n        remaining_budget_ms=5000,\n        expected_request_digest=receipt["requestDigest"],',
    "test gate full base context",
)
replace_once(
    arch,
    '        ({"current_version": 2}, "LostAuthority"),\n        ({"candidate": {**job["candidate"], "digest": "sha256:" + "9" * 64}}, "StaleCandidate"),\n        ({"remaining_budget_ms": 10}, "BudgetUnavailable"),',
    '        ({"current_version": 2}, "LostAuthority"),\n        ({"current_subject": {**job["subject"], "revision": "def"}}, "LostAuthority"),\n        ({"candidate": {**job["candidate"], "digest": "sha256:" + "9" * 64}}, "StaleCandidate"),\n        ({"receipt": {**receipt, "jobId": "foreign-job"}}, "LostAuthority"),\n        ({"receipt": {**receipt, "lineageId": "foreign-lineage"}}, "LostAuthority"),\n        ({"receipt": {**receipt, "generation": 1}}, "LostAuthority"),\n        ({"receipt": {**receipt, "attemptId": "foreign-attempt"}}, "LostAuthority"),\n        ({"receipt": {**receipt, "jobVersion": 0}}, "LostAuthority"),\n        ({"receipt": {**receipt, "operationKind": "cancel"}}, "LostAuthority"),\n        ({"receipt": {**receipt, "requestDigest": "sha256:" + "8" * 64}}, "LostAuthority"),\n        ({"receipt": {**receipt, "candidateDigest": "sha256:" + "7" * 64}}, "StaleCandidate"),\n        ({"remaining_budget_ms": 1499}, "BudgetUnavailable"),',
    "test gate cross product",
)
replace_once(
    arch,
    '    assert (\n        validator.evaluate_mutation_admission(**{**base, "capability": drift})["disposition"] == "CapabilityUnavailable"\n    )',
    '    assert (\n        validator.evaluate_mutation_admission(**{**base, "capability": drift})["disposition"] == "CapabilityUnavailable"\n    )\n\n    cancel_effect = next(item for item in docs["steward_mutation_policy"]["effects"] if item["id"] == "cancellation-dispatch")\n    cancel_job = {**job, "cancellation": "requested"}\n    cancel_authority = {**authority, "scope": "cancellation-dispatch"}\n    cancel_receipt = {**receipt, "operationKind": "cancel"}\n    cancel_request_digest = "sha256:" + "6" * 64\n    cancel_receipt["requestDigest"] = cancel_request_digest\n    assert cancel_effect["operation_kind"] == "cancel"\n    assert validator.evaluate_mutation_admission(\n        effect_id="cancellation-dispatch", mutation_policy=docs["steward_mutation_policy"], job=cancel_job,\n        capability=docs["steward_upstream_capability"], current_job_id="j1", current_generation=2,\n        current_attempt_id="a1", current_version=1, current_subject=job["subject"], effective_authority=cancel_authority,\n        remaining_budget_ms=5000, expected_request_digest=cancel_request_digest, receipt=cancel_receipt,\n        candidate=job["candidate"], now=datetime(2026, 9, 12, tzinfo=UTC),\n    )["disposition"] == "Admitted"',
    "test cancellation admission special case",
)
replace_once(
    arch,
    '    mutation["effects"][0]["capability_ref"] = "missing:capability"',
    '    mutation["effects"][0]["capability_ref"] = "missing:capability"\n    mutation["effects"][0]["capability_contract"]["id"] = "missing:capability"',
    "test unresolved capability contract id",
)
# Add an exact contract drift assertion to design pack test.
replace_once(
    arch,
    '    assert any("capability_ref must resolve" in item for item in findings)\n\n    profile = json.loads(json.dumps(docs["steward_profile"]))',
    '    assert any("capability_ref must resolve" in item for item in findings)\n\n    contract_drift = json.loads(json.dumps(docs["steward_mutation_policy"]))\n    contract_drift["effects"][0]["capability_contract"]["revision"] = "2"\n    findings = validator.validate_design_pack(\n        profile=docs["steward_profile"], state_machine=docs["steward_state_machine"], mutation_policy=contract_drift,\n        proof_recipe=docs["steward_proof_recipe"], acceptance=docs["steward_acceptance"],\n        upstreams=[docs["steward_upstream_capability"]],\n    )\n    assert any("capability contract" in item for item in findings)\n\n    profile = json.loads(json.dumps(docs["steward_profile"]))',
    "test exact capability design drift",
)

# Runtime security regressions: actual generated Python enforcement point, zero provider calls.
sec = "tests/test_mcp_steward_runtime_security.py"
append_sec = r'''


def test_real_dispatch_gate_rejects_full_receipt_subject_lease_request_and_budget_cross_product(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)

    class CountingProvider(runtime.FakeProvider):
        def __init__(self) -> None:
            self.dispatch_count = 0

        def dispatch(self, operation_id: str, subject: dict[str, Any]) -> str:
            self.dispatch_count += 1
            return super().dispatch(operation_id, subject)

    cases = {
        "foreign-lineage": ("UPDATE external_operations SET lineage_id='foreign' WHERE job_id=?", ()),
        "foreign-generation": ("UPDATE external_operations SET generation=generation+1 WHERE job_id=?", ()),
        "foreign-attempt": ("UPDATE external_operations SET attempt_id='foreign' WHERE job_id=?", ()),
        "stale-job-version": ("UPDATE external_operations SET job_version=job_version-1 WHERE job_id=?", ()),
        "wrong-target": ("UPDATE external_operations SET target_identity='target:other:abc' WHERE job_id=?", ()),
        "wrong-candidate": ("UPDATE external_operations SET candidate_digest=? WHERE job_id=?", ("sha256:" + "7" * 64,)),
        "wrong-request": ("UPDATE external_operations SET request_digest=? WHERE job_id=?", ("sha256:" + "8" * 64,)),
        "wrong-kind": ("UPDATE external_operations SET operation_kind='cancel' WHERE job_id=?", ()),
        "wrong-lease-owner": ("UPDATE steward_jobs SET lease_owner='foreign-owner' WHERE job_id=?", ()),
        "wrong-lease-fence": ("UPDATE steward_jobs SET lease_fencing_token=lease_fencing_token+1 WHERE job_id=?", ()),
        "wrong-subject": ("UPDATE steward_lineages SET subject_json=? WHERE current_job_id=?", (json.dumps({"type": "target", "id": "repo", "revision": "other"}, sort_keys=True, separators=(",", ":")),)),
    }
    for name, (sql, prefix) in cases.items():
        clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
        provider = CountingProvider()
        store = runtime.StewardStore(tmp_path / f"{name}.db", clock)
        steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream, provider=provider)
        job_id = steward.submit("repo", "abc", f"idem-{name}")["jobId"]
        assert steward.run_once() is True
        with store._write() as db:
            db.execute(sql, (*prefix, job_id))
        assert steward.run_once() is True
        assert provider.dispatch_count == 0, name
        assert steward.status(job_id)["status"] == "blocked", name

    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    provider = CountingProvider()
    store = runtime.StewardStore(tmp_path / "budget-reserve.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream, provider=provider)
    job_id = steward.submit("repo", "abc", "idem-budget-reserve")["jobId"]
    assert steward.run_once() is True
    deadline = runtime._parse(steward.status(job_id)["deadlineAt"])
    clock.advance((deadline - clock.now()).total_seconds() - 1.499)
    assert steward.run_once() is True
    assert provider.dispatch_count == 0
    assert steward.status(job_id)["blockedReason"] == "mutation-admission:BudgetUnavailable"


def test_dispatch_commit_closes_toctou_and_stale_generation_reconciles_without_redispatch(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)

    class CountingProvider(runtime.FakeProvider):
        def __init__(self) -> None:
            self.dispatch_count = 0
            self.reconcile_count = 0

        def dispatch(self, operation_id: str, subject: dict[str, Any]) -> str:
            self.dispatch_count += 1
            return super().dispatch(operation_id, subject)

        def reconcile(self, operation_id: str, subject: dict[str, Any]) -> str:
            self.reconcile_count += 1
            return super().reconcile(operation_id, subject)

    provider = CountingProvider()
    steward = runtime.StewardRuntime(
        runtime.StewardStore(tmp_path / "toctou.db", runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))),
        profile, proof, mutation, upstream=upstream, provider=provider,
        faults=runtime.FaultInjector({"after-dispatch-start"}),
    )
    old_job = steward.submit("repo", "abc", "toctou-old")["jobId"]
    steward.run_once()
    steward.run_once()
    old_op = steward.get(old_job)["operations"][0]
    assert old_op["delivery"] == "delivery-unknown"
    assert old_op["mutation_decision_ref"]
    assert provider.dispatch_count == 0
    steward.submit("repo", "abc", "toctou-new")
    assert steward.run_once() is True
    assert provider.dispatch_count == 0
    assert provider.reconcile_count == 1


def test_completion_rejects_persisted_authority_above_producer_ceiling(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))
    store = runtime.StewardStore(tmp_path / "authority-ceiling.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream)
    job_id = steward.submit("repo", "abc", "authority-ceiling")["jobId"]
    for _ in range(8):
        steward.run_once()
        if steward.status(job_id)["status"] == "finalizing":
            break
    evidence_id = steward.get(job_id)["evidence"][0]["evidenceId"]
    with store._write() as db:
        db.execute("UPDATE steward_evidence SET authority_class='independent' WHERE evidence_id=?", (evidence_id,))
    evaluation = steward.completion_gate(job_id)
    assert evaluation["disposition"] == "blocked"
    assert evaluation["obligations"][0]["state"] == "unsatisfied"
'''
sec_path = ROOT / sec
sec_text = sec_path.read_text(encoding="utf-8")
if "test_real_dispatch_gate_rejects_full_receipt_subject_lease_request_and_budget_cross_product" in sec_text:
    raise RuntimeError("runtime security regressions already present unexpectedly")
sec_path.write_text(sec_text.rstrip() + append_sec + "\n", encoding="utf-8", newline="\n")

# Generated Python seed also carries a focused self-regression for reserve semantics.
py_test = "skills/mcp-steward-architect/tools/steward-templates/python/test_steward_runtime.py.template"
append_py_test = r'''


def test_dispatch_budget_includes_deterministic_finalization_reserve(tmp_path: Path) -> None:
    provider = CountingProvider()
    profile, proof, mutation, upstream = _docs()
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    store = StewardStore(tmp_path / "budget-reserve.db", clock)
    runtime = StewardRuntime(store, profile, proof, mutation, upstream=upstream, provider=provider)
    job_id = runtime.submit("repo", "abc", "idem-budget-reserve")["jobId"]
    runtime.run_once()
    deadline = datetime.fromisoformat(runtime.status(job_id)["deadlineAt"].replace("Z", "+00:00"))
    clock.advance((deadline - clock.now()).total_seconds() - 1.499)
    runtime.run_once()
    assert provider.dispatch_count == 0
    assert runtime.status(job_id)["blockedReason"] == "mutation-admission:BudgetUnavailable"
'''
py_test_path = ROOT / py_test
py_test_text = py_test_path.read_text(encoding="utf-8")
if "test_dispatch_budget_includes_deterministic_finalization_reserve" in py_test_text:
    raise RuntimeError("generated Python budget regression already present unexpectedly")
py_test_path.write_text(py_test_text.rstrip() + append_py_test + "\n", encoding="utf-8", newline="\n")

# Exact .NET artifact smoke: persisted lease/request tamper must stop before provider dispatch.
smoke = "skills/mcp-steward-architect/tools/steward-templates/dotnet/SmokeProgram.cs.template"
replace_once(
    smoke,
    '        var blockedProvider = new UnapprovedSeedProvider();',
    '''        VerifyMutationRejection("wrong-request", profile, proof, clock, static root =>\n        {\n            var operations = root["Operations"]!.AsObject();\n            var operation = operations.First().Value!.AsObject();\n            operation["RequestDigest"] = "sha256:" + new string('8', 64);\n        });\n        VerifyMutationRejection("wrong-lease-fence", profile, proof, clock, static root =>\n        {\n            var jobs = root["Jobs"]!.AsObject();\n            var job = jobs.First().Value!.AsObject();\n            job["Lease"]!["FencingToken"] = 999;\n        });\n        VerifyMutationRejection("wrong-subject", profile, proof, clock, static root =>\n        {\n            var lineages = root["Lineages"]!.AsObject();\n            var lineage = lineages.First().Value!.AsObject();\n            lineage["Subject"]!["Revision"] = "other";\n        });\n\n        var blockedProvider = new UnapprovedSeedProvider();''',
    "dotnet smoke mutation rejection calls",
)
replace_once(
    smoke,
    'using System.Text.Json;\nusing __NAMESPACE__.Mcp.Server;',
    'using System.Text.Json;\nusing System.Text.Json.Nodes;\nusing __NAMESPACE__.Mcp.Server;',
    "dotnet smoke json nodes import",
)
insert_before = 'static async Task RunStdioAsync(string dll)\n'
helper = '''static void VerifyMutationRejection(string name, string profile, string proof, FakeSeedClock clock, Action<JsonObject> tamper)\n{\n    var root = Path.Combine(Path.GetTempPath(), "__NAMESPACE__.gate-" + name + "-" + Guid.NewGuid().ToString("N"));\n    Directory.CreateDirectory(root);\n    try\n    {\n        using (var reserve = new StewardSeedRuntime(root, clock, new FakeSeedProvider(), new SeedFaultInjector(), profile, proof))\n        {\n            reserve.Submit("repo", "abc", "idem-" + name);\n            reserve.RunOneDue();\n        }\n        var snapshot = Path.Combine(root, "steward-state.json");\n        var json = JsonNode.Parse(File.ReadAllText(snapshot))!.AsObject();\n        tamper(json);\n        File.WriteAllText(snapshot, json.ToJsonString());\n        var provider = new CountingSeedProvider();\n        using var runtime = new StewardSeedRuntime(root, clock, provider, new SeedFaultInjector(), profile, proof);\n        runtime.RunOneDue();\n        if (provider.DispatchCount != 0) throw new InvalidOperationException($"{name}: rejected mutation reached provider dispatch.");\n        if (runtime.Doctor().Audit.All(item => item.EventType != "mutation-admission-rejected"))\n            throw new InvalidOperationException($"{name}: rejected mutation did not emit durable admission rejection.");\n    }\n    finally { Directory.Delete(root, recursive: true); }\n}\n\n'''
replace_once(smoke, insert_before, helper + insert_before, "dotnet smoke mutation rejection helper")

# Evidence plan includes the new enforcement regressions.
evidence = "contracts/evidence-claim-plan.yaml"
replace_once(
    evidence,
    "    - '*test_mcp_steward_runtime_security::test_real_dispatch_gate_rejects_capability_drift_and_stale_fence_with_zero_provider_calls'\n    result_files:",
    "    - '*test_mcp_steward_runtime_security::test_real_dispatch_gate_rejects_capability_drift_and_stale_fence_with_zero_provider_calls'\n    - '*test_mcp_steward_runtime_security::test_real_dispatch_gate_rejects_full_receipt_subject_lease_request_and_budget_cross_product'\n    - '*test_mcp_steward_runtime_security::test_dispatch_commit_closes_toctou_and_stale_generation_reconciles_without_redispatch'\n    result_files:",
    "mutation evidence selectors",
)
replace_once(
    evidence,
    "    - '*test_mcp_steward_runtime_security::test_evidence_promotion_uses_observed_binding_coverage_and_authority_without_minting'\n    result_files:",
    "    - '*test_mcp_steward_runtime_security::test_evidence_promotion_uses_observed_binding_coverage_and_authority_without_minting'\n    - '*test_mcp_steward_runtime_security::test_completion_rejects_persisted_authority_above_producer_ceiling'\n    result_files:",
    "claim evidence authority ceiling selector",
)

selector_test = "tests/test_mcp_steward_evidence_selectors.py"
selector_path = ROOT / selector_test
selector_text = selector_path.read_text(encoding="utf-8")
append_selector = r'''


def test_steward_mutation_and_claim_rules_bind_cross_product_runtime_regressions() -> None:
    document = yaml.safe_load(PLAN.read_text(encoding="utf-8"))
    claims = {claim["subject"]: claim for claim in document["profiles"]["repository-rules"]}
    required = {
        "steward.mutation.admitted": {
            "test_real_dispatch_gate_rejects_full_receipt_subject_lease_request_and_budget_cross_product",
            "test_dispatch_commit_closes_toctou_and_stale_generation_reconciles_without_redispatch",
        },
        "steward.claim.bound": {
            "test_completion_rejects_persisted_authority_above_producer_ceiling",
        },
    }
    for subject, names in required.items():
        selectors = claims[subject]["selectors"]
        for name in names:
            identity = f"tests.test_mcp_steward_runtime_security::{name}"
            assert any(fnmatchcase(identity, selector) for selector in selectors), (subject, name)
'''
if "test_steward_mutation_and_claim_rules_bind_cross_product_runtime_regressions" in selector_text:
    raise RuntimeError("selector cross-product regression already present unexpectedly")
selector_path.write_text(selector_text.rstrip() + append_selector + "\n", encoding="utf-8", newline="\n")

print("Steward final compositional gate hardening patch applied")
