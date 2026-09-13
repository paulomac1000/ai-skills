from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8", newline="\n")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def replace_regex(text: str, pattern: str, new: str, label: str) -> str:
    updated, count = re.subn(pattern, lambda _: new, text, count=1, flags=re.MULTILINE | re.DOTALL)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return updated


# ---------------------------------------------------------------------------
# Contract: proof producers declare an authority ceiling.
# ---------------------------------------------------------------------------
path = "contracts/steward-proof-recipe.schema.json"
text = read(path)
text = replace_once(
    text,
    '"required": ["producer_id", "trust_class", "observation_kind", "subject_dimensions", "claim_classes", "binding_requirements", "independence"]',
    '"required": ["producer_id", "trust_class", "observation_kind", "subject_dimensions", "claim_classes", "binding_requirements", "authority_ceiling", "independence"]',
    "proof schema required producer fields",
)
text = replace_once(
    text,
    '"binding_requirements": {"$ref": "#/$defs/stringSet"}, "independence":',
    '"binding_requirements": {"$ref": "#/$defs/stringSet"}, "authority_ceiling": {"enum": ["advisory", "observed", "verified", "independent"]}, "independence":',
    "proof schema authority ceiling",
)
write(path, text)

path = "skills/mcp-steward-architect/templates/proof-recipe.yaml.template"
text = read(path)
text = replace_once(
    text,
    "    binding_requirements: [target]\n    independence: external",
    "    binding_requirements: [target]\n    authority_ceiling: observed\n    independence: external",
    "proof template authority ceiling",
)
write(path, text)

# The reference mutation-policy template should demonstrate real lease fencing.
path = "skills/mcp-steward-architect/templates/mutation-policy.yaml.template"
text = read(path)
if text.count("    lease_required: false") < 3:
    raise RuntimeError("mutation policy template: expected three lease flags")
text = text.replace("    lease_required: false", "    lease_required: true", 2)
write(path, text)

# ---------------------------------------------------------------------------
# Validator hardening.
# ---------------------------------------------------------------------------
path = "skills/mcp-steward-architect/tools/validate_steward.py"
text = read(path)
text = replace_once(
    text,
    "    for field in _TIMESTAMP_FIELDS.get(kind, ()):\n        timestamp = value.get(field)\n        if timestamp is None:\n            continue\n        try:\n            _parse_timestamp(str(timestamp))\n        except ValueError as exc:\n            findings.append(f\"schema:{field}: {exc}\")\n    return findings",
    "    for field in _TIMESTAMP_FIELDS.get(kind, ()):\n        timestamp = value.get(field)\n        if timestamp is None:\n            continue\n        try:\n            _parse_timestamp(str(timestamp))\n        except ValueError as exc:\n            findings.append(f\"schema:{field}: {exc}\")\n    if kind == \"job\" and isinstance(value.get(\"lease\"), dict):\n        try:\n            _parse_timestamp(str(value[\"lease\"].get(\"expiresAt\", \"\")))\n        except ValueError as exc:\n            findings.append(f\"schema:lease.expiresAt: {exc}\")\n    return findings",
    "nested lease timestamp validation",
)

text = replace_once(
    text,
    "def _upstream_findings(value: dict[str, Any]) -> list[str]:\n    findings: list[str] = []\n    if value[\"contract\"][\"id\"].casefold() in _PLACEHOLDER_AUTHORITY:",
    "def _upstream_findings(value: dict[str, Any]) -> list[str]:\n    findings: list[str] = []\n    contract = value[\"contract\"]\n    identity = {\"source\": contract[\"source\"], \"id\": contract[\"id\"], \"revision\": contract[\"revision\"]}\n    expected_digest = \"sha256:\" + hashlib.sha256(\n        json.dumps(identity, ensure_ascii=False, separators=(\",\", \":\"), sort_keys=True).encode(\"utf-8\")\n    ).hexdigest()\n    if contract[\"digest\"] != expected_digest:\n        findings.append(\"upstream: capability contract digest does not bind source/id/revision\")\n    if contract[\"id\"] != value[\"capability_id\"]:\n        findings.append(\"upstream: capability contract id must equal capability_id\")\n    if value[\"contract\"][\"id\"].casefold() in _PLACEHOLDER_AUTHORITY:",
    "upstream exact contract digest",
)

proof_function = '''def _proof_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    producers = {item["producer_id"]: item for item in value["producers"]}
    if len(producers) != len(value["producers"]):
        findings.append("proof: duplicate producer ids")
    criteria = {item["criterion_id"]: item for item in value["criteria"]}
    if len(criteria) != len(value["criteria"]):
        findings.append("proof: duplicate criterion ids")
    for criterion in value["criteria"]:
        location = f"proof: criterion {criterion['criterion_id']}"
        approved = criterion["approved_producers"]
        missing = sorted(set(approved) - set(producers))
        if missing:
            findings.append(f"{location} references unknown producers: {', '.join(missing)}")
            continue
        for producer_id in approved:
            producer = producers[producer_id]
            if criterion["canonical_claim"] not in producer["claim_classes"]:
                findings.append(f"{location} producer {producer_id} cannot produce canonical claim")
            if not set(criterion["subject_dimensions"]) <= set(producer["subject_dimensions"]):
                findings.append(f"{location} producer {producer_id} cannot observe required subject dimensions")
            if not set(criterion["binding_requirements"]) <= set(producer["binding_requirements"]):
                findings.append(f"{location} producer {producer_id} cannot satisfy binding requirements")
            if _AUTHORITY_RANK[producer["authority_ceiling"]] < _AUTHORITY_RANK[criterion["required_authority"]]:
                findings.append(f"{location} producer {producer_id} authority ceiling is below criterion requirement")
        if criterion["required_authority"] == "independent" and not any(
            producers[item]["independence"] == "independent" for item in approved
        ):
            findings.append(f"{location} requires independent authority but has no independent producer")
    return findings

'''
text = replace_regex(
    text,
    r"def _proof_findings\(value: dict\[str, Any\]\) -> list\[str\]:\n.*?(?=def _acceptance_findings)",
    proof_function,
    "proof cross-contract producer enforcement",
)

admission_and_pack = '''def _capability_contract_digest(capability: dict[str, Any]) -> str | None:
    contract = capability.get("contract")
    if not isinstance(contract, dict):
        return None
    try:
        identity = {"source": contract["source"], "id": contract["id"], "revision": contract["revision"]}
    except KeyError:
        return None
    return "sha256:" + hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _target_identity(job: dict[str, Any]) -> str:
    subject = job["subject"]
    return f"{subject['type']}:{subject['id']}:{subject.get('revision') or 'none'}"


def evaluate_mutation_admission(
    *,
    effect_id: str,
    mutation_policy: dict[str, Any],
    job: dict[str, Any],
    capability: dict[str, Any],
    current_job_id: str,
    current_generation: int,
    current_attempt_id: str,
    current_version: int,
    effective_authority: dict[str, Any] | None,
    remaining_budget_ms: int,
    receipt: dict[str, Any] | None = None,
    candidate: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    effects = {item["id"]: item for item in mutation_policy.get("effects", [])}
    effect = effects.get(effect_id)
    if effect is None:
        return {"disposition": "CapabilityUnavailable", "reasons": ["unknown mutation effect"]}
    reasons: list[tuple[str, str]] = []
    if job["jobId"] != current_job_id or job["generation"] != current_generation:
        reasons.append(("LostAuthority", "stale job/generation"))
    if job["attemptId"] != current_attempt_id:
        reasons.append(("LostAuthority", "stale attempt"))
    if int(job["version"]) != int(current_version):
        reasons.append(("LostAuthority", "stale optimistic version"))
    if job["status"] in _TERMINAL or job["cancellation"] in {"requested", "fenced", "reconciling"}:
        reasons.append(("LostAuthority", "job is terminal or cancellation-fenced"))

    target_identity = _target_identity(job)
    authority = effective_authority or {}
    source = str(authority.get("source", ""))
    principal = str(authority.get("principal", ""))
    if source != effect["authority_source"]:
        reasons.append(("LostAuthority", "effective authority source does not match mutation policy"))
    if principal.casefold() in _PLACEHOLDER_AUTHORITY:
        reasons.append(("LostAuthority", "effective authority principal is missing/fabricated"))
    if authority.get("scope") != effect_id:
        reasons.append(("LostAuthority", "effective authority scope does not match mutation effect"))
    if authority.get("target") != target_identity:
        reasons.append(("LostAuthority", "effective authority target does not match current subject"))
    if authority.get("attemptId") != current_attempt_id or int(authority.get("jobVersion", -1)) != int(current_version):
        reasons.append(("LostAuthority", "effective authority is fenced to a stale attempt/version"))

    selected_now = (now or datetime.now(UTC)).astimezone(UTC)
    if effect["lease_required"]:
        lease = job.get("lease")
        if not isinstance(lease, dict):
            reasons.append(("LostAuthority", "required lease is missing"))
        else:
            try:
                if _parse_timestamp(str(lease["expiresAt"])) <= selected_now:
                    reasons.append(("LostAuthority", "required lease is expired"))
            except (KeyError, ValueError):
                reasons.append(("LostAuthority", "required lease expiry is invalid"))
            if lease.get("owner") != principal or authority.get("leaseOwner") != lease.get("owner"):
                reasons.append(("LostAuthority", "lease owner does not match effective authority"))
            if authority.get("leaseFencingToken") != lease.get("fencingToken"):
                reasons.append(("LostAuthority", "lease fencing token is stale"))

    if effect["candidate_required"]:
        if candidate is None or not candidate.get("digest"):
            reasons.append(("StaleCandidate", "exact candidate is required"))
        elif job.get("candidate") != candidate:
            reasons.append(("StaleCandidate", "candidate differs from admitted job candidate"))

    expected_contract_digest = _capability_contract_digest(capability)
    contract = capability.get("contract") if isinstance(capability.get("contract"), dict) else {}
    if capability.get("capability_id") != effect["capability_ref"]:
        reasons.append(("CapabilityUnavailable", "capability identity does not match mutation policy"))
    if contract.get("id") != capability.get("capability_id") or expected_contract_digest != contract.get("digest"):
        reasons.append(("CapabilityUnavailable", "capability contract provenance/digest is invalid"))

    if remaining_budget_ms < int(effect["minimum_budget_ms"]):
        reasons.append(("BudgetUnavailable", "remaining budget is below mutation minimum"))
    if effect["durable_operation_required"]:
        if receipt is None:
            reasons.append(("ReconciliationRequired", "durable operation receipt is missing"))
        else:
            if receipt.get("jobId") != current_job_id or receipt.get("generation") != current_generation or receipt.get("attemptId") != current_attempt_id:
                reasons.append(("LostAuthority", "operation receipt belongs to stale job/generation/attempt"))
            if receipt.get("targetIdentity") != target_identity:
                reasons.append(("LostAuthority", "operation receipt target differs from current subject"))
            if receipt.get("capabilityIdentity") != capability.get("capability_id") or receipt.get("capabilityContractDigest") != contract.get("digest"):
                reasons.append(("CapabilityUnavailable", "operation receipt is not bound to current reviewed capability contract"))
            if candidate is not None and receipt.get("candidateDigest") != candidate.get("digest"):
                reasons.append(("StaleCandidate", "operation receipt candidate digest is stale"))
            if receipt.get("delivery") == "delivery-unknown":
                reasons.append(("ReconciliationRequired", "operation delivery is ambiguous"))
            elif receipt.get("state") != "reserved" or receipt.get("delivery") != "not-delivered":
                reasons.append(("ReconciliationRequired", "operation is not in pre-dispatch reserved state"))
    if reasons:
        return {"disposition": reasons[0][0], "reasons": [item[1] for item in reasons]}
    return {"disposition": "Admitted", "reasons": []}


def validate_design_pack(
    *,
    profile: dict[str, Any],
    state_machine: dict[str, Any],
    mutation_policy: dict[str, Any],
    proof_recipe: dict[str, Any],
    acceptance: dict[str, Any],
    upstreams: list[dict[str, Any]],
) -> list[str]:
    findings: list[str] = []
    for kind, value in (
        ("profile", profile),
        ("state-machine", state_machine),
        ("mutation-policy", mutation_policy),
        ("proof", proof_recipe),
        ("acceptance", acceptance),
    ):
        findings.extend(f"{kind}: {item}" for item in validate_document(kind, value))
    for index, upstream in enumerate(upstreams):
        findings.extend(f"upstream[{index}]: {item}" for item in validate_document("upstream", upstream))
    if findings:
        return findings

    expected_refs = {
        "state_machine": f"{state_machine['machine_id']}@{state_machine['revision']}",
        "mutation_policy": f"{mutation_policy['policy_id']}@{mutation_policy['revision']}",
        "proof_recipe": f"{proof_recipe['recipe_id']}@{proof_recipe['revision']}",
        "acceptance": f"{acceptance['acceptance_id']}@{acceptance['revision']}",
    }
    for key, expected in expected_refs.items():
        if profile["contracts"].get(key) != expected:
            findings.append(f"design-pack: profile contract {key} must reference {expected}")

    transition_ids = {item["id"] for item in state_machine["transitions"]}
    upstream_by_id: dict[str, list[dict[str, Any]]] = {}
    for upstream in upstreams:
        upstream_by_id.setdefault(str(upstream["capability_id"]), []).append(upstream)
    for capability_id, matches in upstream_by_id.items():
        if len(matches) != 1:
            findings.append(f"design-pack: capability {capability_id} must resolve to exactly one reviewed upstream contract")
    for effect in mutation_policy["effects"]:
        if effect["transition"] not in transition_ids and effect["transition"] not in {"cancel-start"}:
            findings.append(
                f"design-pack: mutation effect {effect['id']} references unknown transition {effect['transition']}"
            )
        if effect["durable_operation_required"] and len(upstream_by_id.get(str(effect["capability_ref"]), [])) != 1:
            findings.append(
                f"design-pack: mutation effect {effect['id']} capability_ref must resolve to exactly one reviewed upstream contract"
            )

    criteria = {item["criterion_id"] for item in proof_recipe["criteria"]}
    for obligation in profile["completion"]["obligations"]:
        if obligation["id"] not in criteria:
            findings.append(f"design-pack: completion obligation {obligation['id']} has no proof criterion")
    features = profile["features"]
    if features["durable_external_async"] and not any(item["delivery"] == "durable-async" for item in upstreams):
        findings.append("design-pack: durable_external_async has no durable-async upstream contract")
    if features["external_cancellation"] and not any(item["cancellation"]["mode"] != "none" for item in upstreams):
        findings.append("design-pack: external_cancellation has no cancellable upstream contract")
    if features["exact_candidate_binding"]:
        if not any(item["candidate_required"] for item in mutation_policy["effects"]):
            findings.append("design-pack: exact_candidate_binding has no candidate-required mutation")
        if not any(item["candidate_binding_required"] for item in proof_recipe["criteria"]):
            findings.append("design-pack: exact_candidate_binding has no candidate-bound proof criterion")
    return findings


'''
text = replace_regex(
    text,
    r"def evaluate_mutation_admission\(\n.*?(?=def validate_path)",
    admission_and_pack,
    "mutation admission and design pack",
)
write(path, text)

