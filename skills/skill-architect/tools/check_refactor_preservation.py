"""Read-only semantic-preservation audit of a pinned skill refactor ledger.

This verifies declared invariants and route reachability, NOT stochastic model
behavior.  A candidate-authored ledger cannot certify semantic equivalence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any

MATERIAL = {"trigger", "authority", "safety_stop", "exception", "recovery", "completion", "evidence", "precedence"}
DISPOSITIONS = {"PRESERVE", "MOVE", "DEDUPLICATE", "REPLACE_BY_CANONICAL_OWNER", "REMOVE_WITH_REASON"}
SHA40 = re.compile(r"^[0-9a-f]{40}$")


def _contains_symlink(root: Path, relative: str) -> bool:
    """Reject any symlink component, even one resolving back inside the skill."""
    at = root
    for part in Path(relative).parts:
        at = at / part
        if at.is_symlink() or (os.name == "nt" and at.is_junction()):
            return True
    return False


def _windows_fd_inside_root(fd: int, root: Path) -> bool:
    """Bind the Windows path boundary to the opened file handle, not a racy name."""
    import ctypes
    import msvcrt

    try:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        get_name = kernel.GetFinalPathNameByHandleW
        get_name.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32)
        get_name.restype = ctypes.c_uint32
        handle = ctypes.c_void_p(msvcrt.get_osfhandle(fd))
        count = get_name(handle, None, 0, 0)
        if not count or count > 32768:
            return False
        buffer = ctypes.create_unicode_buffer(count + 1)
        written = get_name(handle, buffer, len(buffer), 0)
        if not written or written >= len(buffer):
            return False
        name = buffer.value
        if name.startswith("\\\\?\\UNC\\"):
            name = "\\\\" + name[8:]
        elif name.startswith("\\\\?\\"):
            name = name[4:]
        return Path(name).is_relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return False


def _read_attested_regular_file(root: Path, relative: str) -> bytes:
    """Read through a verified regular-file descriptor; never follow POSIX symlinks."""
    parts = Path(relative).parts
    if not parts or Path(relative).is_absolute() or ".." in parts:
        raise ValueError("invalid_relative_path")
    if os.name != "posix":
        # Windows lacks the portable dir_fd/O_NOFOLLOW chain; double-check
        # reparse/symlink status and require a bounded regular-file handle.
        if _contains_symlink(root, relative):
            raise ValueError("symlink_rejected")
        with (root / relative).open("rb") as stream:
            if not _windows_fd_inside_root(stream.fileno(), root):
                raise ValueError("outside_root_handle")
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 1_000_000:
                raise ValueError("unsafe_file_type_or_size")
            data = stream.read(1_000_001)
        if _contains_symlink(root, relative) or len(data) > 1_000_000:
            raise ValueError("file_changed_or_oversized")
        return data

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    handles: list[int] = [os.open(root, directory_flags)]
    try:
        for part in parts[:-1]:
            handles.append(os.open(part, directory_flags, dir_fd=handles[-1]))
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        handles.append(os.open(parts[-1], flags, dir_fd=handles[-1]))
        info = os.fstat(handles[-1])
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1_000_000:
            raise ValueError("unsafe_file_type_or_size")
        data = os.read(handles[-1], 1_000_001)
        if len(data) > 1_000_000:
            raise ValueError("oversized_file")
        return data
    finally:
        for handle in reversed(handles):
            os.close(handle)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _trusted_git_executable(configured: str | None = None) -> str:
    """Choose fixed system Git or an operator-configured absolute path, never PATH."""
    if configured is not None:
        if not configured or not Path(configured).is_absolute():
            raise ValueError("trusted_git_executable_not_absolute")
        if os.name == "nt":
            # Portable Windows paths need externally verified ACL authority.
            raise ValueError("trusted_git_override_unsupported_on_windows")
        candidates = (configured,)
    elif os.name == "nt":
        candidates = (
            "C:/Program Files/Git/cmd/git.exe",
            "C:/Program Files/Git/bin/git.exe",
            "C:/Program Files/Git/mingw64/bin/git.exe",
            "C:/Program Files (x86)/Git/cmd/git.exe",
        )
    else:
        candidates = ("/usr/bin/git", "/bin/git", "/opt/homebrew/bin/git", "/usr/local/bin/git")
    for name in candidates:
        try:
            binary = Path(name).resolve(strict=True)
            if not binary.is_file():
                continue
            if os.name == "nt":
                # Fixed Program Files installations are the Windows trust boundary.
                return str(binary)
            # The complete executable chain must be system-owned, not caller-
            # controlled; a chmod 755 shim alone cannot authenticate Git.
            if all(
                part.stat().st_uid == 0 and not part.stat().st_mode & (stat.S_IWGRP | stat.S_IWOTH)
                for part in (binary, *binary.parents)
            ):
                return str(binary)
        except (OSError, RuntimeError):
            continue
    raise FileNotFoundError("trusted_git_executable_unavailable")


def _trusted_git_env(executable: str) -> dict[str, str]:
    """Drop inherited Git and dynamic loader overrides; use fixed helper paths."""
    env = {name: value for name, value in os.environ.items() if not name.upper().startswith(("GIT_", "LD_", "DYLD_"))}
    env["PATH"] = (
        str(Path(executable).parent) + ";C:/Windows/System32;C:/Windows"
        if os.name == "nt"
        else str(Path(executable).parent) + ":/usr/bin:/bin:/usr/sbin:/sbin"
    )
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    env["GIT_OPTIONAL_LOCKS"] = "0"
    return env


def _verify_baseline_git_revision(
    baseline: dict[str, Any], ledger: dict[str, Any], candidate: Path, *, trusted_git_executable: str | None = None
) -> list[str]:
    """Resolve historical objects only from the checker's own trusted checkout.

    Candidate paths, candidate-owned .git and caller-authored metadata cannot
    select the provenance repository; a missing baseline object fails closed.
    """
    revision = baseline.get("revision")
    expected_tree = ledger.get("baseline_source_tree_sha")
    source_blobs = ledger.get("baseline_source_blobs")
    if (
        not isinstance(revision, str)
        or not SHA40.fullmatch(revision)
        or not isinstance(expected_tree, str)
        or not SHA40.fullmatch(expected_tree)
        or not isinstance(source_blobs, dict)
        or not source_blobs
        or len(source_blobs) > 64
    ):
        return ["invalid_git_revision_bindings"]

    # The running tool itself establishes the trust anchor. The candidate
    # is never a source for historical Git object resolution.
    trusted_root = Path(__file__).resolve().parents[3]
    # Only auditable skill directories inside the checker's trusted checkout
    # may select historical subtree names. A foreign candidate's .git cannot.
    try:
        relative_skill = candidate.resolve().relative_to(trusted_root)
    except (ValueError, RuntimeError):
        return ["candidate_outside_trusted_repo"]
    if len(relative_skill.parts) != 2 or relative_skill.parts[0] != "skills":
        return ["candidate_not_skill_directory"]
    location = relative_skill.as_posix()
    try:
        git_executable = _trusted_git_executable(trusted_git_executable)
        git_env = _trusted_git_env(git_executable)

        def resolve(object_id: str) -> str:
            completed = subprocess.run(
                [git_executable, "-C", str(trusted_root), "rev-parse", "--verify", object_id],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
                env=git_env,
            )
            return completed.stdout.strip()

        actual_root = subprocess.run(
            [git_executable, "-C", str(trusted_root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            env=git_env,
        ).stdout.strip()
        if Path(actual_root).resolve() != trusted_root:
            return ["trusted_git_root_mismatch"]
        # Classify an existing tree/tag/blob as a wrong revision type rather
        # than conflating it with an unavailable Git object.
        object_type = subprocess.run(
            [git_executable, "-C", str(trusted_root), "cat-file", "-t", revision],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
            env=git_env,
        ).stdout.strip()
        if object_type != "commit":
            return ["baseline_git_commit_mismatch"]
        if resolve(revision + "^{commit}") != revision:
            return ["baseline_git_commit_mismatch"]
        # A valid object hash is not a history trust boundary: reject detached
        # objects unrelated to the checked-out, reviewed revision.
        ancestry = subprocess.run(
            [git_executable, "-C", str(trusted_root), "merge-base", "--is-ancestor", revision, "HEAD"],
            check=False, capture_output=True, timeout=10, env=git_env,
        )
        if ancestry.returncode != 0:
            return ["baseline_git_revision_untrusted"]
        historical_tree = resolve(revision + ":" + location)
        if historical_tree != expected_tree:
            return ["baseline_git_tree_mismatch"]
        for relative, expected_blob in source_blobs.items():
            if (
                not isinstance(relative, str)
                or not relative
                or Path(relative).is_absolute()
                or ".." in Path(relative).parts
                or not isinstance(expected_blob, str)
                or not SHA40.fullmatch(expected_blob)
            ):
                return ["invalid_git_blob_reference"]
            prefix = location + "/" if location else ""
            if resolve(revision + ":" + prefix + relative) != expected_blob:
                return ["baseline_git_blob_mismatch:" + relative[:100]]
    except (OSError, subprocess.SubprocessError, ValueError):
        return ["baseline_git_revision_unavailable"]
    return []


def _has_negated_or_delayed_route(text: str) -> bool:
    """Fail closed on negated and delayed requirements in verified instructions."""
    normalized = text.replace("\u2019", "'")
    return bool(
        re.search(
            r"\b(?:not|never|no|avoid|without|skip|ignore|disregard|bypass|waive|"
            r"omit|discard|circumvent|prohibit|forbid|cannot|set\s+aside)\b|\w+n't\b",
            normalized,
            re.IGNORECASE,
        )
        or re.search(r"\b(?:after|later|until|once|afterward|afterwards)\b", normalized, re.IGNORECASE)
        or re.search(
            r"\b(?:optional|optionally|may|might|could|can|should|unless|suggested|"
            r"recommended|discretionary|discretion)\b"
            r"|\bif\s+(?:convenient|available|possible|practical|desired|preferred|requested)\b"
            r"|\bwhen\s+convenient\b",
            normalized,
            re.IGNORECASE,
        )
    )


def _effect_bound_timing(text: str) -> bool:
    """Recognize explicit pre-effect clauses; unrelated deadlines are not proof."""
    return bool(
        re.match(
            r"\b(?:before|prior to)\s+(?:(?:any|the|a|each)\s+)?"
            r"(?:(?:governed|destructive|external|mutating|irreversible)\s+)?"
            r"(?:action|operation|effect|side[- ]effect|mutation|change|write|commit|"
            r"call|execution|publishing|publication|deleting|deletion|removing|removal)\b",
            text.lstrip(" \t`"),
            re.IGNORECASE,
        )
    )


def _retained_pre_action(line: str, anchor: str, kind: str) -> bool:
    """Require an effect deadline directly on the anchor or the owner load."""
    index = line.find(anchor)
    if index < 0:
        return False
    remainder = line[index + len(anchor) :]
    if _effect_bound_timing(remainder):
        return True
    if kind != "trigger":
        return False
    return any(
        _effect_bound_timing(remainder[match.end() :])
        for match in re.finditer(
            r"\b(?:read|consult|load|open|follow|use|see)\s+`?[A-Za-z0-9_./-]+`?",
            remainder,
            re.IGNORECASE,
        )
    )


def _mandatory_owner_instruction(line: str, anchor: str) -> bool:
    """A critical owner anchor must start an affirmative, mandatory instruction."""
    normalized = re.sub(r"^\s*(?:[-*+]|\d+\.)\s+", "", line).lstrip()
    if _has_negated_or_delayed_route(normalized):
        return False
    if re.search(
        r"\b(?:optional|optionally|may|might|could|can|should|suggested|recommended|"
        r"discretionary|unless|when convenient)\b",
        normalized,
        re.IGNORECASE,
    ):
        return False
    if not re.match(re.escape(anchor) + r"\b", normalized):
        return False
    # Passive or historical negation can disable an apparently imperative
    # anchor. Prefer rejecting unsupported semantic qualifiers to false PASS.
    suffix = normalized[len(anchor) :]
    if re.search(
        r"\b(?:prohibited|forbidden|disallowed|disabled|revoked|deprecated|"
        r"waived|unnecessary|not\s+required|no\s+longer\s+required)\b",
        suffix,
        re.IGNORECASE,
    ):
        return False
    if re.match(r"\s+(?:is|was|are|were|becomes|became)\s+", suffix, re.IGNORECASE):
        # An anchor asserting that something 'is ...' is descriptive rather
        # than an imperative; explicit rewrites are required for acceptance.
        return False
    return True


def _positive_entrypoint_route(route: str, owner: str, *, require_pre_action: bool = False) -> bool:
    """Accept only a local affirmative instruction leading to the declared owner.

    The static grammar is intentionally restrictive: unsupported phrasing
    requires a reviewed route rewrite, never a guessed behavioral equivalent.
    """
    position = route.find(owner)
    if position < 0 or route.find(owner, position + len(owner)) >= 0:
        return False
    # A declared owner must terminate at a path/token boundary. Otherwise a
    # route to STANDARD.md.bak can impersonate a route to STANDARD.md.
    suffix = route[position + len(owner) :]
    if suffix and suffix[0] not in " \t\r\n`),;:!?":
        return False
    # Examine the entire declared route for explicit negation. Restricting
    # this check to the last 128 characters can certify a long negative
    # instruction as an affirmative owner route.
    normalized = route.replace("\u2019", "'")
    # Check the entire instruction, including qualifiers after the owner.
    if _has_negated_or_delayed_route(normalized):
        return False
    if require_pre_action and not _effect_bound_timing(normalized[position + len(owner) :]):
        return False
    prefix = normalized[:position][-128:]
    return bool(
        re.search(
            r"(?:\b(?:read|consult|load|open|follow|use|see)\s+`?|->\s*`?)$",
            prefix,
            re.IGNORECASE,
        )
    )


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _git_blob_sha(data: bytes) -> str:
    normalized = data.replace(b"\r\n", b"\n")
    return hashlib.sha1(
        b"blob " + str(len(normalized)).encode() + b"\0" + normalized, usedforsecurity=False
    ).hexdigest()


def _content_bindings(
    baseline: dict[str, Any], ledger: dict[str, Any], candidate: Path, verified: dict[str, bytes] | None = None
) -> list[str]:
    findings: list[str] = []
    revision = baseline.get("revision")
    if not isinstance(revision, str) or not SHA40.fullmatch(revision):
        findings.append("invalid_baseline_revision")
    digest = "sha256:" + hashlib.sha256(_canonical_json(baseline)).hexdigest()
    if ledger.get("baseline_sha256") != digest:
        findings.append("baseline_content_mismatch")
    bindings = ledger.get("candidate_files")
    if not isinstance(bindings, dict) or not bindings:
        return findings + ["candidate_files_missing"]
    if len(bindings) > 64:
        return findings + ["candidate_inventory_too_large"]
    for required in ("SKILL.md", "STANDARD.md", "manifest.yaml"):
        if required not in bindings:
            findings.append("required_candidate_document_missing:" + required)
    root = candidate.resolve()
    for rel, expected in bindings.items():
        if (
            not isinstance(rel, str)
            or not rel
            or Path(rel).is_absolute()
            or ".." in Path(rel).parts
            or not isinstance(expected, str)
            or not SHA40.fullmatch(expected)
        ):
            findings.append("invalid_candidate_binding")
            continue
        if _contains_symlink(root, rel):
            findings.append("candidate_symlink_rejected:" + rel)
            continue
        path = (candidate / rel).resolve()
        if not path.is_relative_to(root):
            findings.append("candidate_file_missing:" + rel)
            continue
        try:
            content = _read_attested_regular_file(root, rel)
        except (OSError, ValueError):
            findings.append("candidate_file_unreadable:" + rel)
            continue
        if _git_blob_sha(content) != expected:
            findings.append("candidate_content_mismatch:" + rel)
        elif verified is not None:
            verified[rel] = content
    return findings


def _operative_skill_text(content: bytes) -> str:
    """Exclude fenced examples, HTML comments, quotes and indented code."""
    text = re.sub(r"<!--.*?(?:-->|\Z)", "", content.decode("utf-8"), flags=re.DOTALL)
    kept: list[str] = []
    fence = ""
    for line in text.splitlines():
        if fence:
            close = r"^[ ]{0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*$"
            if re.match(close, line):
                fence = ""
            continue
        opener = re.match(r"^[ ]{0,3}(`{3,}|~{3,})", line)
        if opener:
            fence = opener.group(1)
            continue
        if line.startswith(("    ", "\t")) or re.match(r"^[ ]{0,3}>", line):
            continue
        kept.append(line)
    return "\n".join(kept)


def assess(
    baseline: dict[str, Any], ledger: dict[str, Any], candidate: Path, *, baseline_tree: Path | None = None
) -> dict[str, Any]:
    """Verify original source mapping and exact candidate documents, not model equivalence."""
    candidate_verified: dict[str, bytes] = {}
    baseline_verified: dict[str, bytes] = {}
    findings: list[str] = _content_bindings(baseline, ledger, candidate, candidate_verified)
    operative_skill = (
        _operative_skill_text(candidate_verified["SKILL.md"]) if "SKILL.md" in candidate_verified else ""
    )
    candidate_files = ledger.get("candidate_files")
    if not isinstance(candidate_files, dict):
        candidate_files = {}  # The invalid shape was already reported above.
    original_files = ledger.get("baseline_source_blobs")
    if baseline_tree is None or not isinstance(original_files, dict) or not original_files:
        findings.append("baseline_source_unverified")
    elif len(original_files) > 64:
        findings.append("baseline_source_inventory_too_large")
    else:
        root = baseline_tree.resolve()
        for rel, blob in original_files.items():
            if (
                not isinstance(rel, str)
                or not rel
                or Path(rel).is_absolute()
                or ".." in Path(rel).parts
                or not isinstance(blob, str)
                or not SHA40.fullmatch(blob)
            ):
                findings.append("invalid_baseline_binding")
                continue
            if _contains_symlink(root, rel):
                findings.append("baseline_symlink_rejected:" + rel)
                continue
            source = (baseline_tree / rel).resolve()
            if not source.is_relative_to(root):
                findings.append("baseline_source_missing:" + rel)
                continue
            try:
                original = _read_attested_regular_file(root, rel)
            except (OSError, ValueError):
                findings.append("baseline_source_unreadable:" + rel)
                continue
            if _git_blob_sha(original) != blob:
                findings.append("baseline_source_drift:" + rel)
            else:
                baseline_verified[rel] = original
    baseline_rules = baseline.get("required_behaviors")
    decisions = ledger.get("decisions")
    if (
        not isinstance(baseline_rules, list)
        or not baseline_rules
        or len(baseline_rules) > 128
        or not isinstance(decisions, list)
        or len(decisions) > 128
    ):
        return {"structural": "FAILED", "behavior": "BEHAVIOR_NOT_VERIFIED", "findings": findings + ["invalid_ledger"]}
    by_id: dict[str, dict[str, Any]] = {}
    for entry in decisions:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not 1 <= len(entry["id"]) <= 128:
            findings.append("invalid_decision")
            continue
        if entry["id"] in by_id:
            findings.append("duplicate_decision:" + entry["id"])
        by_id[entry["id"]] = entry
    seen_baseline_ids: set[str] = set()
    for old in baseline_rules:
        if not isinstance(old, dict) or not isinstance(old.get("id"), str):
            findings.append("invalid_baseline_rule")
            continue
        rule_id = old["id"]
        if rule_id in seen_baseline_ids:
            findings.append("duplicate_baseline_rule:" + rule_id[:128])
            continue
        seen_baseline_ids.add(rule_id)
        decision = by_id.get(rule_id)
        if decision is None:
            findings.append("missing_required_behavior:" + rule_id)
            continue
        kind = old.get("kind")
        if kind not in MATERIAL:
            findings.append("unsupported_behavior_class:" + rule_id[:128])
        old_path = decision.get("source_path")
        old_anchor = decision.get("source_anchor")
        if (
            not isinstance(old_path, str)
            or old_path not in (original_files if isinstance(original_files, dict) else {})
            or not isinstance(old_anchor, str)
            or not 1 <= len(old_anchor) <= 256
            or not isinstance(decision.get("positive_case"), str)
            or not 1 <= len(decision["positive_case"]) <= 256
            or not isinstance(decision.get("negative_case"), str)
            or not 1 <= len(decision["negative_case"]) <= 256
            or not isinstance(decision.get("verification"), str)
            or not 1 <= len(decision["verification"]) <= 256
        ):
            findings.append("incomplete_old_to_new_mapping:" + rule_id[:128])
        elif baseline_tree is not None:
            root = baseline_tree.resolve()
            if _contains_symlink(root, old_path):
                findings.append("baseline_symlink_rejected:" + old_path)
            else:
                content = baseline_verified.get(old_path)
                if content is None:
                    findings.append("baseline_source_unverified:" + rule_id[:128])
                elif old_anchor not in content.decode("utf-8"):
                    findings.append("baseline_anchor_missing:" + rule_id[:128])
        disposition = decision.get("disposition")
        if disposition not in DISPOSITIONS:
            findings.append("invalid_disposition:" + rule_id)
            continue
        if kind in MATERIAL and disposition == "REMOVE_WITH_REASON":
            # Human review and model-backed comparison, not this ledger, may authorize a semantic removal.
            findings.append("required_behavior_removed:" + rule_id)
        if disposition == "REMOVE_WITH_REASON" and not decision.get("reason"):
            findings.append("unexplained_removal:" + rule_id)
        if disposition != "REMOVE_WITH_REASON":
            rel = decision.get("target_path")
            if not isinstance(rel, str) or not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
                findings.append("unsafe_or_missing_owner:" + rule_id)
                continue
            if rel not in candidate_files:
                findings.append("unbound_owner:" + rule_id)
            root = candidate.resolve()
            if _contains_symlink(root, rel):
                findings.append("candidate_symlink_rejected:" + rel)
                continue
            target = (candidate / rel).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                findings.append("unreachable_owner:" + rule_id)
                continue
            if rel != "SKILL.md":
                require_pre_action = kind in {"trigger", "authority", "safety_stop", "precedence"}
                # A visible trigger with an unreachable moved owner is not a valid
                # route: bind the exact conditional entrypoint instruction to its
                # destination, including for noncritical reference-only rules.
                trigger = decision.get("pre_load_trigger")
                route = decision.get("entrypoint_route")
                if "SKILL.md" not in candidate_verified:
                    findings.append("owner_entrypoint_unbound:" + rule_id[:128])
                elif (
                    not isinstance(trigger, str)
                    or not trigger
                    or not isinstance(route, str)
                    or len(route) > 1024
                    or trigger not in route
                    or rel not in route
                    or not _positive_entrypoint_route(route, rel)
                    or not any(
                        _positive_entrypoint_route(match.group(0), rel, require_pre_action=require_pre_action)
                        for match in re.finditer(
                            r"(?m)^[ \t]*(?:[-*+]|\d+\.)?[ \t]*" + re.escape(route) + r"[^\r\n]*",
                            operative_skill,
                        )
                    )
                ):
                    findings.append("owner_route_unreachable:" + rule_id[:128])
            elif kind in {"trigger", "authority", "safety_stop", "precedence"}:
                # Rules retained in SKILL.md still need an affirmative before-action
                # instruction; a matching anchor alone may be a negated instruction.
                trigger = decision.get("pre_load_trigger")
                anchor = decision.get("target_anchor")
                if (
                    "SKILL.md" not in candidate_verified
                    or not isinstance(trigger, str)
                    or not trigger
                    or not isinstance(anchor, str)
                    or not anchor
                    or not any(
                        trigger in line
                        and anchor in line
                        and _mandatory_owner_instruction(line, anchor)
                        and _retained_pre_action(line, anchor, kind)
                        for line in operative_skill.splitlines()
                    )
                ):
                    findings.append("critical_entrypoint_not_affirmative:" + rule_id[:128])
            required_anchor = decision.get("target_anchor")
            if not isinstance(required_anchor, str) or not required_anchor:
                findings.append("missing_target_anchor:" + rule_id)
            elif rel not in candidate_verified:
                findings.append("target_content_unverified:" + rule_id[:128])
            elif required_anchor not in (
                operative_skill if rel == "SKILL.md" else candidate_verified[rel].decode("utf-8")
            ):
                findings.append("anchor_not_present:" + rule_id)
            elif kind in MATERIAL:
                critical = kind in {"trigger", "authority", "safety_stop", "precedence"}
                if not any(
                    _mandatory_owner_instruction(line, required_anchor)
                    if critical
                    else any(
                        _mandatory_owner_instruction(sentence, required_anchor)
                        for sentence in re.split(r"(?<=[.!?])\s+", line)
                    )
                    for line in (
                        operative_skill if rel == "SKILL.md" else candidate_verified[rel].decode("utf-8")
                    ).splitlines()
                ):
                    finding = "critical_owner_rule_negated:" if critical else "material_owner_rule_negated:"
                    findings.append(finding + rule_id[:128])
            if kind in MATERIAL and not decision.get("negative_case"):
                findings.append("negative_case_missing:" + rule_id)
            if not decision.get("verification"):
                findings.append("verification_missing:" + rule_id)
            if kind in {"trigger", "authority", "safety_stop", "precedence"}:
                pre_load = decision.get("pre_load_path")
                if pre_load != "SKILL.md":
                    findings.append("critical_preload_not_in_skill_entrypoint:" + rule_id[:128])
                marker = decision.get("pre_load_trigger")
                if not isinstance(pre_load, str) or not isinstance(marker, str) or not marker:
                    findings.append("preload_route_missing:" + rule_id)
                elif Path(pre_load).is_absolute() or ".." in Path(pre_load).parts:
                    findings.append("preload_route_unsafe:" + rule_id)
                else:
                    if pre_load not in candidate_files:
                        findings.append("unbound_preload_route:" + rule_id)
                    if pre_load not in candidate_verified or marker not in (
                        operative_skill if pre_load == "SKILL.md" else candidate_verified[pre_load].decode("utf-8")
                    ):
                        findings.append("preload_trigger_unreachable:" + rule_id)
    unknown = sorted(set(by_id) - {x.get("id") for x in baseline_rules if isinstance(x, dict)})
    findings.extend("unreviewed_new_rule:" + item for item in unknown)
    # Bounded diagnostics never promote a failed or incomplete check.
    findings = [item[:256] for item in findings[:128]] + (["findings_truncated"] if len(findings) > 128 else [])
    # Candidate files are content-attested, but the ledger's release label is
    # not a Git commit identity and must never be presented as one.
    declared_version = ledger.get("candidate_revision")
    if not isinstance(declared_version, str) or re.fullmatch(r"\d+\.\d+\.\d+", declared_version) is None:
        declared_version = None
    return {
        "structural": "FAILED" if findings else "PASS",
        "behavior": "BEHAVIOR_NOT_VERIFIED",
        "verification_scope": "normative_owner_and_route_mapping",
        "eval_corpus": "NOT_VERIFIED",
        "findings": findings,
        "baseline_revision": baseline.get("revision"),
        "candidate_revision": "NOT_VERIFIED",
        "declared_candidate_version": declared_version,
    }


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        # Parser-supplied messages can embed caller paths or untrusted argument
        # values. Keep the public outcome typed, bounded, and non-disclosing.
        print(
            json.dumps(
                {
                    "structural": "INVALID_INPUT",
                    "behavior": "BEHAVIOR_NOT_VERIFIED",
                    "findings": ["invalid_arguments"],
                }
            )
        )
        raise SystemExit(2)


def _read_bounded_json_object(path: Path) -> dict[str, Any]:
    """Validate the opened descriptor, not a racy path stat; never read a FIFO."""
    max_bytes = 262144
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as source:
        st = os.fstat(source.fileno())
        if not stat.S_ISREG(st.st_mode):
            raise ValueError("non_regular_input")
        if st.st_size > max_bytes:
            raise ValueError("oversized_input")
        content = source.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError("oversized_input")
    obj = json.loads(content.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    if not isinstance(obj, dict):
        raise ValueError("invalid_json_object")
    return obj


def main() -> int:
    parser = JsonArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline-tree", type=Path)
    parser.add_argument("--trusted-git-executable", type=str)
    args = parser.parse_args()
    try:
        baseline = _read_bounded_json_object(args.baseline)
        ledger = _read_bounded_json_object(args.ledger)
        if not args.candidate.is_dir():
            raise ValueError("invalid_candidate")
        if not isinstance(ledger.get("candidate_files"), dict):
            raise ValueError("invalid_candidate_files")
        baseline_tree = args.baseline_tree or args.baseline.parent / "baseline_snapshots"
        result = assess(baseline, ledger, args.candidate, baseline_tree=baseline_tree)
        git_findings = _verify_baseline_git_revision(
            baseline, ledger, args.candidate, trusted_git_executable=args.trusted_git_executable
        )
        if git_findings:
            result["structural"] = "FAILED"
            result["findings"] = (result["findings"] + git_findings)[:129]
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError, RuntimeError) as exc:
        result = {
            "structural": "INVALID_INPUT",
            "behavior": "BEHAVIOR_NOT_VERIFIED",
            "findings": ["invalid_input:" + type(exc).__name__],
        }
        print(json.dumps(result))
        return 2
    print(json.dumps(result, indent=2))
    return 1 if result["structural"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
