#!/usr/bin/env python3
"""One-shot exact-text fixup for generated Steward runtime templates."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOTNET = ROOT / "skills/mcp-steward-architect/tools/steward-templates/dotnet/StewardSeedRuntime.cs.template"
SMOKE = ROOT / "skills/mcp-steward-architect/tools/steward-templates/dotnet/SmokeProgram.cs.template"
PYTHON = ROOT / "skills/mcp-steward-architect/tools/steward-templates/python/steward_runtime.py.template"
PYTHON_TEST = ROOT / "skills/mcp-steward-architect/tools/steward-templates/python/test_steward_runtime.py.template"
REPO_TEST = ROOT / "tests/test_mcp_steward_architect.py"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"expected one match in {path}: {old[:100]!r}; got {text.count(old)}")
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


def main() -> None:
    # C#: collection expressions cannot target IReadOnlyDictionary directly.
    replace_once(
        DOTNET,
        '            AuditLocked(jobId, "cancel-requested", []);\n',
        '            AuditLocked(jobId, "cancel-requested", new Dictionary<string, string>());\n',
    )
    replace_once(
        DOTNET,
        '                AuditLocked(job.JobId, "cancelled", []);\n',
        '                AuditLocked(job.JobId, "cancelled", new Dictionary<string, string>());\n',
    )

    # C#: a new semantic generation atomically supersedes the previous non-terminal generation.
    replace_once(
        DOTNET,
        '''            var jobId = $"job-{Guid.NewGuid():N}";\n            var now = _clock.UtcNow;\n            var job = new StewardSeedJob(\n''',
        '''            var jobId = $"job-{Guid.NewGuid():N}";\n            var now = _clock.UtcNow;\n            if (lineage is not null &&\n                _state.Jobs.TryGetValue(lineage.CurrentJobId, out var previousJob) &&\n                !Terminal.Contains(previousJob.Status))\n            {\n                previousJob = previousJob with\n                {\n                    Version = previousJob.Version + 1,\n                    Status = "superseded",\n                    Stage = "superseded",\n                    UpdatedAt = now,\n                };\n                _state.Jobs[previousJob.JobId] = previousJob;\n                AuditLocked(previousJob.JobId, "superseded", new Dictionary<string, string>\n                {\n                    ["byJobId"] = jobId,\n                    ["generation"] = generation.ToString(System.Globalization.CultureInfo.InvariantCulture),\n                });\n            }\n            var job = new StewardSeedJob(\n''',
    )

    # C#: the named fault point must happen before evidence mutates durable/in-memory state.
    replace_once(
        DOTNET,
        '''        lock (_gate)\n        {\n            RequireCurrentLocked(action.Job);\n            PersistEvidenceLocked(action.Job, result.Payload);\n            _faults.Trip("before-result-persist");\n            SaveLocked();\n        }\n''',
        '''        lock (_gate)\n        {\n            RequireCurrentLocked(action.Job);\n            if (_faults.Trip("before-result-persist"))\n                return true;\n            PersistEvidenceLocked(action.Job, result.Payload);\n            SaveLocked();\n        }\n''',
    )

    # Python: bind lineage replacement and old-job terminalization in the same BEGIN IMMEDIATE transaction.
    replace_once(
        PYTHON,
        '''            lineage = db.execute("SELECT current_generation FROM steward_lineages WHERE lineage_id=?", (lineage_id,)).fetchone()\n            generation = 1 if lineage is None else int(lineage[0]) + 1\n            job_id, attempt_id = f"job-{uuid.uuid4().hex}", f"attempt-{uuid.uuid4().hex}"\n            db.execute("INSERT INTO steward_jobs VALUES(?,?,?,?,0,?,?,?,?,?,?,?)",\n''',
        '''            lineage = db.execute(\n                "SELECT current_generation,current_job_id FROM steward_lineages WHERE lineage_id=?",\n                (lineage_id,),\n            ).fetchone()\n            generation = 1 if lineage is None else int(lineage["current_generation"]) + 1\n            job_id, attempt_id = f"job-{uuid.uuid4().hex}", f"attempt-{uuid.uuid4().hex}"\n            if lineage is not None:\n                previous_job_id = str(lineage["current_job_id"])\n                superseded = db.execute(\n                    "UPDATE steward_jobs SET status='superseded',stage='superseded',version=version+1,updated_at=? "\n                    "WHERE job_id=? AND status NOT IN ('completed','completed-with-gaps','failed','cancelled','superseded')",\n                    (now, previous_job_id),\n                )\n                if superseded.rowcount:\n                    self._audit(\n                        db,\n                        previous_job_id,\n                        "superseded",\n                        {"byJobId": job_id, "generation": generation},\n                    )\n            db.execute("INSERT INTO steward_jobs VALUES(?,?,?,?,0,?,?,?,?,?,?,?)",\n''',
    )

    # Generated .NET smoke: prove supersession prevents stale work from starving the scheduler or publishing handoff.
    replace_once(
        SMOKE,
        '''            if (result.Handoff is null || !StewardSeedRuntime.VerifyHandoffDigest(result.Handoff))\n                throw new InvalidOperationException("Handoff digest did not bind canonical handoff content.");\n        }\n''',
        '''            if (result.Handoff is null || !StewardSeedRuntime.VerifyHandoffDigest(result.Handoff))\n                throw new InvalidOperationException("Handoff digest did not bind canonical handoff content.");\n        }\n\n        using (var current = new StewardSeedRuntime(\n            Path.Combine(root, "supersession"),\n            clock,\n            new FakeSeedProvider(),\n            new SeedFaultInjector(),\n            profile,\n            proof))\n        {\n            var stale = current.Submit("repo-2", "abc", "supersede-1");\n            current.RunOneDue();\n            current.RunOneDue();\n            var latest = current.Submit("repo-2", "abc", "supersede-2");\n            if (current.Status(stale.JobId).Status != "superseded")\n                throw new InvalidOperationException("Previous lineage generation was not superseded atomically.");\n            current.RecoverUntilIdle();\n            if (current.Status(latest.JobId).Status != "completed")\n                throw new InvalidOperationException("Current lineage generation was starved by stale work.");\n            if (current.Get(stale.JobId).Handoff is not null)\n                throw new InvalidOperationException("Superseded lineage generation published a terminal handoff.");\n        }\n''',
    )

    # Generated Python self-test covers the same cross-product invariant.
    python_extra = '''\n\ndef test_new_generation_supersedes_nonterminal_predecessor(tmp_path: Path) -> None:\n    profile, proof = _policy()\n    runtime = StewardRuntime(\n        StewardStore(tmp_path / "supersession.db", FakeClock(datetime(2026, 1, 1, tzinfo=UTC))),\n        profile,\n        proof,\n    )\n    stale = runtime.submit("repo-2", "abc", "supersede-1")\n    runtime.run_once()\n    runtime.run_once()\n    latest = runtime.submit("repo-2", "abc", "supersede-2")\n    assert runtime.status(stale["jobId"])["status"] == "superseded"\n    runtime.recover_until_idle()\n    assert runtime.status(latest["jobId"])["status"] == "completed"\n    assert runtime.get(stale["jobId"])["handoff"] is None\n'''
    text = PYTHON_TEST.read_text(encoding="utf-8")
    if "test_new_generation_supersedes_nonterminal_predecessor" in text:
        raise RuntimeError("Python supersession test already exists")
    PYTHON_TEST.write_text(text.rstrip() + python_extra + "\n", encoding="utf-8", newline="\n")

    # Repository regression executes the rendered Python runtime, not merely template text.
    replace_once(
        REPO_TEST,
        '''    assert result["handoff"]["digest"] == runtime_module.compute_handoff_digest(result["handoff"])\n\n    with pytest.raises(FileExistsError):\n''',
        '''    assert result["handoff"]["digest"] == runtime_module.compute_handoff_digest(result["handoff"])\n\n    stale = recovered.submit("repo-2", "abc", "supersede-1")\n    recovered.run_once()\n    recovered.run_once()\n    latest = recovered.submit("repo-2", "abc", "supersede-2")\n    assert recovered.status(stale["jobId"])["status"] == "superseded"\n    recovered.recover_until_idle()\n    assert recovered.status(latest["jobId"])["status"] == "completed"\n    assert recovered.get(stale["jobId"])["handoff"] is None\n\n    with pytest.raises(FileExistsError):\n''',
    )


if __name__ == "__main__":
    main()