# ---------------------------------------------------------------------------
# Generator: authority ceilings, lease-required stateful mutations, and inherited
# canonical no-symlink confinement.
# ---------------------------------------------------------------------------
path = "skills/mcp-steward-architect/tools/generate_steward.py"
text = read(path)
text = replace_once(
    text,
    '                "binding_requirements": ["target", "candidate"],\n                "independence": "external",',
    '                "binding_requirements": ["target", "candidate"],\n                "authority_ceiling": "observed",\n                "independence": "external",',
    "generated producer authority ceiling",
)
# Only the two external stateful effects; terminal publication remains lease-free.
needle = '                "lease_required": False,'
if text.count(needle) < 3:
    raise RuntimeError("generated mutation policy: expected three lease flags")
text = text.replace(needle, '                "lease_required": True,', 2)

text = replace_once(
    text,
    "def generate_project(\n    destination: Path, *, language: str, identity: str, server_name: str, steward_id: str, profile: str\n) -> list[Path]:\n    files = steward_files(language, identity, server_name, steward_id, profile)\n    expanded = destination.expanduser()\n    if os.path.lexists(expanded):\n        raise FileExistsError(expanded)\n    parent = expanded.parent.resolve(strict=False)\n    parent.mkdir(parents=True, exist_ok=True)\n    destination = parent / expanded.name",
    "def _reject_symlink_components(path: Path) -> None:\n    canonical = _base_generator(\"python\")\n    guard = getattr(canonical, \"_reject_symlink_components\", None)\n    if not callable(guard):\n        raise RuntimeError(\"canonical MCP generator symlink-confinement primitive is unavailable\")\n    guard(path)\n\n\ndef generate_project(\n    destination: Path, *, language: str, identity: str, server_name: str, steward_id: str, profile: str\n) -> list[Path]:\n    files = steward_files(language, identity, server_name, steward_id, profile)\n    expanded = destination.expanduser()\n    if os.path.lexists(expanded):\n        raise FileExistsError(expanded)\n    _reject_symlink_components(expanded)\n    parent = expanded.parent.resolve(strict=False)\n    parent.mkdir(parents=True, exist_ok=True)\n    _reject_symlink_components(expanded)\n    if not parent.is_dir():\n        raise ValueError(\"destination parent must be a regular directory\")\n    destination = parent / expanded.name\n    if os.path.lexists(destination):\n        raise FileExistsError(destination)",
    "generator inherited path confinement",
)
write(path, text)

# ---------------------------------------------------------------------------
# Python runtime: exact admission on the real dispatch/publication path and
# observation-derived evidence.
# ---------------------------------------------------------------------------
path = "skills/mcp-steward-architect/tools/steward-templates/python/steward_runtime.py.template"
text = read(path)

admission_helper = '''def _capability_digest(capability: dict[str, Any]) -> str | None:
    contract = capability.get("contract")
    if not isinstance(contract, dict):
        return None
    try:
        identity = {"source": contract["source"], "id": contract["id"], "revision": contract["revision"]}
    except KeyError:
        return None
    return _digest(identity)


def _target_identity(job: dict[str, Any]) -> str:
    subject = job["subject"]
    return f"{subject['type']}:{subject['id']}:{subject.get('revision') or 'none'}"


def _evaluate_mutation(
    effect: dict[str, Any], job: dict[str, Any], capability: dict[str, Any], authority: dict[str, Any],
    *, current_job_id: str, current_generation: int, current_attempt_id: str, current_version: int,
    remaining_budget_ms: int, receipt: dict[str, Any] | None, candidate: dict[str, Any] | None,
    now: datetime,
) -> dict[str, Any]:
    reasons: list[tuple[str, str]] = []
    if job["jobId"] != current_job_id or job["generation"] != current_generation:
        reasons.append(("LostAuthority", "stale job/generation"))
    if job["attemptId"] != current_attempt_id or int(job["version"]) != int(current_version):
        reasons.append(("LostAuthority", "stale attempt/version"))
    if job["status"] in _TERMINAL or job["cancellation"] in {"requested", "fenced", "reconciling"}:
        reasons.append(("LostAuthority", "job is terminal or cancellation-fenced"))
    target = _target_identity(job)
    if authority.get("source") != effect["authority_source"]:
        reasons.append(("LostAuthority", "authority source mismatch"))
    if not authority.get("principal") or authority.get("scope") != effect["id"] or authority.get("target") != target:
        reasons.append(("LostAuthority", "authority principal/scope/target mismatch"))
    if authority.get("attemptId") != current_attempt_id or int(authority.get("jobVersion", -1)) != int(current_version):
        reasons.append(("LostAuthority", "authority attempt/version fence mismatch"))
    if effect["lease_required"]:
        lease = job.get("lease")
        if not isinstance(lease, dict):
            reasons.append(("LostAuthority", "required lease missing"))
        else:
            if _parse(str(lease["expiresAt"])) <= now:
                reasons.append(("LostAuthority", "required lease expired"))
            if authority.get("principal") != lease.get("owner") or authority.get("leaseOwner") != lease.get("owner"):
                reasons.append(("LostAuthority", "lease owner mismatch"))
            if authority.get("leaseFencingToken") != lease.get("fencingToken"):
                reasons.append(("LostAuthority", "lease fencing token mismatch"))
    if effect["candidate_required"]:
        if candidate is None or candidate != job.get("candidate"):
            reasons.append(("StaleCandidate", "exact candidate mismatch"))
    contract = capability.get("contract") if isinstance(capability.get("contract"), dict) else {}
    if capability.get("capability_id") != effect["capability_ref"] or contract.get("id") != capability.get("capability_id"):
        reasons.append(("CapabilityUnavailable", "capability identity mismatch"))
    if _capability_digest(capability) != contract.get("digest"):
        reasons.append(("CapabilityUnavailable", "capability contract provenance/digest mismatch"))
    if remaining_budget_ms < int(effect["minimum_budget_ms"]):
        reasons.append(("BudgetUnavailable", "remaining budget below mutation minimum"))
    if effect["durable_operation_required"]:
        if receipt is None:
            reasons.append(("ReconciliationRequired", "durable receipt missing"))
        else:
            if receipt.get("jobId") != current_job_id or receipt.get("generation") != current_generation or receipt.get("attemptId") != current_attempt_id:
                reasons.append(("LostAuthority", "receipt stale job/generation/attempt"))
            if int(receipt.get("jobVersion", -1)) != int(current_version):
                reasons.append(("LostAuthority", "receipt stale optimistic version"))
            if receipt.get("targetIdentity") != target:
                reasons.append(("LostAuthority", "receipt target mismatch"))
            if receipt.get("capabilityIdentity") != capability.get("capability_id") or receipt.get("capabilityContractDigest") != contract.get("digest"):
                reasons.append(("CapabilityUnavailable", "receipt capability provenance mismatch"))
            if candidate is not None and receipt.get("candidateDigest") != candidate.get("digest"):
                reasons.append(("StaleCandidate", "receipt candidate mismatch"))
            if receipt.get("state") != "reserved" or receipt.get("delivery") != "not-delivered":
                reasons.append(("ReconciliationRequired", "receipt is not reserved/not-delivered"))
    if reasons:
        return {"disposition": reasons[0][0], "reasons": [reason for _, reason in reasons]}
    return {"disposition": "Admitted", "reasons": []}


'''
text = replace_once(text, "class SystemClock:\n", admission_helper + "class SystemClock:\n", "python runtime admission helper")

