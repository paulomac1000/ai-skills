"""Commit authorship audit regressions."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_commit_authorship.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("check_commit_authorship_target", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _repository(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "--quiet"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "pawel.maciejewski95@gmail.com"],
        cwd=root,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Pawel"], cwd=root, check=True)
    return root


def _commit(root: Path, message: str, *, email: str, name: str = "Pawel") -> str:
    (root / "file.txt").write_text(message, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    environment = {
        "GIT_AUTHOR_NAME": name,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": name,
        "GIT_COMMITTER_EMAIL": email,
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(root),
    }
    subprocess.run(
        ["git", "commit", "--quiet", "-m", message],
        cwd=root,
        check=True,
        capture_output=True,
        env=environment,
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_owner_and_bot_identities_are_accepted() -> None:
    module = _load_script()
    commits = [
        ("a" * 40, "Pawel Maciejewski", "pawel.maciejewski95@gmail.com", "pawel.maciejewski95@gmail.com"),
        (
            "b" * 40,
            "dependabot[bot]",
            "49699333+dependabot[bot]@users.noreply.github.com",
            "49699333+dependabot[bot]@users.noreply.github.com",
        ),
        (
            "c" * 40,
            "github-actions[bot]",
            "41898282+github-actions[bot]@users.noreply.github.com",
            "41898282+github-actions[bot]@users.noreply.github.com",
        ),
        (
            "d" * 40,
            "Pawel Maciejewski",
            "9095484+paulomac1000@users.noreply.github.com",
            "9095484+paulomac1000@users.noreply.github.com",
        ),
    ]
    assert module.unauthorized_identities(commits) == []


def test_platform_committer_is_accepted_for_merge_and_rebase() -> None:
    module = _load_script()
    commits = [
        ("a" * 40, "Pawel Maciejewski", "pawel.maciejewski95@gmail.com", "noreply@github.com"),
        ("b" * 40, "dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com", "noreply@github.com"),
    ]
    assert module.unauthorized_identities(commits) == []


def test_platform_address_is_not_trusted_as_an_author() -> None:
    module = _load_script()
    commits = [
        ("a" * 40, "Pawel Maciejewski", "noreply@github.com", "noreply@github.com"),
    ]
    findings = module.unauthorized_identities(commits)
    assert len(findings) == 1
    assert "UNAUTHORIZED_AUTHOR_IDENTITY" in findings[0]


def test_unverified_display_name_with_the_same_address_is_still_accepted() -> None:
    module = _load_script()
    commits = [
        ("a" * 40, "Any Name", "pawel.maciejewski95@gmail.com", "pawel.maciejewski95@gmail.com"),
    ]
    assert module.unauthorized_identities(commits) == []


def test_unverified_address_is_rejected() -> None:
    module = _load_script()
    commits = [
        ("a" * 40, "Pawel Maciejewski", "paulomac1000@gmail.com", "paulomac1000@gmail.com"),
    ]
    findings = module.unauthorized_identities(commits)
    assert len(findings) == 2
    assert "UNAUTHORIZED_AUTHOR_IDENTITY" in findings[0]
    assert "UNAUTHORIZED_COMMITTER_IDENTITY" in findings[1]


def test_foreign_identity_is_rejected() -> None:
    module = _load_script()
    commits = [
        ("a" * 40, "sisyphus-lab", "sisyphus-lab@example.invalid", "sisyphus-lab@example.invalid"),
    ]
    findings = module.unauthorized_identities(commits)
    assert len(findings) == 2
    assert "sisyphus-lab" in findings[0]


def test_the_audit_reads_the_commits_of_the_range(tmp_path: Path) -> None:
    module = _load_script()
    root = _repository(tmp_path)
    base = _commit(root, "base", email="pawel.maciejewski95@gmail.com")
    _commit(root, "trusted", email="49699333+dependabot[bot]@users.noreply.github.com")
    commits = module._commits(base, "HEAD", root=root)
    assert len(commits) == 1
    # The identity is recognized by the verified address, not by the name.
    assert commits[0][2] == "49699333+dependabot[bot]@users.noreply.github.com"
    assert module.unauthorized_identities(commits) == []


def test_an_empty_range_fails_closed(tmp_path: Path, capsys) -> None:
    module = _load_script()
    root = _repository(tmp_path)
    head = _commit(root, "base", email="pawel.maciejewski95@gmail.com")
    exit_code = module.main(["--base", head, "--head", head], root=root)
    assert exit_code == 1
    assert "AUTHORSHIP_AUDIT_EMPTY" in capsys.readouterr().out


def test_a_base_that_is_not_an_ancestor_fails_closed(tmp_path: Path, capsys) -> None:
    module = _load_script()
    root = _repository(tmp_path)
    base = _commit(root, "base", email="pawel.maciejewski95@gmail.com")
    _commit(root, "second", email="pawel.maciejewski95@gmail.com")
    orphan = _repository(tmp_path / "other")
    foreign = _commit(orphan, "foreign", email="pawel.maciejewski95@gmail.com")
    exit_code = module.main(["--base", foreign, "--head", base], root=root)
    assert exit_code == 1
    assert "AUTHORSHIP_AUDIT_INCOMPLETE" in capsys.readouterr().out


def test_an_unparsable_commit_record_fails_closed() -> None:
    module = _load_script()
    broken = "sha\x1fname\x1femail"
    try:
        module._parse_commits(broken, "base", "HEAD")
    except module.AuditError as error:
        assert "cannot be parsed" in str(error)
    else:
        raise AssertionError("an unparsable commit record must fail the audit")


def test_the_audited_head_is_taken_from_the_invocation(tmp_path: Path) -> None:
    """The gate must measure the ref the caller names, not a default."""
    module = _load_script()
    root = _repository(tmp_path)
    base = _commit(root, "base", email="pawel.maciejewski95@gmail.com")
    head = _commit(root, "second", email="49699333+dependabot[bot]@users.noreply.github.com")
    exit_code = module.main(["--base", base, "--head", head], root=root)
    assert exit_code == 0
    other = _commit(root, "third", email="sisyphus-lab@example.invalid")
    exit_code = module.main(["--base", base, "--head", other], root=root)
    assert exit_code == 1


def _merge_branch(root: Path, message: str, *, email: str) -> str:
    """Create a real merge commit so topology behavior is exercised, not faked."""
    subprocess.run(["git", "checkout", "--quiet", "-b", "side"], cwd=root, check=True)
    _commit(root, "side", email=email)
    subprocess.run(["git", "checkout", "--quiet", "-"], cwd=root, check=True)
    environment = {
        "GIT_AUTHOR_NAME": "Pawel",
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": "Pawel",
        "GIT_COMMITTER_EMAIL": email,
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": str(root),
    }
    subprocess.run(
        ["git", "merge", "--quiet", "--no-ff", "--no-edit", "-m", message, "side"],
        cwd=root,
        check=True,
        capture_output=True,
        env=environment,
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_a_foreign_commit_hidden_behind_a_merge_is_still_audited(
    tmp_path: Path,
    capsys,
) -> None:
    """Excluding merge commits from the identity listing must not hide identities."""
    module = _load_script()
    root = _repository(tmp_path)
    base = _commit(root, "base", email="pawel.maciejewski95@gmail.com")
    _merge_branch(root, "merge", email="sisyphus-lab@example.invalid")
    exit_code = module.main(["--base", base, "--head", "HEAD"], root=root)
    assert exit_code == 1
    output = capsys.readouterr().out
    assert "UNAUTHORIZED_AUTHOR_IDENTITY" in output
    assert "sisyphus-lab" in output


def test_a_push_range_with_a_merge_commit_fails_closed(tmp_path: Path, capsys) -> None:
    """T11: the integration policy is squash-only linear history, so a merge
    commit in a pushed main range is a policy violation, not an audited skip."""
    module = _load_script()
    root = _repository(tmp_path)
    base = _commit(root, "base", email="pawel.maciejewski95@gmail.com")
    _merge_branch(root, "merge", email="pawel.maciejewski95@gmail.com")
    exit_code = module.main(
        ["--base", base, "--head", "HEAD", "--forbid-merge-commits"],
        root=root,
    )
    assert exit_code == 1
    output = capsys.readouterr().out
    assert "MERGE_COMMIT_IN_RANGE" in output


def test_a_squash_shaped_push_range_passes_the_merge_topology_check(tmp_path: Path) -> None:
    module = _load_script()
    root = _repository(tmp_path)
    base = _commit(root, "base", email="pawel.maciejewski95@gmail.com")
    _commit(root, "integrated", email="pawel.maciejewski95@gmail.com")
    exit_code = module.main(
        ["--base", base, "--head", "HEAD", "--forbid-merge-commits"],
        root=root,
    )
    assert exit_code == 0
