#!/usr/bin/env python3
"""Apply final reviewed integration fixes and parameterize NuGet project identities."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old in text:
        if text.count(old) != 1:
            raise RuntimeError(f"{path}: expected one replacement")
        path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
        return
    if new not in text:
        raise RuntimeError(f"{path}: neither reviewed old nor new fragment is present")


generator = ROOT / "skills/mcp-server-architect/tools/generate_dotnet_server.py"
replace_once(
    generator,
    '    return value.replace("__NAMESPACE__", namespace).replace("__SERVER_NAME__", server_name)\n',
    '    return (\n'
    '        value.replace("__NAMESPACE_LOWER__", namespace.lower())\n'
    '        .replace("__NAMESPACE__", namespace)\n'
    '        .replace("__SERVER_NAME__", server_name)\n'
    '    )\n',
)

generator_tests = ROOT / "tests/test_mcp_dotnet_generator.py"
replace_once(
    generator_tests,
    '    assert "<RestorePackagesWithLockFile>true</RestorePackagesWithLockFile>" in build_props\n\n'
    '    packages = (target / "Directory.Packages.props").read_text(encoding="utf-8")\n',
    '    assert "<RestorePackagesWithLockFile>true</RestorePackagesWithLockFile>" in build_props\n\n'
    '    server_lock = (target / "src/Acme.Mcp.Server/packages.lock.json").read_text(encoding="utf-8")\n'
    '    smoke_lock = (target / "tests/Acme.Mcp.Smoke/packages.lock.json").read_text(encoding="utf-8")\n'
    '    for lock in (server_lock, smoke_lock):\n'
    '        assert "Locked" not in lock\n'
    '        assert "locked.mcp." not in lock\n'
    '        assert "__NAMESPACE" not in lock\n'
    '    assert "acme.mcp.domain" in server_lock\n'
    '    assert "acme.mcp.server" in smoke_lock\n\n'
    '    packages = (target / "Directory.Packages.props").read_text(encoding="utf-8")\n',
)

decision_tests = ROOT / "tests/test_decision_engine.py"
replace_once(
    decision_tests,
    '''def test_retry_requires_valid_attempt_and_positive_non_conflicting_signals() -> None:\n    engine = load_engine()\n    assert engine.should_retry(\n        error_code="TIMEOUT", attempt=0, operation_idempotent=True, manifest={"retryable": True}\n    )\n    assert engine.should_retry(\n        error_code="TIMEOUT", attempt=0, operation_idempotent=True, response_retryable=True\n    )\n    for attempt in (-1, True, 2):\n        assert not engine.should_retry(\n            error_code="TIMEOUT", attempt=attempt, operation_idempotent=True, manifest={"retryable": True}\n        )\n    for manifest in (None, {}, {"retryable": False}):\n        assert not engine.should_retry(\n            error_code="TIMEOUT", attempt=0, operation_idempotent=True, manifest=manifest\n        )\n    assert not engine.should_retry(\n        error_code="TIMEOUT",\n        attempt=0,\n        operation_idempotent=True,\n        manifest={"retryable": True},\n        response_retryable=False,\n    )\n    assert not engine.should_retry(\n        error_code="TIMEOUT",\n        attempt=0,\n        operation_idempotent=True,\n        manifest={"retryable": False},\n        response_retryable=True,\n    )\n''',
    '''def test_retry_requires_valid_attempt_and_positive_non_conflicting_signals() -> None:\n    engine = load_engine()\n    governed = {\n        "retryable": True,\n        "retryConditions": {\n            "eligibleErrors": ["TIMEOUT"],\n            "maxTotalAttempts": 2,\n            "backoff": {"initialMilliseconds": 100},\n            "requiresReconciliation": True,\n        },\n    }\n    assert engine.should_retry(\n        error_code="TIMEOUT",\n        attempt=0,\n        operation_idempotent=True,\n        manifest=governed,\n        reconciliation_succeeded=True,\n    )\n    assert engine.should_retry(\n        error_code="TIMEOUT", attempt=0, operation_idempotent=True, response_retryable=True\n    )\n    for attempt in (-1, True, 2):\n        assert not engine.should_retry(\n            error_code="TIMEOUT",\n            attempt=attempt,\n            operation_idempotent=True,\n            manifest=governed,\n            reconciliation_succeeded=True,\n        )\n    for manifest in (None, {}, {"retryable": False}, {"retryable": True}):\n        assert not engine.should_retry(\n            error_code="TIMEOUT", attempt=0, operation_idempotent=True, manifest=manifest\n        )\n    assert not engine.should_retry(\n        error_code="TIMEOUT",\n        attempt=0,\n        operation_idempotent=True,\n        manifest=governed,\n        response_retryable=False,\n        reconciliation_succeeded=True,\n    )\n    assert not engine.should_retry(\n        error_code="TIMEOUT",\n        attempt=0,\n        operation_idempotent=True,\n        manifest={"retryable": False},\n        response_retryable=True,\n    )\n''',
)
replace_once(
    decision_tests,
    '''def test_conflict_retry_requires_refreshed_precondition() -> None:\n    engine = load_engine()\n    kwargs = {\n        "error_code": "CONFLICT",\n        "attempt": 0,\n        "operation_idempotent": True,\n        "manifest": {"retryable": True},\n    }\n    assert not engine.should_retry(**kwargs)\n    assert engine.should_retry(**kwargs, precondition_refreshed=True)\n''',
    '''def test_conflict_retry_requires_refreshed_precondition() -> None:\n    engine = load_engine()\n    kwargs = {\n        "error_code": "CONFLICT",\n        "attempt": 0,\n        "operation_idempotent": True,\n        "manifest": {\n            "retryable": True,\n            "retryConditions": {\n                "eligibleErrors": ["CONFLICT"],\n                "maxTotalAttempts": 2,\n                "backoff": {"initialMilliseconds": 100},\n                "requiresReconciliation": False,\n            },\n        },\n    }\n    assert not engine.should_retry(**kwargs)\n    assert engine.should_retry(**kwargs, precondition_refreshed=True)\n''',
)

locks = (
    ROOT
    / "skills/mcp-server-architect/tools/dotnet-template/src/"
    "__NAMESPACE__.Mcp.Server/packages.lock.json.template",
    ROOT
    / "skills/mcp-server-architect/tools/dotnet-template/tests/"
    "__NAMESPACE__.Mcp.Smoke/packages.lock.json.template",
)
for path in locks:
    content = path.read_text(encoding="utf-8")
    rendered = content.replace("locked.mcp.", "__NAMESPACE_LOWER__.mcp.")
    rendered = rendered.replace("Locked", "__NAMESPACE__")
    if "locked.mcp." in rendered or "Locked" in rendered:
        raise RuntimeError(f"unparameterized lock identity remains in {path}")
    path.write_text(rendered, encoding="utf-8", newline="\n")