text = replace_once(
    text,
    '    def poll(self, remote_handle: str, subject: dict[str, Any]) -> dict[str, Any]:\n        return {"state": "completed", "remoteHandle": remote_handle, "subject": subject, "revision": "terminal-1"}',
    '    def poll(self, remote_handle: str, subject: dict[str, Any]) -> dict[str, Any]:\n        return {\n            "state": "completed", "remoteHandle": remote_handle, "subject": subject, "revision": "terminal-1",\n            "observation": {\n                "producerId": self.producer_id, "observationGrade": "observed", "authorityClass": "observed",\n                "binding": {"satisfied": ["target"]}, "coverage": {"required": 1, "observed": 1},\n            },\n        }',
    "python provider observation envelope",
)

text = replace_once(
    text,
    "              operation_id TEXT PRIMARY KEY,operation_kind TEXT,job_id TEXT,lineage_id TEXT,generation INTEGER,attempt_id TEXT,\n              capability_identity TEXT,capability_contract_digest TEXT,target_identity TEXT,candidate_digest TEXT,request_digest TEXT,\n              state TEXT,delivery TEXT,retry_disposition TEXT,credential_slot_id TEXT,remote_handle TEXT,result_json TEXT,\n              created_at TEXT,observed_at TEXT,reconcile_count INTEGER);",
    "              operation_id TEXT PRIMARY KEY,operation_kind TEXT,job_id TEXT,lineage_id TEXT,generation INTEGER,attempt_id TEXT,job_version INTEGER,\n              capability_identity TEXT,capability_contract_digest TEXT,target_identity TEXT,candidate_digest TEXT,request_digest TEXT,\n              state TEXT,delivery TEXT,retry_disposition TEXT,credential_slot_id TEXT,remote_handle TEXT,result_json TEXT,\n              created_at TEXT,observed_at TEXT,reconcile_count INTEGER,mutation_decision_ref TEXT);",
    "python operation durable admission columns",
)

text = replace_once(
    text,
    "        if row is None:\n            raise KeyError(job_id)\n        return {",
    "        if row is None:\n            raise KeyError(job_id)\n        lease = None if row[\"status\"] in _TERMINAL else {\n            \"owner\": f\"steward-runtime:{row['attempt_id']}\", \"fencingToken\": row[\"generation\"], \"expiresAt\": row[\"deadline_at\"]\n        }\n        return {",
    "python derived authoritative lease",
)
text = replace_once(
    text,
    '            "finalizationStartsAt": row["finalization_starts_at"], "lease": None, "cancellation": row["cancellation"],',
    '            "finalizationStartsAt": row["finalization_starts_at"], "lease": lease, "cancellation": row["cancellation"],',
    "python job exposes lease",
)

reserve_external = '''    def reserve_external(self, job_id: str, capability: dict[str, Any], kind: str = "submit") -> dict[str, Any]:
        job = self.job(job_id)
        existing = self.operation_for_job(job_id, kind)
        if existing is not None:
            return existing
        operation_id = f"operation-{uuid.uuid4().hex}"
        now = _iso(self.clock.now())
        target = _target_identity(job)
        request = {"kind": kind, "subject": job["subject"], "candidate": job["candidate"]}
        with self._write() as db:
            if not self._is_current_tx(db, job_id, int(job["generation"]), str(job["attemptId"])):
                raise RuntimeError("stale lineage operation reservation")
            db.execute(
                "INSERT INTO external_operations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,NULL)",
                (operation_id, kind, job_id, job["lineageId"], job["generation"], job["attemptId"], int(job["version"]) + 1,
                 capability["capability_id"], capability["contract"]["digest"], target, job["candidate"]["digest"],
                 _digest(request), "reserved", "not-delivered", "forbidden", "primary", None, None, now, now),
            )
            self._advance(db, job_id, stage=f"{kind}-reserved", marker=f"{kind}-reserved")
            self._audit(db, job_id, "external-reserved", {"operationId": operation_id, "kind": kind,
                        "capabilityContractDigest": capability["contract"]["digest"]})
        return self.operation_for_job(job_id, kind) or {}

    @staticmethod
    def _receipt_view(op: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        return {
            "jobId": op["job_id"], "generation": op["generation"], "attemptId": op["attempt_id"],
            "jobVersion": op["job_version"], "capabilityIdentity": op["capability_identity"],
            "capabilityContractDigest": op["capability_contract_digest"], "targetIdentity": op["target_identity"],
            "candidateDigest": op["candidate_digest"], "state": op["state"], "delivery": op["delivery"],
        }

    def begin_dispatch(
        self, operation_id: str, effect: dict[str, Any], capability: dict[str, Any], authority: dict[str, Any]
    ) -> dict[str, Any]:
        now = self.clock.now()
        with self._write() as db:
            op = db.execute("SELECT * FROM external_operations WHERE operation_id=?", (operation_id,)).fetchone()
            if op is None:
                raise KeyError(operation_id)
            row = db.execute("SELECT * FROM steward_jobs WHERE job_id=?", (op["job_id"],)).fetchone()
            lineage = db.execute("SELECT * FROM steward_lineages WHERE lineage_id=?", (op["lineage_id"],)).fetchone()
            if row is None or lineage is None:
                raise RuntimeError("mutation admission lost canonical job/lineage")
            lease = None if row["status"] in _TERMINAL else {
                "owner": f"steward-runtime:{row['attempt_id']}", "fencingToken": row["generation"], "expiresAt": row["deadline_at"]
            }
            job = {
                "jobId": row["job_id"], "lineageId": row["lineage_id"], "generation": row["generation"],
                "attemptId": row["attempt_id"], "version": row["version"], "subject": json.loads(row["subject_json"]),
                "candidate": json.loads(row["candidate_json"]), "status": row["status"], "cancellation": row["cancellation"],
                "deadlineAt": row["deadline_at"], "lease": lease,
            }
            budget_ms = max(0, int((_parse(job["deadlineAt"]) - now).total_seconds() * 1000))
            decision = _evaluate_mutation(
                effect, job, capability, authority,
                current_job_id=str(lineage["current_job_id"]), current_generation=int(lineage["current_generation"]),
                current_attempt_id=str(row["attempt_id"]), current_version=int(row["version"]),
                remaining_budget_ms=budget_ms, receipt=self._receipt_view(op), candidate=job["candidate"], now=now,
            )
            if decision["disposition"] != "Admitted":
                reason = f"mutation-admission:{decision['disposition']}"
                self._advance(db, str(op["job_id"]), status="blocked", stage="mutation-admission-rejected",
                              marker=reason, blocked_reason=reason)
                self._audit(db, str(op["job_id"]), "mutation-admission-rejected",
                            {"operationId": operation_id, "effect": effect["id"], "disposition": decision["disposition"]})
                return decision
            decision_ref = f"admission-{uuid.uuid4().hex}"
            db.execute(
                "UPDATE external_operations SET state='dispatching',delivery='delivery-unknown',retry_disposition='reconcile-first',"
                "observed_at=?,mutation_decision_ref=? WHERE operation_id=?",
                (_iso(now), decision_ref, operation_id),
            )
            status = "cancelling" if op["operation_kind"] == "cancel" else "reconciling"
            cancellation = "reconciling" if op["operation_kind"] == "cancel" else None
            self._advance(db, str(op["job_id"]), status=status, stage=f"{op['operation_kind']}-dispatch-started",
                          marker=f"{op['operation_kind']}-dispatch-started", cancellation=cancellation)
            self._audit(db, str(op["job_id"]), "mutation-admitted",
                        {"operationId": operation_id, "effect": effect["id"], "decisionRef": decision_ref})
            return {"disposition": "Admitted", "reasons": [], "decisionRef": decision_ref}

'''
text = replace_regex(
    text,
    r"    def reserve_external\(self, job_id: str, capability: dict\[str, Any\], kind: str = \"submit\"\) -> dict\[str, Any\]:\n.*?(?=    def bind_dispatch)",
    reserve_external,
    "python reserve/begin-dispatch gate",
)

persist_evidence = '''    def persist_evidence(
        self, job_id: str, requirement: dict[str, Any], criterion: dict[str, Any], adapter_producer_id: str,
        payload: dict[str, Any], recipe_id: str, operation: dict[str, Any], producer: dict[str, Any],
    ) -> bool:
        observation = payload.get("observation")
        if not isinstance(observation, dict) or observation.get("producerId") != adapter_producer_id:
            return False
        producer_id = str(observation.get("producerId", ""))
        if producer_id != producer.get("producer_id"):
            return False
        if criterion["approved_producers"] and producer_id not in criterion["approved_producers"]:
            return False
        authority = str(observation.get("authorityClass", ""))
        if authority not in _AUTHORITY_RANK:
            return False
        ceiling = str(producer.get("authority_ceiling", "advisory"))
        if ceiling not in _AUTHORITY_RANK:
            return False
        if _AUTHORITY_RANK[authority] > _AUTHORITY_RANK[ceiling]:
            authority = ceiling
        binding_observation = observation.get("binding")
        coverage_observation = observation.get("coverage")
        if not isinstance(binding_observation, dict) or not isinstance(coverage_observation, dict):
            return False
        actual_satisfied = {str(item) for item in binding_observation.get("satisfied", [])}
        job = self.job(job_id)
        if operation.get("candidate_digest") == job["candidate"]["digest"]:
            actual_satisfied.add("candidate")
        required = [str(item) for item in criterion["binding_requirements"]]
        satisfied = [item for item in required if item in actual_satisfied]
        binding_status = "complete" if set(required) <= set(satisfied) else ("partial" if satisfied else "unknown")
        binding = {"required": required, "satisfied": satisfied, "status": binding_status}
        try:
            required_count = int(coverage_observation["required"])
            observed_count = int(coverage_observation["observed"])
        except (KeyError, TypeError, ValueError):
            return False
        if required_count < 1 or observed_count < 0 or observed_count > required_count:
            return False
        coverage_state = "complete" if observed_count >= required_count else ("partial" if observed_count else "unknown")
        coverage = {"state": coverage_state, "required": required_count, "observed": observed_count}
        observation_grade = str(observation.get("observationGrade", ""))
        if not observation_grade:
            return False
        observed = self.clock.now()
        evidence_id = f"evidence-{uuid.uuid4().hex}"
        with self._write() as db:
            if not self._is_current_tx(db, job_id, int(job["generation"]), str(job["attemptId"])):
                raise RuntimeError("stale lineage evidence")
            db.execute(
                "INSERT INTO steward_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (evidence_id, job_id, job["lineageId"], job["generation"], _canonical(job["subject"]), _canonical(job["candidate"]),
                 requirement["id"], criterion["canonical_claim"], requirement["evidence_class"], observation_grade,
                 authority, producer_id, recipe_id, _canonical(binding), _canonical(coverage), _iso(observed),
                 _iso(observed + timedelta(seconds=int(criterion["freshness_seconds"]))), _digest(payload)),
            )
            self._advance(db, job_id, status="finalizing", stage="evidence-persisted", marker=f"evidence:{evidence_id}")
            self._audit(db, job_id, "evidence-persisted", {"evidenceId": evidence_id, "claimId": criterion["canonical_claim"],
                        "authorityClass": authority, "bindingStatus": binding_status, "coverageState": coverage_state})
        return True

'''
text = replace_regex(
    text,
    r"    def persist_evidence\(self, job_id: str, requirement: dict\[str, Any\], criterion: dict\[str, Any\], producer_id: str,\n.*?(?=    def block)",
    persist_evidence,
    "python observation-derived evidence",
)

