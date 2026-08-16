"""Regressions from the post-.NET-migration review of PR #12."""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_python_generator_refuses_dangling_symlink_and_racing_target(
    tmp_path: Path,
) -> None:
    generator = _load(
        ROOT / "skills/mcp-server-architect/tools/generate_python_server.py",
        "post_review_python_generator",
    )

    outside = tmp_path / "outside"
    dangling = tmp_path / "dangling"
    dangling.symlink_to(outside, target_is_directory=True)
    try:
        generator.generate_project(dangling, "safe_mcp", "Safe MCP")
    except FileExistsError:
        pass
    else:
        raise AssertionError("dangling generation-target symlink was followed")
    assert not outside.exists()

    target = tmp_path / "racing"
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    failures: list[BaseException] = []

    def generate() -> None:
        try:
            barrier.wait(timeout=10)
            generator.generate_project(target, "safe_mcp", "Safe MCP")
            outcomes.append("created")
        except FileExistsError:
            outcomes.append("exists")
        except BaseException as exception:  # pragma: no cover - diagnostic path
            failures.append(exception)

    workers = [threading.Thread(target=generate) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=30)
    assert not failures
    assert sorted(outcomes) == ["created", "exists"]
    assert (target / "pyproject.toml").is_file()


def test_generated_http_uses_official_streamable_transport_not_custom_replay(
    tmp_path: Path,
) -> None:
    generator = _load(
        ROOT / "skills/mcp-server-architect/tools/generate_python_server.py",
        "post_review_python_generator_http",
    )
    target = tmp_path / "server"
    generator.generate_project(target, "safe_mcp", "Safe MCP")
    assert not (target / "src/safe_mcp/http.py").exists()
    source = (target / "src/safe_mcp/server.py").read_text(encoding="utf-8")
    assert "mcp.streamable_http_app(" in source
    assert "stateless_http=True" in source
    assert "legacy" not in source.casefold()


def test_consumer_rejects_empty_or_meta_only_response() -> None:
    engine = _load(
        ROOT / "skills/mcp-server-consumer/tools/decision_engine.py",
        "post_review_decision_engine",
    )
    for payload in ({}, {"_meta": {"request_id": "abc"}}):
        result = engine.handle_response(payload)
        assert result.success is False
        assert result.error_code == "MALFORMED_RESPONSE"

    explicit_empty = engine.handle_response({"success": True})
    assert explicit_empty.success is True
    protocol_empty = engine.handle_response({"isError": False, "content": []})
    assert protocol_empty.success is True


def _release_template() -> str:
    return (ROOT / "skills/ci-cd-architect/templates/dotnet-package.yml.template").read_text(encoding="utf-8")


def _semver_is_accepted(version: str) -> bool:
    source = _release_template()
    assignments = []
    for name in (
        "core_identifier",
        "prerelease_identifier",
        "build_identifier",
        "semver_regex",
    ):
        match = re.search(rf"^\s*{name}=.*$", source, re.M)
        assert match, name
        assignments.append(match.group(0).strip())
    bash = shutil.which("bash")
    assert bash is not None
    script = "\n".join(assignments)
    script += '\nnormalized_version="$1"\n'
    script += '[[ "$normalized_version" =~ $semver_regex ]]\n'
    return (
        subprocess.run(
            [bash, "-s", "--", version],
            input=script.encode("utf-8"),
            check=False,
        ).returncode
        == 0
    )


def test_dotnet_release_version_is_validated_and_passed_through_env() -> None:
    source = _release_template()
    assert "canonical SemVer 2.0" in source
    assert "PACKAGE_VERSION: ${{ steps.release.outputs.version }}" in source
    assert '-p:PackageVersion="$PACKAGE_VERSION"' in source
    assert "-p:PackageVersion=${{ steps.release.outputs.version }}" not in source
    assert '[[ ! "$normalized_version" =~ $semver_regex ]]' in source


def test_dotnet_release_semver_rejects_leading_zeroes_and_empty_identifiers() -> None:
    for version in (
        "0.0.0",
        "1.2.3",
        "1.2.3-alpha",
        "1.2.3-alpha.0",
        "1.2.3-0.3.7",
        "1.2.3-x.7.z.92+001",
        "1.2.3+001",
    ):
        assert _semver_is_accepted(version), version

    for version in (
        "01.2.3",
        "1.02.3",
        "1.2.03",
        "1.2.3-01",
        "1.2.3-alpha.01",
        "1.2.3-alpha..1",
        "1.2.3+build..1",
        "1.2",
        "1.2.3/evil",
        "1.2.3 alpha",
    ):
        assert not _semver_is_accepted(version), version


def test_target_authorization_precedes_network_resolution_in_normative_docs() -> None:
    transport = (ROOT / "skills/mcp-server-architect/references/transport-lifecycle-and-conformance.md").read_text(
        encoding="utf-8"
    )
    simulation = (ROOT / "skills/mcp-server-architect/references/dotnet-migration-simulation.md").read_text(
        encoding="utf-8"
    )

    assert "authorize the selector namespace or tenant before any discovery or lookup" in transport
    assert "failed preliminary authorization must produce no network-backed target probe" in transport
    assert "authorize its device namespace before discovery" in simulation
    assert "unauthorized selector and prove the resolver performs no network-backed discovery" in simulation
    assert "Authorization occurs after target resolution" not in transport


def test_dotnet_approval_capacity_check_is_serialized() -> None:
    source = (
        ROOT / "skills/mcp-server-architect/tools/dotnet-template/src/"
        "__NAMESPACE__.Mcp.Server/ApprovalRegistry.cs.template"
    ).read_text(encoding="utf-8")
    lock_index = source.index("lock (_gate)")
    count_index = source.index("_records.Count >= MaximumRecords")
    add_index = source.index("_records.TryAdd(token, record)")
    assert lock_index < count_index < add_index
    assert "while (true)" in source


def test_dotnet_smoke_rejects_unknown_mode_and_retries_probe_timeout() -> None:
    source = (
        ROOT / "skills/mcp-server-architect/tools/dotnet-template/tests/__NAMESPACE__.Mcp.Smoke/Program.cs.template"
    ).read_text(encoding="utf-8")
    assert 'args.Length == 2 && !string.Equals(args[1], "--http", StringComparison.Ordinal)' in source
    assert "if (args.Length == 2)" in source
    assert "args.Contains(" not in source
    assert "catch (HttpRequestException)" in source
    assert "catch (OperationCanceledException)" in source
