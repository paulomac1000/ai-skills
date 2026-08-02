"""Patch incremental repository discovery and its existing regression."""

from __future__ import annotations

from textwrap import dedent, indent

from .common import read, replace_between


def stage_discovery() -> str:
    path = "skills/agents-md-architect/tools/discover_repository.py"
    text = read(path)
    text = replace_between(
        text,
        "def _is_dotnet_bin_output(project_directory: Path, candidate: Path) -> bool:\n",
        "def _is_ignored_directory(root: Path, current: Path, name: str) -> bool:\n",
        dedent(
            '''\
            def _is_dotnet_bin_output(project_directory: Path, candidate: Path) -> bool:
                if not _is_dotnet_project_directory(project_directory):
                    return False
                script_suffixes = {"", ".py", ".rb", ".ps1", ".sh"}
                compiled_suffixes = {".dll", ".exe", ".json", ".pdb", ".so", ".dylib"}
                try:
                    with os.scandir(candidate) as entries:
                        for index, entry in enumerate(entries, start=1):
                            if index > MAX_DISCOVERY_ENTRIES:
                                return False
                            if entry.is_symlink():
                                return False
                            if entry.is_file(follow_symlinks=False):
                                suffix = Path(entry.name).suffix.casefold()
                                if suffix in script_suffixes or suffix not in compiled_suffixes:
                                    return False
                            elif not entry.is_dir(follow_symlinks=False):
                                return False
                except OSError:
                    return False
                return True


            '''
        ),
        label=f"{path} bounded bin inspection",
    )
    replacement = indent(
        dedent(
            '''\
            entries_seen = 0
            stop = False
            pending: list[tuple[Path, int]] = [(safe_root, 0)]

            while pending and not stop:
                current, depth = pending.pop()
                if depth > MAX_DISCOVERY_DEPTH:
                    issues.add(
                        f"discovery depth exceeds {MAX_DISCOVERY_DEPTH}: {_relative(safe_root, current)}"
                    )
                    continue

                retained_directories: list[Path] = []
                try:
                    with os.scandir(current) as entries:
                        for entry in entries:
                            entries_seen += 1
                            if entries_seen > MAX_DISCOVERY_ENTRIES:
                                issues.add(f"discovery entries exceed {MAX_DISCOVERY_ENTRIES}")
                                stop = True
                                break
                            candidate = Path(entry.path)
                            relative = _relative(safe_root, candidate)
                            try:
                                if entry.is_symlink():
                                    symlinks.add(relative)
                                elif entry.is_dir(follow_symlinks=False):
                                    if _is_ignored_directory(safe_root, current, entry.name):
                                        continue
                                    if depth + 1 > MAX_DISCOVERY_DEPTH:
                                        issues.add(
                                            f"discovery depth exceeds {MAX_DISCOVERY_DEPTH}: {relative}"
                                        )
                                        continue
                                    retained_directories.append(candidate)
                                elif entry.is_file(follow_symlinks=False):
                                    files.add(relative)
                            except (OSError, RuntimeError) as error:
                                issues.add(f"unreadable path {relative}: {error}")
                except OSError as error:
                    location = error.filename or current.as_posix()
                    issues.add(f"unreadable path {location}: {error}")
                    continue

                if stop:
                    break
                pending.extend(
                    (candidate, depth + 1)
                    for candidate in sorted(retained_directories, key=lambda item: item.name, reverse=True)
                )

            '''
        ),
        "    ",
    )
    text = replace_between(
        text,
        "    entries_seen = 0\n",
        "    manifests = {\n",
        replacement,
        label=f"{path} incremental discovery",
    )
    return text


def stage_existing_tests() -> str:
    path = "tests/test_agents_md_review_regressions.py"
    text = read(path)
    text = replace_between(
        text,
        "def test_discovery_reports_walk_errors_and_entry_limits(\n",
        "def test_audit_reports_incomplete_discovery(\n",
        dedent(
            '''\
            def test_discovery_reports_scandir_errors_and_entry_limits(
                tmp_path: Path,
                monkeypatch: pytest.MonkeyPatch,
            ) -> None:
                def broken_scandir(path: Path) -> Any:
                    raise PermissionError(13, "denied", str(Path(path) / "private"))

                monkeypatch.setattr(discovery.os, "scandir", broken_scandir)
                result = discovery.discover(tmp_path)
                assert result.issues and "unreadable path" in result.issues[0]

                monkeypatch.undo()
                monkeypatch.setattr(discovery, "MAX_DISCOVERY_ENTRIES", 1)
                write(tmp_path / "one.txt", "1")
                write(tmp_path / "two.txt", "2")
                result = discovery.discover(tmp_path)
                assert any("discovery entries exceed" in issue for issue in result.issues)


            '''
        ),
        label=f"{path} scandir regression",
    )
    return text