save_terminal = '''    def save_terminal(
        self, job_id: str, completion: dict[str, Any], handoff: dict[str, Any], *,
        expected_attempt_id: str, expected_version: int, mutation_decision_ref: str,
    ) -> None:
        with self._write() as db:
            row = db.execute(
                "SELECT j.generation,j.candidate_json,j.attempt_id,j.version,l.current_generation,l.current_job_id,l.candidate_json "
                "FROM steward_jobs j JOIN steward_lineages l ON l.lineage_id=j.lineage_id WHERE j.job_id=?", (job_id,),
            ).fetchone()
            if (row is None or row[0] != row[4] or row[5] != job_id or row[1] != row[6]
                    or row[2] != expected_attempt_id or int(row[3]) != int(expected_version)):
                raise RuntimeError("stale lineage/candidate/attempt/version publication")
            if self.unresolved_lineage_operations(job_id):
                raise RuntimeError("completion blocked by unresolved lineage operation")
            db.execute("INSERT OR REPLACE INTO completion_evaluations VALUES(?,?)", (job_id, _canonical(completion)))
            db.execute("INSERT OR REPLACE INTO steward_handoffs VALUES(?,?)", (job_id, _canonical(handoff)))
            self._advance(db, job_id, status="completed", stage="completed", marker="completed")
            self._audit(db, job_id, "handoff-sealed", {"digest": handoff["digest"], "candidate": handoff["candidate"]["digest"],
                        "mutationDecisionRef": mutation_decision_ref})

'''
text = replace_regex(text, r"    def save_terminal\(self, job_id: str, completion: dict\[str, Any\], handoff: dict\[str, Any\]\) -> None:\n.*?(?=    def result)", save_terminal, "python fenced terminal publication")

constructor = '''    def __init__(
        self, store: StewardStore, profile: dict[str, Any], proof_recipe: dict[str, Any], mutation_policy: dict[str, Any], *,
        upstream: dict[str, Any], provider: FakeProvider | None = None, faults: FaultInjector | None = None,
    ) -> None:
        if not isinstance(upstream, dict) or not isinstance(mutation_policy, dict):
            raise ValueError("explicit reviewed upstream capability and mutation policy are required")
        self.store, self.profile, self.proof_recipe = store, profile, proof_recipe
        self.mutation_policy, self.upstream = mutation_policy, upstream
        self.provider, self.faults = provider or FakeProvider(), faults or FaultInjector()
        self._stop, self._thread = threading.Event(), None

'''
text = replace_regex(
    text,
    r"    def __init__\(self, store: StewardStore, profile: dict\[str, Any\], proof_recipe: dict\[str, Any\], \*,\n.*?(?=    @property\n    def recipe_id)",
    constructor,
    "python runtime explicit design pack constructor",
)

runtime_helpers = '''    def _effect(self, effect_id: str) -> dict[str, Any]:
        for effect in self.mutation_policy["effects"]:
            if effect["id"] == effect_id:
                return effect
        raise RuntimeError(f"mutation policy has no effect {effect_id}")

    def _producer(self, producer_id: str) -> dict[str, Any] | None:
        for producer in self.proof_recipe["producers"]:
            if producer["producer_id"] == producer_id:
                return producer
        return None

    @staticmethod
    def _local_handoff_capability() -> dict[str, Any]:
        identity = {"source": "local", "id": "local:handoff@1", "revision": "1"}
        return {"capability_id": "local:handoff@1", "contract": {**identity, "digest": _digest(identity)}}

    def _authority(self, effect_id: str, job: dict[str, Any], *, source: str, target: str) -> dict[str, Any]:
        lease = job.get("lease") if isinstance(job.get("lease"), dict) else None
        principal = lease["owner"] if lease is not None else f"{source}:{job['attemptId']}"
        return {
            "source": source, "principal": principal, "scope": effect_id, "target": target,
            "attemptId": job["attemptId"], "jobVersion": job["version"],
            "leaseOwner": None if lease is None else lease["owner"],
            "leaseFencingToken": None if lease is None else lease["fencingToken"],
        }

'''
text = replace_once(text, "    def submit(self, subject_id: str, subject_revision: str | None, idempotency_key: str) -> dict[str, Any]:\n", runtime_helpers + "    def submit(self, subject_id: str, subject_revision: str | None, idempotency_key: str) -> dict[str, Any]:\n", "python runtime policy helpers")

finalize = '''    def finalize_with_gate(self, job_id: str) -> None:
        completion = self.completion_gate(job_id)
        if completion["disposition"] != "eligible":
            self.store.block(job_id, "completion-obligations-unresolved")
            return
        job = self.store.job(job_id)
        effect = self._effect("terminal-publication")
        capability = self._local_handoff_capability()
        budget_ms = max(0, int((_parse(job["deadlineAt"]) - self.store.clock.now()).total_seconds() * 1000))
        admission = _evaluate_mutation(
            effect, job, capability,
            self._authority("terminal-publication", job, source="completion-gate", target=_target_identity(job)),
            current_job_id=job_id, current_generation=int(job["generation"]), current_attempt_id=str(job["attemptId"]),
            current_version=int(job["version"]), remaining_budget_ms=budget_ms, receipt=None,
            candidate=job["candidate"], now=self.store.clock.now(),
        )
        if admission["disposition"] != "Admitted":
            self.store.block(job_id, f"mutation-admission:{admission['disposition']}")
            return
        decision_ref = f"admission-{uuid.uuid4().hex}"
        handoff = {
            "schema_version": 2, "handoffId": f"handoff-{uuid.uuid4().hex}", "jobId": job_id,
            "lineageId": job["lineageId"], "generation": job["generation"], "subject": job["subject"],
            "candidate": job["candidate"], "status": "completed", "actionable": True,
            "outcome": "seed-provider-completed", "evidenceRefs": [ref for item in completion["obligations"] for ref in item["evidenceRefs"]],
            "artifactRefs": [], "externalOperationRefs": job["externalOperationRefs"], "gaps": [],
            "correlationId": job_id, "sealedAt": _iso(self.store.clock.now()),
        }
        handoff["digest"] = compute_handoff_digest(handoff)
        if self.faults.trip("before-terminal-publication"):
            return
        self.store.save_terminal(
            job_id, completion, handoff, expected_attempt_id=str(job["attemptId"]),
            expected_version=int(job["version"]), mutation_decision_ref=decision_ref,
        )

'''
text = replace_regex(text, r"    def finalize_with_gate\(self, job_id: str\) -> None:\n.*?(?=    def _handle_cancellation)", finalize, "python publication mutation gate")

text = replace_once(
    text,
    '        if cancel_op["delivery"] == "not-delivered":\n            self.store.begin_dispatch(cancel_op["operation_id"])\n            if self.faults.trip("after-cancel-start"):',
    '        if cancel_op["delivery"] == "not-delivered":\n            current = self.store.job(job["jobId"])\n            admission = self.store.begin_dispatch(\n                cancel_op["operation_id"], self._effect("cancellation-dispatch"), self.upstream,\n                self._authority("cancellation-dispatch", current, source="steward-runtime", target=cancel_op["target_identity"]),\n            )\n            if admission["disposition"] != "Admitted":\n                return True\n            if self.faults.trip("after-cancel-start"):',
    "python cancellation admission before provider",
)
text = replace_once(
    text,
    '        if submit["delivery"] == "not-delivered":\n            self.store.begin_dispatch(submit["operation_id"])\n            if self.faults.trip("after-dispatch-start"):',
    '        if submit["delivery"] == "not-delivered":\n            current = self.store.job(job["jobId"])\n            admission = self.store.begin_dispatch(\n                submit["operation_id"], self._effect("external-dispatch"), self.upstream,\n                self._authority("external-dispatch", current, source="steward-runtime", target=submit["target_identity"]),\n            )\n            if admission["disposition"] != "Admitted":\n                return True\n            if self.faults.trip("after-dispatch-start"):',
    "python dispatch admission before provider",
)
text = replace_once(
    text,
    '            for requirement in self.profile["completion"]["obligations"]:\n                criterion = self._criterion(requirement["id"])\n                if not self._provider_approved(criterion):\n                    continue\n                self.store.persist_evidence(job["jobId"], requirement, criterion, self.provider.producer_id, payload, self.recipe_id)\n                promoted = True',
    '            for requirement in self.profile["completion"]["obligations"]:\n                criterion = self._criterion(requirement["id"])\n                producer = self._producer(self.provider.producer_id)\n                if producer is None:\n                    continue\n                if self.store.persist_evidence(\n                    job["jobId"], requirement, criterion, self.provider.producer_id, payload, self.recipe_id, submit, producer\n                ):\n                    promoted = True',
    "python observation promotion call",
)
text = replace_once(
    text,
    '            proof = json.loads(package.joinpath("steward_proof_recipe.json").read_text(encoding="utf-8"))\n            upstream = json.loads(package.joinpath("steward_upstream_capability.json").read_text(encoding="utf-8"))\n            _DEFAULT_RUNTIME = StewardRuntime(\n                StewardStore(Path(os.environ.get("STEWARD_STATE_PATH", "steward-state.db"))), profile, proof, upstream=upstream\n            )',
    '            proof = json.loads(package.joinpath("steward_proof_recipe.json").read_text(encoding="utf-8"))\n            mutation = json.loads(package.joinpath("steward_mutation_policy.json").read_text(encoding="utf-8"))\n            upstream = json.loads(package.joinpath("steward_upstream_capability.json").read_text(encoding="utf-8"))\n            _DEFAULT_RUNTIME = StewardRuntime(\n                StewardStore(Path(os.environ.get("STEWARD_STATE_PATH", "steward-state.db"))), profile, proof, mutation, upstream=upstream\n            )',
    "python default runtime explicit mutation policy",
)
write(path, text)

