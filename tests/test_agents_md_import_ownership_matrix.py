"""Ownership-resolution matrix: one coordinate-frame contract across reference forms."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills" / "agents-md-architect" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from agents_md_gate_sources import classify_gate_sources  # noqa: E402
from discover_repository import discover  # noqa: E402

PIN = "0123456789abcdef0123456789abcdef01234567"
VENDOR_PIN = "abcdef0123456789abcdef0123456789abcdef01"


def _checkout(repository: str | None, alias: str) -> str:
    with_block = ""
    if repository:
        with_block += f"        with:\n          repository: {repository}\n          ref: {VENDOR_PIN}\n"
    if alias != ".":
        with_block += f"{'        with:\n' if not with_block else ''}          path: {alias}\n"
    return f"      - uses: actions/checkout@{PIN}\n{with_block}"


def _build(
    tmp_path: Path,
    *,
    pythonpath: str | None,
    working_directory: str | None = None,
    extra_checkout: str = "",
    symlink_helper: bool = False,
    vendor_lookalike: bool = False,
) -> None:
    helper = tmp_path / "lib" / "helper.py"
    helper.parent.mkdir(parents=True)
    helper.write_text("VALUE = 1\n", encoding="utf-8")
    if symlink_helper:
        target = tmp_path / "outside"
        target.mkdir()
        (target / "helper_target.py").write_text("VALUE = 3\n", encoding="utf-8")
        helper.unlink()
        try:
            helper.symlink_to(target / "helper_target.py")
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"symlink creation unavailable: {exc}")
    if vendor_lookalike:
        lookalike = tmp_path / "vendor" / "helper.py"
        lookalike.parent.mkdir(parents=True)
        lookalike.write_text("EXTERNAL = 1\n", encoding="utf-8")
    (tmp_path / "entry.py").write_text("import helper\n", encoding="utf-8")
    steps = [_checkout(None, "."), extra_checkout]
    if working_directory:
        steps.append(_checkout(None, working_directory))
    env = f"        env:\n          PYTHONPATH: {pythonpath}\n" if pythonpath else ""
    cwd = f"        working-directory: {working_directory}\n" if working_directory else ""
    steps.append(f"      - name: invoke\n{cwd}{env}        run: python entry.py\n")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n" + "".join(steps),
        encoding="utf-8",
    )


def _paths(inventory) -> set[str]:
    return {source.path for source in inventory.sources}


@pytest.mark.parametrize(
    ("pythonpath", "working_directory"),
    [
        ("$GITHUB_WORKSPACE/candidate/lib", "candidate"),
        ("$PWD/lib", "candidate"),
        ("lib", "candidate"),
        ("lib", None),
    ],
)
def test_local_owner_includes_candidate_libraries_across_root_forms(
    pythonpath: str,
    working_directory: str | None,
    tmp_path: Path,
) -> None:
    _build(tmp_path, pythonpath=pythonpath, working_directory=working_directory)
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    assert "lib/helper.py" in _paths(inventory)
    assert not inventory.issues


def test_absolute_root_inside_candidate_is_owned_by_candidate(tmp_path: Path) -> None:
    """F12: absolute PYTHONPATH inside the audited checkout resolves as candidate content."""
    _build(
        tmp_path,
        pythonpath=str(tmp_path.resolve() / "candidate" / "lib"),
        working_directory="candidate",
        extra_checkout=_checkout("example/authority", "."),
    )
    (tmp_path / "candidate" / "lib").mkdir(parents=True)
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    assert "lib/helper.py" in _paths(inventory)
    assert not any(source.path.startswith("external:") and "helper" in source.path for source in inventory.sources)
    assert not inventory.issues


def test_external_owner_excludes_vendor_module_by_identity(tmp_path: Path) -> None:
    _build(
        tmp_path,
        pythonpath="$GITHUB_WORKSPACE/vendor",
        extra_checkout=_checkout("example/vendor", "vendor"),
        vendor_lookalike=True,
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    assert "external:example/vendor@" + VENDOR_PIN + "/helper.py" in _paths(inventory)
    assert not any(source.path == "vendor/helper.py" and source.counted for source in inventory.sources)
    assert not inventory.issues


def test_symlinked_helper_reports_incomplete_inventory(tmp_path: Path) -> None:
    _build(tmp_path, pythonpath="lib", symlink_helper=True)
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    assert any("symlink" in issue for issue in inventory.issues)
    assert not any(source.path == "helper.py" and source.counted for source in inventory.sources)


def test_symlinked_module_entrypoint_reports_incomplete_inventory(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "entry_target.py").write_text("VALUE = 1\n", encoding="utf-8")
    try:
        (tmp_path / "entry.py").symlink_to(outside / "entry_target.py")
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n      - run: python -m entry\n",
        encoding="utf-8",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    assert any("invoked module 'entry' not found" in issue or "symlink" in issue for issue in inventory.issues)
    assert not any(source.path == "entry.py" and source.counted for source in inventory.sources)


def test_legitimate_module_entrypoint_is_not_reported_as_symlink(tmp_path: Path) -> None:
    (tmp_path / "entry.py").write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n      - run: python -m entry\n",
        encoding="utf-8",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    row = next(source for source in inventory.sources if source.path == "entry.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert not inventory.issues


def test_same_path_in_different_job_checkout_states_keeps_both_identities(tmp_path: Path) -> None:
    helper = tmp_path / "lib" / "helper.py"
    helper.parent.mkdir(parents=True)
    helper.write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "entry.py").write_text("import helper\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  local:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@" + PIN + "\n"
        "      - run: PYTHONPATH=lib python entry.py\n"
        "  vendor:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@" + PIN + "\n"
        "      - uses: actions/checkout@" + PIN + "\n"
        "        with:\n"
        "          repository: example/vendor\n"
        "          ref: " + VENDOR_PIN + "\n"
        "          path: lib\n"
        "      - run: PYTHONPATH=lib python entry.py\n",
        encoding="utf-8",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    assert "lib/helper.py" in _paths(inventory)
    assert "external:example/vendor@" + VENDOR_PIN + "/helper.py" in _paths(inventory)
    assert not inventory.issues
