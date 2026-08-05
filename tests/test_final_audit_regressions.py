"""Regressions from final independent audits of the governed release."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills/agents-md-architect/tools"
CONTRACTS = ROOT / "contracts"
SCRIPTS = ROOT / "scripts"
DOTNET_TEMPLATE = ROOT / "skills/mcp-server-architect/tools/dotnet-template"
for candidate in (TOOLS, CONTRACTS, SCRIPTS):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agents_md_codex_platform as codex_platform  # noqa: E402
import agents_md_parse as parser  # noqa: E402
import agents_md_shell_evidence_impl as shell_impl  # noqa: E402
import confined_io  # noqa: E402
from quality_targets import TYPE_PATHS  # noqa: E402


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_parser_no_longer_exposes_the_legacy_reader() -> None:
    assert not hasattr(parser, "read_utf8_bounded")


def test_inline_code_closer_requires_an_exact_backtick_run() -> None:
    line = "Use `literal ``missing.md`` text` as an example."
    assert list(parser.iter_references([(1, line)])) == []


def test_unmatched_backtick_run_does_not_hide_a_later_code_span() -> None:
    line = "Read ``unfinished and then `missing.md`."
    assert list(parser.iter_references([(1, line)])) == [(1, "missing.md")]


def test_recursive_yaml_alias_fails_closed_without_recursion_error() -> None:
    text = "jobs: &jobs\n  loop: *jobs\n"
    assert shell_impl._yaml_syntax_error(text) == shell_impl.INVALID_YAML_MESSAGE
    assert shell_impl._extract_yaml_invocations(".github/workflows/ci.yml", text) == set()


def test_shell_implementation_preserves_argv_without_wrapper_rebinding() -> None:
    assert shell_impl._extract_shell_invocations("python 'scripts/full gate.py'") == {"python 'scripts/full gate.py'"}
    wrapper = (TOOLS / "agents_md_shell_evidence.py").read_text(encoding="utf-8")
    assert "_impl._normalize_invocation =" not in wrapper


def test_codex_fallback_rejects_intermediate_directory_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    outside = tmp_path / "outside"
    write(repository / "nested/AGENTS.md", "inside")
    write(outside / "AGENTS.md", "outside secret")

    probe = repository / "symlink-probe"
    try:
        probe.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlinks are unavailable: {error}")
    else:
        probe.unlink()

    target = (repository / "nested/AGENTS.md").absolute()
    real_open_stable = confined_io.open_stable
    replaced = False

    def replacing_open_stable(
        path: Path,
        flags: int,
        *,
        component_nofollow: bool | None = None,
    ) -> tuple[int, object]:
        nonlocal replaced
        if not replaced and Path(path).absolute() == target:
            replaced = True
            (repository / "nested").rename(repository / "nested-original")
            (repository / "nested").symlink_to(outside, target_is_directory=True)
        return real_open_stable(path, flags, component_nofollow=False)

    monkeypatch.setattr(confined_io, "open_stable", replacing_open_stable)
    findings = codex_platform._validate_codex_context(repository, (), 1024)

    assert replaced
    assert "input.read-error" in {finding.code for finding in findings}


def test_codex_context_budget_is_not_a_per_file_read_limit(tmp_path: Path) -> None:
    write(tmp_path / "AGENTS.md", "root")
    write(tmp_path / "packages/PROJECT_GUIDE.md", "nested fallback content")

    findings = codex_platform._validate_codex_context(tmp_path, ("PROJECT_GUIDE.md",), 20)
    codes = {finding.code for finding in findings}

    assert "platform.codex-context-budget" in codes
    assert "input.too-large" not in codes


def test_workflow_policy_impl_is_published_and_type_checked() -> None:
    implementation = "skills/ci-cd-architect/tools/check_github_actions_policy_impl.py"
    manifest = yaml.safe_load((ROOT / "skills/ci-cd-architect/manifest.yaml").read_text(encoding="utf-8"))
    assert "tools/check_github_actions_policy_impl.py" in manifest["required"]
    assert implementation in TYPE_PATHS


def test_dotnet_http_enforces_and_executes_loopback_origin_policy() -> None:
    program = (DOTNET_TEMPLATE / "src/__NAMESPACE__.Mcp.Server/Program.cs.template").read_text(encoding="utf-8")
    smoke = (DOTNET_TEMPLATE / "tests/__NAMESPACE__.Mcp.Smoke/Program.cs.template").read_text(encoding="utf-8")

    for token in (
        'request.Headers.TryGetValue("Origin"',
        "values.Count != 1",
        "origin.Port != expectedPort",
        "IPAddress.IsLoopback",
        "StatusCodes.Status403Forbidden",
    ):
        assert token in program
    assert program.index("IsAllowedOrigin(context.Request") < program.index("Headers.Authorization")

    assert '"Origin", "https://attacker.invalid"' in smoke
    assert "foreignOriginResponse.StatusCode != HttpStatusCode.Forbidden" in smoke


def test_dotnet_tool_attributes_and_manifests_share_canonical_names() -> None:
    manifests = (DOTNET_TEMPLATE / "src/__NAMESPACE__.Mcp.Server/CapabilityManifest.cs.template").read_text(
        encoding="utf-8"
    )
    tools = (DOTNET_TEMPLATE / "src/__NAMESPACE__.Mcp.Server/Tools.cs.template").read_text(encoding="utf-8")
    smoke = (DOTNET_TEMPLATE / "tests/__NAMESPACE__.Mcp.Smoke/Program.cs.template").read_text(encoding="utf-8")

    for constant in ("DescribeCapabilities", "ListItems", "PutItem"):
        assert f"Name = CapabilityNames.{constant}" in tools
        assert f"[CapabilityNames.{constant}]" in manifests
    assert "CapabilityNames.Registered" in manifests
    assert ".SetEquals(CapabilityNames.Registered)" in manifests

    # The public-client test deliberately keeps an independent expected catalog,
    # so a broken attribute/manifest projection cannot make all checks agree.
    for public_name in ("describe_capabilities", "list_items", "put_item"):
        assert f'"{public_name}"' in smoke