# Generated Python tests now load the active mutation policy too.
path = "skills/mcp-steward-architect/tools/steward-templates/python/test_steward_runtime.py.template"
text = read(path)
text = text.replace(
    "def _docs() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:",
    "def _docs() -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:",
)
text = replace_once(
    text,
    '        json.loads((root / "steward_proof_recipe.json").read_text(encoding="utf-8")),\n        json.loads((root / "steward_upstream_capability.json").read_text(encoding="utf-8")),',
    '        json.loads((root / "steward_proof_recipe.json").read_text(encoding="utf-8")),\n        json.loads((root / "steward_mutation_policy.json").read_text(encoding="utf-8")),\n        json.loads((root / "steward_upstream_capability.json").read_text(encoding="utf-8")),',
    "generated python test docs mutation policy",
)
text = replace_once(
    text,
    "    profile, proof, upstream = _docs()\n    return StewardRuntime(\n        StewardStore(path, FakeClock(datetime(2026, 1, 1, tzinfo=UTC))), profile, proof,\n        upstream=upstream, faults=FaultInjector(faults), provider=provider,\n    )",
    "    profile, proof, mutation, upstream = _docs()\n    return StewardRuntime(\n        StewardStore(path, FakeClock(datetime(2026, 1, 1, tzinfo=UTC))), profile, proof, mutation,\n        upstream=upstream, faults=FaultInjector(faults), provider=provider,\n    )",
    "generated python runtime constructor",
)
write(path, text)

# ---------------------------------------------------------------------------
# .NET runtime: fail-closed snapshot recovery, exact Design Pack provenance,
# mutation admission on actual side-effect paths, and observation-derived proof.
# ---------------------------------------------------------------------------
path = "skills/mcp-steward-architect/tools/steward-templates/dotnet/StewardSeedRuntime.cs.template"
text = read(path)
text = replace_once(
    text,
    '    public SeedPollResult Poll(string remoteHandle, StewardSubject subject) => new(true, JsonSerializer.SerializeToElement(new { state = "completed", remoteHandle, subject, revision = "terminal-1" }));',
    '    public SeedPollResult Poll(string remoteHandle, StewardSubject subject) => new(true, JsonSerializer.SerializeToElement(new { state = "completed", remoteHandle, subject, revision = "terminal-1", observation = new { producerId = ProducerId, observationGrade = "observed", authorityClass = "observed", binding = new { satisfied = new[] { "target" } }, coverage = new { required = 1, observed = 1 } } }));',
    ".NET provider observation envelope",
)
text = replace_once(
    text,
    "public sealed record StewardCandidate(string Type, string Id, string? Revision, string Digest);\npublic sealed record StewardSeedJob(",
    "public sealed record StewardCandidate(string Type, string Id, string? Revision, string Digest);\npublic sealed record StewardLease(string Owner, long FencingToken, DateTimeOffset ExpiresAt);\npublic sealed record StewardSeedJob(",
    ".NET lease record",
)
text = replace_once(
    text,
    "    DateTimeOffset DeadlineAt, DateTimeOffset? FinalizationStartsAt,\n    IReadOnlyList<string> EvidenceRefs, IReadOnlyList<string> ExternalOperationRefs);",
    "    DateTimeOffset DeadlineAt, DateTimeOffset? FinalizationStartsAt, StewardLease? Lease,\n    IReadOnlyList<string> EvidenceRefs, IReadOnlyList<string> ExternalOperationRefs);",
    ".NET job lease field",
)
text = replace_once(
    text,
    "    string OperationId, string OperationKind, string JobId, string LineageId, long Generation, string AttemptId,\n    string CapabilityIdentity, string CapabilityContractDigest, string TargetIdentity, string CandidateDigest,",
    "    string OperationId, string OperationKind, string JobId, string LineageId, long Generation, string AttemptId, long JobVersion,\n    string CapabilityIdentity, string CapabilityContractDigest, string TargetIdentity, string CandidateDigest,",
    ".NET operation job version",
)
text = replace_once(
    text,
    "    string? RemoteHandle, JsonElement? Result, DateTimeOffset CreatedAt, DateTimeOffset ObservedAt, int ReconcileCount);",
    "    string? RemoteHandle, JsonElement? Result, DateTimeOffset CreatedAt, DateTimeOffset ObservedAt, int ReconcileCount, string? MutationDecisionRef);",
    ".NET operation decision ref",
)
text = replace_once(
    text,
    "internal sealed record SeedRequirement(string Id, bool Required, string EvidenceClass, string CanonicalClaim, string RequiredAuthority, int FreshnessSeconds, IReadOnlySet<string> ApprovedProducers, IReadOnlyList<string> BindingRequirements, string CoverageSemantics);\ninternal sealed record SeedAction(string Kind, StewardSeedJob Job, StewardOperation Operation);",
    "internal sealed record SeedRequirement(string Id, bool Required, string EvidenceClass, string CanonicalClaim, string RequiredAuthority, int FreshnessSeconds, IReadOnlySet<string> ApprovedProducers, IReadOnlyList<string> BindingRequirements, string CoverageSemantics);\ninternal sealed record SeedProducer(string Id, string AuthorityCeiling, IReadOnlySet<string> BindingRequirements, IReadOnlySet<string> SubjectDimensions);\ninternal sealed record SeedMutationEffect(string Id, string AuthoritySource, bool LeaseRequired, bool CandidateRequired, string CapabilityRef, bool DurableOperationRequired, int MinimumBudgetMs);\ninternal sealed record SeedCapability(string Id, string Source, string Revision, string Digest);\ninternal sealed record SeedAction(string Kind, StewardSeedJob Job, StewardOperation Operation);",
    ".NET policy records",
)

seed_policy = '''internal sealed class SeedPolicy
{
    public required int ProfileRevision { get; init; }
    public required string RecipeId { get; init; }
    public required int ProofRevision { get; init; }
    public required IReadOnlyList<SeedRequirement> Requirements { get; init; }
    public required IReadOnlyDictionary<string, SeedProducer> Producers { get; init; }
    public required IReadOnlyDictionary<string, SeedMutationEffect> Effects { get; init; }
    public required SeedCapability Capability { get; init; }

    private static string CapabilityDigest(string source, string id, string revision)
    {
        var identity = new SortedDictionary<string, string>(StringComparer.Ordinal) { ["id"] = id, ["revision"] = revision, ["source"] = source };
        return "sha256:" + Convert.ToHexStringLower(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(identity)));
    }

    public static SeedPolicy Load(string profilePath, string proofPath)
    {
        var root = Path.GetDirectoryName(Path.GetFullPath(profilePath)) ?? throw new InvalidOperationException("profile path has no directory");
        var mutationPath = Path.Combine(root, "steward_mutation_policy.json");
        var upstreamPath = Path.Combine(root, "steward_upstream_capability.json");
        using var profile = JsonDocument.Parse(File.ReadAllText(profilePath));
        using var proof = JsonDocument.Parse(File.ReadAllText(proofPath));
        using var mutation = JsonDocument.Parse(File.ReadAllText(mutationPath));
        using var upstream = JsonDocument.Parse(File.ReadAllText(upstreamPath));
        var producerMap = proof.RootElement.GetProperty("producers").EnumerateArray().ToDictionary(
            item => item.GetProperty("producer_id").GetString()!,
            item => new SeedProducer(
                item.GetProperty("producer_id").GetString()!, item.GetProperty("authority_ceiling").GetString()!,
                item.GetProperty("binding_requirements").EnumerateArray().Select(value => value.GetString()!).ToHashSet(StringComparer.Ordinal),
                item.GetProperty("subject_dimensions").EnumerateArray().Select(value => value.GetString()!).ToHashSet(StringComparer.Ordinal)),
            StringComparer.Ordinal);
        var criteria = proof.RootElement.GetProperty("criteria").EnumerateArray().ToDictionary(item => item.GetProperty("criterion_id").GetString()!, item => item.Clone(), StringComparer.Ordinal);
        var requirements = new List<SeedRequirement>();
        foreach (var obligation in profile.RootElement.GetProperty("completion").GetProperty("obligations").EnumerateArray())
        {
            var id = obligation.GetProperty("id").GetString()!;
            if (!criteria.TryGetValue(id, out var criterion)) throw new InvalidOperationException($"proof recipe has no criterion for obligation {id}");
            requirements.Add(new(
                id, obligation.GetProperty("required").GetBoolean(), obligation.GetProperty("evidence_class").GetString()!,
                criterion.GetProperty("canonical_claim").GetString()!, criterion.GetProperty("required_authority").GetString()!,
                criterion.GetProperty("freshness_seconds").GetInt32(),
                criterion.GetProperty("approved_producers").EnumerateArray().Select(item => item.GetString()!).ToHashSet(StringComparer.Ordinal),
                criterion.GetProperty("binding_requirements").EnumerateArray().Select(item => item.GetString()!).ToArray(),
                criterion.GetProperty("coverage_semantics").GetString()!));
        }
        var effects = mutation.RootElement.GetProperty("effects").EnumerateArray().ToDictionary(
            item => item.GetProperty("id").GetString()!,
            item => new SeedMutationEffect(
                item.GetProperty("id").GetString()!, item.GetProperty("authority_source").GetString()!,
                item.GetProperty("lease_required").GetBoolean(), item.GetProperty("candidate_required").GetBoolean(),
                item.GetProperty("capability_ref").GetString()!, item.GetProperty("durable_operation_required").GetBoolean(),
                item.GetProperty("minimum_budget_ms").GetInt32()), StringComparer.Ordinal);
        var contract = upstream.RootElement.GetProperty("contract");
        var capability = new SeedCapability(
            upstream.RootElement.GetProperty("capability_id").GetString()!, contract.GetProperty("source").GetString()!,
            contract.GetProperty("revision").GetString()!, contract.GetProperty("digest").GetString()!);
        if (!string.Equals(contract.GetProperty("id").GetString(), capability.Id, StringComparison.Ordinal)
            || !string.Equals(CapabilityDigest(capability.Source, capability.Id, capability.Revision), capability.Digest, StringComparison.Ordinal))
            throw new InvalidOperationException("reviewed upstream capability contract identity/digest is invalid");
        var revision = proof.RootElement.GetProperty("revision").GetInt32();
        return new() {
            ProfileRevision = profile.RootElement.GetProperty("steward").GetProperty("contract_revision").GetInt32(),
            RecipeId = $"{proof.RootElement.GetProperty("recipe_id").GetString()}@{revision}", ProofRevision = revision,
            Requirements = requirements, Producers = producerMap, Effects = effects, Capability = capability,
        };
    }
}

'''
text = replace_regex(text, r"internal sealed class SeedPolicy\n\{.*?(?=public sealed class StewardSeedRuntime)", seed_policy, ".NET active Design Pack loader")

text = replace_once(
    text,
    '            var job = new StewardSeedJob(jobId, lineageId, generation, $"attempt-{Guid.NewGuid():N}", 0, subject, candidate, requestDigest,\n                "queued", "admitted", "none", null, now, now, now, now, 1, "admitted", now.AddMinutes(15), null, [], []);',
    '            var attemptId = $"attempt-{Guid.NewGuid():N}"; var deadline = now.AddMinutes(15);\n            var lease = new StewardLease($"steward-runtime:{attemptId}", generation, deadline);\n            var job = new StewardSeedJob(jobId, lineageId, generation, attemptId, 0, subject, candidate, requestDigest,\n                "queued", "admitted", "none", null, now, now, now, now, 1, "admitted", deadline, null, lease, [], []);',
    ".NET persisted lease at admission",
)

text = replace_once(
    text,
    '                    if (submit.Delivery == "not-delivered") { BeginDispatchLocked(submit.OperationId); SaveLocked(); action = new("dispatch", job, _state.Operations[submit.OperationId]); }',
    '                    if (submit.Delivery == "not-delivered") { if (!BeginDispatchLocked(submit.OperationId, "external-dispatch")) { SaveLocked(); return true; } SaveLocked(); action = new("dispatch", _state.Jobs[job.JobId], _state.Operations[submit.OperationId]); }',
    ".NET dispatch gate call",
)
text = replace_once(
    text,
    '        if (cancel.Delivery == "not-delivered") { BeginDispatchLocked(cancel.OperationId); SaveLocked(); return new("cancel-dispatch", job, _state.Operations[cancel.OperationId]); }',
    '        if (cancel.Delivery == "not-delivered") { if (!BeginDispatchLocked(cancel.OperationId, "cancellation-dispatch")) { SaveLocked(); return null; } SaveLocked(); return new("cancel-dispatch", _state.Jobs[job.JobId], _state.Operations[cancel.OperationId]); }',
    ".NET cancellation gate call",
)
text = replace_once(
    text,
    '                    else if (!HasEvidenceLocked(job.JobId)) { PromoteOrBlockLocked(job, submit.Result.Value); SaveLocked(); return true; }',
    '                    else if (!HasEvidenceLocked(job.JobId)) { PromoteOrBlockLocked(job, submit, submit.Result.Value); SaveLocked(); return true; }',
    ".NET evidence promotion gets causal receipt",
)

reserve_and_begin = '''    private void ReserveOperationLocked(StewardSeedJob job, string kind, string? submitOperationId = null)
    {
        RequireCurrentLocked(job);
        var id = $"operation-{Guid.NewGuid():N}"; var now = _clock.UtcNow;
        var requestDigest = submitOperationId ?? job.RequestDigest;
        var op = new StewardOperation(id, kind, job.JobId, job.LineageId, job.Generation, job.AttemptId, job.Version + 1,
            _policy.Capability.Id, _policy.Capability.Digest, $"target:{job.Subject.Id}:{job.Subject.Revision ?? "none"}",
            job.Candidate.Digest, requestDigest, "reserved", "not-delivered", "forbidden", "primary", null, null, now, now, 0, null);
        _state.Operations[id] = op;
        var refs = job.ExternalOperationRefs.Concat([id]).ToArray();
        _state.Jobs[job.JobId] = Advance(job with { ExternalOperationRefs = refs }, job.Status, $"{kind}-reserved", $"{kind}-reserved", cancellation: job.Cancellation);
        AuditLocked(job.JobId, "external-reserved", new Dictionary<string, string> { ["operationId"] = id, ["kind"] = kind, ["capabilityContractDigest"] = _policy.Capability.Digest });
    }

    private bool BeginDispatchLocked(string operationId, string effectId)
    {
        var op = _state.Operations[operationId]; var job = CurrentJobLocked(op.JobId);
        var decision = EvaluateMutationLocked(effectId, job, op, "steward-runtime");
        if (decision != "Admitted")
        {
            var reason = $"mutation-admission:{decision}";
            _state.Jobs[job.JobId] = Advance(job, "blocked", "mutation-admission-rejected", reason, cancellation: job.Cancellation, blockedReason: reason);
            AuditLocked(job.JobId, "mutation-admission-rejected", new Dictionary<string, string> { ["operationId"] = operationId, ["effect"] = effectId, ["disposition"] = decision });
            return false;
        }
        var decisionRef = $"admission-{Guid.NewGuid():N}";
        _state.Operations[operationId] = op with { State = "dispatching", Delivery = "delivery-unknown", RetryDisposition = "reconcile-first", ObservedAt = _clock.UtcNow, MutationDecisionRef = decisionRef };
        var status = op.OperationKind == "cancel" ? "cancelling" : "reconciling";
        var cancellation = op.OperationKind == "cancel" ? "reconciling" : job.Cancellation;
        _state.Jobs[job.JobId] = Advance(job, status, $"{op.OperationKind}-dispatch-started", $"{op.OperationKind}-dispatch-started", cancellation: cancellation);
        AuditLocked(job.JobId, "mutation-admitted", new Dictionary<string, string> { ["operationId"] = operationId, ["effect"] = effectId, ["decisionRef"] = decisionRef });
        return true;
    }

    private string EvaluateMutationLocked(string effectId, StewardSeedJob job, StewardOperation? operation, string actualSource)
    {
        if (!_policy.Effects.TryGetValue(effectId, out var effect)) return "CapabilityUnavailable";
        if (!IsCurrentLocked(job)) return "LostAuthority";
        if (Terminal.Contains(job.Status) || job.Cancellation is "requested" or "fenced" or "reconciling") return "LostAuthority";
        if (!string.Equals(actualSource, effect.AuthoritySource, StringComparison.Ordinal)) return "LostAuthority";
        if (effect.LeaseRequired)
        {
            var expectedOwner = $"steward-runtime:{job.AttemptId}";
            if (job.Lease is null || job.Lease.Owner != expectedOwner || job.Lease.FencingToken != job.Generation || job.Lease.ExpiresAt <= _clock.UtcNow)
                return "LostAuthority";
        }
        if (effect.CandidateRequired && string.IsNullOrWhiteSpace(job.Candidate.Digest)) return "StaleCandidate";
        if (job.DeadlineAt - _clock.UtcNow < TimeSpan.FromMilliseconds(effect.MinimumBudgetMs)) return "BudgetUnavailable";
        if (effect.DurableOperationRequired)
        {
            if (operation is null || operation.State != "reserved" || operation.Delivery != "not-delivered") return "ReconciliationRequired";
            if (operation.JobId != job.JobId || operation.Generation != job.Generation || operation.AttemptId != job.AttemptId || operation.JobVersion != job.Version)
                return "LostAuthority";
            if (operation.CandidateDigest != job.Candidate.Digest) return "StaleCandidate";
            if (operation.CapabilityIdentity != effect.CapabilityRef || operation.CapabilityIdentity != _policy.Capability.Id
                || operation.CapabilityContractDigest != _policy.Capability.Digest) return "CapabilityUnavailable";
            var target = $"target:{job.Subject.Id}:{job.Subject.Revision ?? "none"}";
            if (operation.TargetIdentity != target) return "LostAuthority";
        }
        return "Admitted";
    }

'''
text = replace_regex(text, r"    private void ReserveOperationLocked\(StewardSeedJob job, string kind, string\? submitOperationId = null\)\n.*?(?=    private void BindDispatchLocked)", reserve_and_begin, ".NET mutation gate implementation")

promote = '''    private void PromoteOrBlockLocked(StewardSeedJob job, StewardOperation operation, JsonElement payload)
    {
        var added = false;
        if (!payload.TryGetProperty("observation", out var observation)
            || !observation.TryGetProperty("producerId", out var producerIdElement)
            || !observation.TryGetProperty("authorityClass", out var authorityElement)
            || !observation.TryGetProperty("observationGrade", out var gradeElement)
            || !observation.TryGetProperty("binding", out var bindingElement)
            || !observation.TryGetProperty("coverage", out var coverageElement))
        {
            BlockObservationLocked(job); return;
        }
        var producerId = producerIdElement.GetString() ?? string.Empty;
        if (!string.Equals(producerId, _provider.ProducerId, StringComparison.Ordinal) || !_policy.Producers.TryGetValue(producerId, out var producer))
        {
            BlockObservationLocked(job); return;
        }
        var claimedAuthority = authorityElement.GetString() ?? string.Empty;
        if (!AuthorityRank.TryGetValue(claimedAuthority, out var claimedRank) || !AuthorityRank.TryGetValue(producer.AuthorityCeiling, out var ceilingRank))
        {
            BlockObservationLocked(job); return;
        }
        var actualAuthority = AuthorityRank.First(item => item.Value == Math.Min(claimedRank, ceilingRank)).Key;
        var observedSatisfied = bindingElement.GetProperty("satisfied").EnumerateArray().Select(item => item.GetString()!).ToHashSet(StringComparer.Ordinal);
        if (operation.CandidateDigest == job.Candidate.Digest) observedSatisfied.Add("candidate");
        var requiredCoverage = coverageElement.GetProperty("required").GetInt32();
        var observedCoverage = coverageElement.GetProperty("observed").GetInt32();
        if (requiredCoverage < 1 || observedCoverage < 0 || observedCoverage > requiredCoverage) { BlockObservationLocked(job); return; }
        var coverageState = observedCoverage >= requiredCoverage ? "complete" : observedCoverage > 0 ? "partial" : "unknown";
        foreach (var req in _policy.Requirements)
        {
            if (req.ApprovedProducers.Count > 0 && !req.ApprovedProducers.Contains(producerId)) continue;
            var observed = _clock.UtcNow; var id = $"evidence-{Guid.NewGuid():N}";
            var satisfied = req.BindingRequirements.Where(observedSatisfied.Contains).ToArray();
            var bindingStatus = req.BindingRequirements.All(observedSatisfied.Contains) ? "complete" : satisfied.Length > 0 ? "partial" : "unknown";
            var binding = new StewardBinding(req.BindingRequirements, satisfied, bindingStatus);
            var evidence = new StewardEvidence(id, job.JobId, job.LineageId, job.Generation, job.Subject, job.Candidate, req.Id, req.CanonicalClaim,
                req.EvidenceClass, gradeElement.GetString() ?? "unknown", actualAuthority, producerId, _policy.RecipeId, binding,
                new StewardCoverage(coverageState, requiredCoverage, observedCoverage), observed, observed.AddSeconds(req.FreshnessSeconds), Digest(payload));
            _state.Evidence[id] = evidence; job = job with { EvidenceRefs = job.EvidenceRefs.Concat([id]).ToArray() }; added = true;
            AuditLocked(job.JobId, "evidence-persisted", new Dictionary<string, string> { ["evidenceId"] = id, ["claimId"] = req.CanonicalClaim,
                ["authorityClass"] = actualAuthority, ["bindingStatus"] = bindingStatus, ["coverageState"] = coverageState });
        }
        _state.Jobs[job.JobId] = added ? Advance(job, "finalizing", "evidence-persisted", "evidence-persisted", cancellation: job.Cancellation)
            : Advance(job, "blocked", "blocked", "blocked:terminal-observation-insufficient-authority", cancellation: job.Cancellation, blockedReason: "terminal-observation-insufficient-authority");
        if (!added) AuditLocked(job.JobId, "blocked", new Dictionary<string, string> { ["reason"] = "terminal-observation-insufficient-authority" });
    }

    private void BlockObservationLocked(StewardSeedJob job)
    {
        _state.Jobs[job.JobId] = Advance(job, "blocked", "blocked", "blocked:terminal-observation-insufficient-authority", cancellation: job.Cancellation, blockedReason: "terminal-observation-insufficient-authority");
        AuditLocked(job.JobId, "blocked", new Dictionary<string, string> { ["reason"] = "terminal-observation-insufficient-authority" });
    }

'''
text = replace_regex(text, r"    private void PromoteOrBlockLocked\(StewardSeedJob job, JsonElement payload\)\n.*?(?=    private StewardCompletionEvaluation EvaluateCompletionLocked)", promote, ".NET observation-derived evidence")

text = replace_once(
    text,
    "        var handoff = CreateHandoff(job, completion);\n        if (_faults.Trip(\"before-terminal-publication\")) return;",
    "        var publicationAdmission = EvaluateMutationLocked(\"terminal-publication\", job, null, \"completion-gate\");\n        if (publicationAdmission != \"Admitted\")\n        {\n            var reason = $\"mutation-admission:{publicationAdmission}\";\n            _state.Jobs[job.JobId] = Advance(job, \"blocked\", \"mutation-admission-rejected\", reason, cancellation: job.Cancellation, blockedReason: reason);\n            AuditLocked(job.JobId, \"mutation-admission-rejected\", new Dictionary<string, string> { [\"effect\"] = \"terminal-publication\", [\"disposition\"] = publicationAdmission });\n            return;\n        }\n        var publicationDecisionRef = $\"admission-{Guid.NewGuid():N}\";\n        var handoff = CreateHandoff(job, completion);\n        if (_faults.Trip(\"before-terminal-publication\")) return;",
    ".NET publication admission",
)
text = replace_once(
    text,
    '        AuditLocked(job.JobId, "handoff-sealed", new Dictionary<string, string> { ["digest"] = handoff.Digest, ["candidate"] = handoff.Candidate.Digest });',
    '        AuditLocked(job.JobId, "handoff-sealed", new Dictionary<string, string> { ["digest"] = handoff.Digest, ["candidate"] = handoff.Candidate.Digest, ["mutationDecisionRef"] = publicationDecisionRef });',
    ".NET publication decision audit",
)
text = replace_once(
    text,
    "    private StewardSeedJob Advance(StewardSeedJob job, string status, string stage, string marker, string cancellation, string? blockedReason = null) => job with { Version = job.Version + 1, Status = status, Stage = stage, Cancellation = cancellation, BlockedReason = blockedReason, UpdatedAt = _clock.UtcNow, HeartbeatAt = _clock.UtcNow, ProgressAt = _clock.UtcNow, ProgressRevision = job.ProgressRevision + 1, ProgressMarker = marker };",
    "    private StewardSeedJob Advance(StewardSeedJob job, string status, string stage, string marker, string cancellation, string? blockedReason = null) => job with { Version = job.Version + 1, Status = status, Stage = stage, Cancellation = cancellation, BlockedReason = blockedReason, Lease = Terminal.Contains(status) ? null : job.Lease, UpdatedAt = _clock.UtcNow, HeartbeatAt = _clock.UtcNow, ProgressAt = _clock.UtcNow, ProgressRevision = job.ProgressRevision + 1, ProgressMarker = marker };",
    ".NET terminal lease release",
)
text = replace_once(
    text,
    '        catch (JsonException) { var quarantine = _snapshotPath + $".corrupt-{DateTimeOffset.UtcNow:yyyyMMddHHmmssfff}"; File.Move(_snapshotPath, quarantine); return new(); }',
    '        catch (JsonException exc) { var quarantine = _snapshotPath + $".corrupt-{DateTimeOffset.UtcNow:yyyyMMddHHmmssfff}"; File.Move(_snapshotPath, quarantine); throw new InvalidDataException($"STORE_CORRUPT / OPERATOR_RECOVERY_REQUIRED: canonical snapshot quarantined at {quarantine}", exc); }',
    ".NET corrupt snapshot fail closed",
)
write(path, text)

# ---------------------------------------------------------------------------
# Repository tests: broaden validator + actual execution enforcement.
# ---------------------------------------------------------------------------
path = "tests/test_mcp_steward_architect.py"
text = read(path)
text = replace_once(
    text,
    '        "deadlineAt": "2026-09-12T00:15:00Z", "finalizationStartsAt": None, "lease": None, "cancellation": "none",',
    '        "deadlineAt": "2026-09-12T00:15:00Z", "finalizationStartsAt": None,\n        "lease": {"owner": "steward-runtime:a1", "fencingToken": 2, "expiresAt": "2026-09-12T00:15:00Z"}, "cancellation": "none",',
    "test job authoritative lease",
)
new_admission_test = '''def test_mutation_admission_fails_closed_on_authority_fences_capability_candidate_budget_and_ambiguity() -> None:
    generator, validator = _generator("gen_admission"), _validator("val_admission")
    docs = _docs(generator); job = _job(docs); receipt = _receipt(docs, job)
    authority = {
        "source": "steward-runtime", "principal": "steward-runtime:a1", "scope": "external-dispatch",
        "target": "target:repo:abc", "attemptId": "a1", "jobVersion": 1,
        "leaseOwner": "steward-runtime:a1", "leaseFencingToken": 2,
    }
    base = dict(effect_id="external-dispatch", mutation_policy=docs["steward_mutation_policy"], job=job,
                capability=docs["steward_upstream_capability"], current_job_id="j1", current_generation=2,
                current_attempt_id="a1", current_version=1, effective_authority=authority,
                remaining_budget_ms=5000, receipt=receipt, candidate=job["candidate"],
                now=datetime(2026, 9, 12, tzinfo=UTC))
    assert validator.evaluate_mutation_admission(**base)["disposition"] == "Admitted"
    cases = (
        ({"effective_authority": {**authority, "source": "other-authority"}}, "LostAuthority"),
        ({"effective_authority": {**authority, "leaseOwner": "other-owner"}}, "LostAuthority"),
        ({"effective_authority": {**authority, "leaseFencingToken": 1}}, "LostAuthority"),
        ({"current_attempt_id": "a2"}, "LostAuthority"),
        ({"current_version": 2}, "LostAuthority"),
        ({"candidate": {**job["candidate"], "digest": "sha256:" + "9" * 64}}, "StaleCandidate"),
        ({"remaining_budget_ms": 10}, "BudgetUnavailable"),
        ({"receipt": {**receipt, "state": "dispatching", "delivery": "delivery-unknown", "retryDisposition": "reconcile-first"}}, "ReconciliationRequired"),
    )
    for changes, expected in cases:
        assert validator.evaluate_mutation_admission(**{**base, **changes})["disposition"] == expected

    drift = json.loads(json.dumps(docs["steward_upstream_capability"]))
    drift["contract"]["revision"] = "2"
    identity = {key: drift["contract"][key] for key in ("source", "id", "revision")}
    import hashlib
    drift["contract"]["digest"] = "sha256:" + hashlib.sha256(
        json.dumps(identity, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    assert validator.evaluate_mutation_admission(**{**base, "capability": drift})["disposition"] == "CapabilityUnavailable"


def test_design_pack_rejects_unresolved_capability_profile_ref_and_producer_dimension_drift() -> None:
    generator, validator = _generator("gen_design_negative"), _validator("val_design_negative")
    docs = _docs(generator)
    mutation = json.loads(json.dumps(docs["steward_mutation_policy"]))
    mutation["effects"][0]["capability_ref"] = "missing:capability"
    findings = validator.validate_design_pack(
        profile=docs["steward_profile"], state_machine=docs["steward_state_machine"], mutation_policy=mutation,
        proof_recipe=docs["steward_proof_recipe"], acceptance=docs["steward_acceptance"],
        upstreams=[docs["steward_upstream_capability"]],
    )
    assert any("capability_ref must resolve" in item for item in findings)

    profile = json.loads(json.dumps(docs["steward_profile"])); profile["contracts"]["proof_recipe"] = "wrong-proof@1"
    findings = validator.validate_design_pack(
        profile=profile, state_machine=docs["steward_state_machine"], mutation_policy=docs["steward_mutation_policy"],
        proof_recipe=docs["steward_proof_recipe"], acceptance=docs["steward_acceptance"],
        upstreams=[docs["steward_upstream_capability"]],
    )
    assert any("profile contract proof_recipe" in item for item in findings)

    proof = json.loads(json.dumps(docs["steward_proof_recipe"])); proof["producers"][0]["subject_dimensions"] = []
    assert any("cannot observe required subject dimensions" in item for item in validator.validate_document("proof", proof))


def test_job_validator_rejects_timezone_less_nested_lease_expiry() -> None:
    generator, validator = _generator("gen_lease_timestamp"), _validator("val_lease_timestamp")
    job = _job(_docs(generator)); job["lease"]["expiresAt"] = "2026-09-12T00:15:00"
    assert any("lease.expiresAt" in item for item in validator.validate_document("job", job))

'''
text = replace_regex(
    text,
    r"def test_mutation_admission_fails_closed_on_authority_candidate_budget_and_ambiguity\(\) -> None:\n.*?(?=def test_capability_truth_is_not_health)",
    new_admission_test,
    "expanded mutation/design/lease tests",
)

# Runtime constructor call sites load mutation policy explicitly.
text = replace_once(
    text,
    '    proof = json.loads((destination / "src/sample_steward/steward_proof_recipe.json").read_text(encoding="utf-8"))\n    upstream = json.loads((destination / "src/sample_steward/steward_upstream_capability.json").read_text(encoding="utf-8"))',
    '    proof = json.loads((destination / "src/sample_steward/steward_proof_recipe.json").read_text(encoding="utf-8"))\n    mutation = json.loads((destination / "src/sample_steward/steward_mutation_policy.json").read_text(encoding="utf-8"))\n    upstream = json.loads((destination / "src/sample_steward/steward_upstream_capability.json").read_text(encoding="utf-8"))',
    "runtime test loads mutation policy",
)
text = text.replace("runtime_module.StewardStore(path, clock), profile, proof, upstream=upstream", "runtime_module.StewardStore(path, clock), profile, proof, mutation, upstream=upstream")
text = text.replace("runtime_module.StewardStore(cancel_path, clock), profile, proof, upstream=upstream", "runtime_module.StewardStore(cancel_path, clock), profile, proof, mutation, upstream=upstream")
text = text.replace("runtime_module.StewardStore(tmp_path / \"blocked.db\", clock), profile, proof, upstream=upstream", "runtime_module.StewardStore(tmp_path / \"blocked.db\", clock), profile, proof, mutation, upstream=upstream")
write(path, text)

# Dedicated runtime-security regressions cover real-path zero-side-effect admission,
# observation-derived evidence, capability drift, and missing design contracts.
path = "tests/test_mcp_steward_runtime_security.py"
text = read(path)
text = text.replace(
    "def _generated_runtime(tmp_path: Path) -> tuple[ModuleType, dict[str, Any], dict[str, Any], dict[str, Any]]:",
    "def _generated_runtime(tmp_path: Path) -> tuple[ModuleType, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:",
)
text = replace_once(
    text,
    '    proof = json.loads((destination / "src/security_steward/steward_proof_recipe.json").read_text(encoding="utf-8"))\n    upstream = json.loads(',
    '    proof = json.loads((destination / "src/security_steward/steward_proof_recipe.json").read_text(encoding="utf-8"))\n    mutation = json.loads((destination / "src/security_steward/steward_mutation_policy.json").read_text(encoding="utf-8"))\n    upstream = json.loads(',
    "security helper mutation load",
)
text = replace_once(text, "    return runtime, profile, proof, upstream", "    return runtime, profile, proof, mutation, upstream", "security helper return mutation")
text = text.replace("runtime, profile, proof, upstream = _generated_runtime(tmp_path)", "runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)")
text = text.replace("runtime, _, _, _ = _generated_runtime(tmp_path)", "runtime, _, _, _, _ = _generated_runtime(tmp_path)")
text = text.replace("runtime.StewardRuntime(store, profile, proof, upstream=upstream)", "runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream)")
text = text.replace("        proof,\n        upstream=upstream,", "        proof,\n        mutation,\n        upstream=upstream,")

runtime_regressions = '''

def test_real_dispatch_gate_rejects_capability_drift_and_stale_fence_with_zero_provider_calls(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))

    class CountingProvider(runtime.FakeProvider):
        def __init__(self) -> None:
            self.dispatch_count = 0
        def dispatch(self, operation_id: str, subject: dict[str, Any]) -> str:
            self.dispatch_count += 1
            return super().dispatch(operation_id, subject)

    provider = CountingProvider(); store = runtime.StewardStore(tmp_path / "capability-drift.db", clock)
    steward = runtime.StewardRuntime(store, profile, proof, mutation, upstream=upstream, provider=provider)
    job_id = steward.submit("repo", "abc", "cap-drift")["jobId"]
    assert steward.run_once() is True  # durable reservation only
    drift = json.loads(json.dumps(upstream)); drift["contract"]["revision"] = "2"
    identity = {key: drift["contract"][key] for key in ("source", "id", "revision")}
    import hashlib
    drift["contract"]["digest"] = "sha256:" + hashlib.sha256(json.dumps(identity, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
    steward.upstream = drift
    assert steward.run_once() is True
    assert provider.dispatch_count == 0
    assert steward.status(job_id)["status"] == "blocked"

    provider2 = CountingProvider(); store2 = runtime.StewardStore(tmp_path / "stale-fence.db", clock)
    steward2 = runtime.StewardRuntime(store2, profile, proof, mutation, upstream=upstream, provider=provider2)
    job2 = steward2.submit("repo2", "abc", "stale-fence")["jobId"]
    steward2.run_once()
    with store2._write() as db:
        db.execute("UPDATE steward_jobs SET attempt_id='new-attempt',version=version+1 WHERE job_id=?", (job2,))
    steward2.run_once()
    assert provider2.dispatch_count == 0
    assert steward2.status(job2)["status"] == "blocked"


def test_evidence_promotion_uses_observed_binding_coverage_and_authority_without_minting(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    clock = runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC))

    class PartialProvider(runtime.FakeProvider):
        def poll(self, remote_handle: str, subject: dict[str, Any]) -> dict[str, Any]:
            payload = super().poll(remote_handle, subject)
            payload["observation"]["authorityClass"] = "advisory"
            payload["observation"]["binding"]["satisfied"] = []
            payload["observation"]["coverage"] = {"required": 2, "observed": 1}
            return payload

    steward = runtime.StewardRuntime(
        runtime.StewardStore(tmp_path / "observed-evidence.db", clock), profile, proof, mutation,
        upstream=upstream, provider=PartialProvider(),
    )
    job_id = steward.submit("repo", "abc", "observed-evidence")["jobId"]
    for _ in range(8):
        steward.run_once()
        if steward.status(job_id)["status"] == "blocked":
            break
    evidence = steward.get(job_id)["evidence"]
    assert len(evidence) == 1
    assert evidence[0]["authorityClass"] == "advisory"
    assert evidence[0]["binding"]["status"] == "partial"
    assert evidence[0]["binding"]["satisfied"] == ["candidate"]
    assert evidence[0]["coverage"] == {"state": "partial", "required": 2, "observed": 1}
    assert steward.status(job_id)["status"] == "blocked"


def test_runtime_requires_explicit_reviewed_mutation_policy_and_upstream(tmp_path: Path) -> None:
    runtime, profile, proof, mutation, upstream = _generated_runtime(tmp_path)
    store = runtime.StewardStore(tmp_path / "missing-design.db", runtime.FakeClock(datetime(2026, 9, 13, tzinfo=UTC)))
    with pytest.raises((TypeError, ValueError)):
        runtime.StewardRuntime(store, profile, proof, mutation)  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="explicit reviewed upstream"):
        runtime.StewardRuntime(store, profile, proof, None, upstream=upstream)  # type: ignore[arg-type]

'''
text += runtime_regressions
write(path, text)

# Path confinement regression.
path = "tests/test_mcp_steward_architect.py"
text = read(path)
text += '''

def test_generator_rejects_nested_symlink_destination(tmp_path: Path) -> None:
    generator = _generator("gen_symlink_confinement")
    outside = tmp_path / "outside"; outside.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this platform")
    with pytest.raises(ValueError, match="symlinks|reparse"):
        generator.generate_project(
            linked / "project", language="python", identity="safe_steward", server_name="Safe Steward",
            steward_id="safe", profile="verification",
        )
    assert not (outside / "project").exists()
'''
write(path, text)

# ---------------------------------------------------------------------------
# .NET exact-artifact smoke: capability provenance and corrupt-store fail closed.
# ---------------------------------------------------------------------------
path = "skills/mcp-steward-architect/tools/steward-templates/dotnet/SmokeProgram.cs.template"
text = read(path)
text = replace_once(
    text,
    '            if (result.Handoff is null || result.Handoff.Candidate != result.Job.Candidate || !StewardSeedRuntime.VerifyHandoffDigest(result.Handoff)) throw new InvalidOperationException("Candidate-bound handoff verification failed.");',
    '            if (result.Handoff is null || result.Handoff.Candidate != result.Job.Candidate || !StewardSeedRuntime.VerifyHandoffDigest(result.Handoff)) throw new InvalidOperationException("Candidate-bound handoff verification failed.");\n            using var upstreamDoc = JsonDocument.Parse(File.ReadAllText(Path.GetFullPath("src/__NAMESPACE__.Mcp.Server/steward_upstream_capability.json")));\n            var expectedCapability = upstreamDoc.RootElement.GetProperty("capability_id").GetString();\n            var expectedDigest = upstreamDoc.RootElement.GetProperty("contract").GetProperty("digest").GetString();\n            var submitOperation = result.Operations.Single(item => item.OperationKind == "submit");\n            if (submitOperation.CapabilityIdentity != expectedCapability || submitOperation.CapabilityContractDigest != expectedDigest || string.IsNullOrWhiteSpace(submitOperation.MutationDecisionRef))\n                throw new InvalidOperationException("Mutation receipt is not bound to the reviewed capability contract/admission decision.");',
    ".NET smoke capability provenance",
)
corrupt_test = '''
        var corruptRoot = Path.Combine(root, "corrupt"); Directory.CreateDirectory(corruptRoot);
        File.WriteAllText(Path.Combine(corruptRoot, "steward-state.json"), "{ definitely-not-json");
        var corruptProvider = new CountingSeedProvider(); var corruptRejected = false;
        try { using var _ = new StewardSeedRuntime(corruptRoot, clock, corruptProvider, new SeedFaultInjector(), profile, proof); }
        catch (InvalidDataException exc) when (exc.Message.Contains("STORE_CORRUPT", StringComparison.Ordinal)) { corruptRejected = true; }
        if (!corruptRejected || corruptProvider.DispatchCount != 0) throw new InvalidOperationException("Corrupt canonical state did not fail closed before external mutation.");
'''
text = replace_once(text, "\n        var blockedProvider = new UnapprovedSeedProvider();", corrupt_test + "\n        var blockedProvider = new UnapprovedSeedProvider();", ".NET corrupt-store smoke")
text = replace_once(
    text,
    '    public SeedPollResult Poll(string remoteHandle, StewardSubject subject) { PollCount++; return new(true, JsonSerializer.SerializeToElement(new { state = "completed", remoteHandle, subject, revision = "terminal-1" })); }',
    '    public SeedPollResult Poll(string remoteHandle, StewardSubject subject) { PollCount++; return new(true, JsonSerializer.SerializeToElement(new { state = "completed", remoteHandle, subject, revision = "terminal-1", observation = new { producerId = ProducerId, observationGrade = "observed", authorityClass = "observed", binding = new { satisfied = new[] { "target" } }, coverage = new { required = 1, observed = 1 } } })); }',
    ".NET counting provider observation",
)
text = replace_once(
    text,
    '    public SeedPollResult Poll(string remoteHandle, StewardSubject subject) { PollCount++; return new(true, JsonSerializer.SerializeToElement(new { state = "completed", remoteHandle, subject })); }',
    '    public SeedPollResult Poll(string remoteHandle, StewardSubject subject) { PollCount++; return new(true, JsonSerializer.SerializeToElement(new { state = "completed", remoteHandle, subject, observation = new { producerId = ProducerId, observationGrade = "observed", authorityClass = "observed", binding = new { satisfied = new[] { "target" } }, coverage = new { required = 1, observed = 1 } } })); }',
    ".NET unapproved provider observation",
)
write(path, text)

print("Steward v3 executable enforcement patch applied")
