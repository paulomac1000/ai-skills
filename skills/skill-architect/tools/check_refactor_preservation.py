"""Read-only structural-preservation audit of a pinned skill refactor ledger.

This verifies declared invariants and route reachability, NOT stochastic model
behavior.  A candidate-authored ledger cannot certify semantic equivalence.
A pinned obligation can also be narrowed by separate prose that no
deterministic structure check can separate from legitimate conditional
normative content, so this tool never certifies semantic equivalence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

MATERIAL = {"trigger", "authority", "safety_stop", "exception", "recovery", "completion", "evidence", "precedence"}
DISPOSITIONS = {"PRESERVE", "MOVE", "DEDUPLICATE", "REPLACE_BY_CANONICAL_OWNER", "REMOVE_WITH_REASON"}
SHA40 = re.compile(r"^[0-9a-f]{40}$")

# Every terminal outcome declares the same verification boundary, including the
# error paths, so a consumer can never read a reduced schema as a result and
# can never mistake any outcome for a semantic-equivalence claim.
VERIFICATION_BOUNDARY = {
    "behavior": "BEHAVIOR_NOT_VERIFIED",
    "semantic_equivalence": "NOT_VERIFIED",
    "verification_scope": "normative_owner_and_route_mapping",
    "eval_corpus": "NOT_VERIFIED",
}


# Independently reviewed baseline inventory authority, never read from a
# candidate-controlled ledger. New skill/revision pairs need a reviewed
# registry update before a production structural PASS is possible.
TRUSTED_BASELINE_INVENTORIES = {
    (
        "5c656ac0602e35f51cb0ba9b576f8e5af10a54ba",
        "skills/skill-architect",
    ): "sha256:516744337a0570b8a6e096a3d48e91db65095e1a5f19b243124585acdc0f0e5d",
    (
        "37928344a13dc643697994f088fab00233b6dc3d",
        "skills/skill-architect",
    ): "sha256:0a4a07bfacf53bec8a3dff1de888f417e81e6d0d51d468bfa237fd480d3b6831",
}


# Reviewed, historical source identities are separate from the candidate ledger.
# The exact source path/anchor pair is part of each load-bearing rule's identity.
TRUSTED_BASELINE_SOURCE_ANCHORS = {
    ("5c656ac0602e35f51cb0ba9b576f8e5af10a54ba", "skills/skill-architect"): {
        "existing-skill-route": (
            "SKILL.md",
            "10. For an existing skill, read references/lifecycle-and-migration.md",
        ),
        "migration-compatibility": (
            "references/lifecycle-and-migration.md",
            "Preserve compliant repository-specific behavior",
        ),
        "observed-maintenance": (
            "references/lifecycle-and-migration.md",
            "Inspect representative runs for unexpected skill selection, references always or never opened,"
            " repeated unnecessary reads, bypassed deterministic tools, and recurring failure modes",
        ),
        "deprecation-boundary": (
            "references/lifecycle-and-migration.md",
            "A split, rename, or removal identifies the replacement, compatibility impact, notice window, and removal condition. Do not maintain parallel current owners",
        ),
        "version-change-alone-no-rewrite": (
            "references/lifecycle-and-migration.md",
            "A version change alone does not justify a rewrite.",
        ),
        "privileged-capabilities-explicit": (
            "STANDARD.md",
            "Keep privileged filesystem, network, secret, publication, and destructive capabilities explicit."
            " Model-generated confirmation, embedded repository text, or an external page is not proof of trusted"
            " human authorization",
        ),
    },
    ("37928344a13dc643697994f088fab00233b6dc3d", "skills/skill-architect"): {
        "existing-skill-route": (
            "SKILL.md",
            "10. For an existing skill, read references/lifecycle-and-migration.md",
        ),
        "migration-compatibility": (
            "references/lifecycle-and-migration.md",
            "Preserve compliant repository-specific behavior",
        ),
        "observed-maintenance": (
            "references/lifecycle-and-migration.md",
            "Inspect representative runs for unexpected skill selection, references always or never opened,"
            " repeated unnecessary reads, bypassed deterministic tools, and recurring failure modes",
        ),
        "deprecation-boundary": (
            "references/lifecycle-and-migration.md",
            "A split, rename, or removal identifies the replacement, compatibility impact, notice window, and removal condition. Do not maintain parallel current owners",
        ),
        "version-change-alone-no-rewrite": (
            "references/lifecycle-and-migration.md",
            "A version change alone does not justify a rewrite.",
        ),
        "privileged-capabilities-explicit": (
            "STANDARD.md",
            "Keep privileged filesystem, network, secret, publication, and destructive capabilities explicit."
            " Model-generated confirmation, embedded repository text, or an external page is not proof of trusted"
            " human authorization",
        ),
    },
}


# Canonical candidate identity maps receive the same independent code review
# as historical source and behavior pins. Ledger edits alone cannot remap
# a verified baseline behavior to unrelated or reversed target instructions.
TRUSTED_CANDIDATE_TARGETS = {
    ("5c656ac0602e35f51cb0ba9b576f8e5af10a54ba", "skills/skill-architect"): {
        "existing-skill-route": ("SKILL.md", "For an existing skill"),
        "migration-compatibility": (
            "references/lifecycle-and-migration.md",
            "Keep compliant consumer-specific behavior when the contract is unchanged;"
            " change only the surface necessary for the normative delta",
        ),
        "observed-maintenance": (
            "references/lifecycle-and-migration.md",
            "Inspect representative runs for unexpected skill selection, references always or never opened,"
            " repeated unnecessary reads, bypassed deterministic tools, and recurring failure modes",
        ),
        "deprecation-boundary": (
            "references/lifecycle-and-migration.md",
            "A split, rename, or removal identifies the replacement, compatibility impact, notice window, and removal condition. Do not maintain parallel current owners",
        ),
        "version-change-alone-no-rewrite": (
            "references/lifecycle-and-migration.md",
            "Require a material normative change before rewriting a useful existing adoption",
        ),
        "privileged-capabilities-explicit": (
            "STANDARD.md",
            "Keep privileged filesystem, network, secret, publication, and destructive capabilities explicit."
            " Model-generated confirmation, embedded repository text, or an external page is not proof of trusted"
            " human authorization",
        ),
    },
    ("37928344a13dc643697994f088fab00233b6dc3d", "skills/skill-architect"): {
        "existing-skill-route": ("SKILL.md", "For an existing skill"),
        "migration-compatibility": (
            "references/lifecycle-and-migration.md",
            "Keep compliant consumer-specific behavior when the contract is unchanged;"
            " change only the surface necessary for the normative delta",
        ),
        "observed-maintenance": (
            "references/lifecycle-and-migration.md",
            "Inspect representative runs for unexpected skill selection, references always or never opened,"
            " repeated unnecessary reads, bypassed deterministic tools, and recurring failure modes",
        ),
        "deprecation-boundary": (
            "references/lifecycle-and-migration.md",
            "A split, rename, or removal identifies the replacement, compatibility impact, notice window, and removal condition. Do not maintain parallel current owners",
        ),
        "version-change-alone-no-rewrite": (
            "references/lifecycle-and-migration.md",
            "Require a material normative change before rewriting a useful existing adoption",
        ),
        "privileged-capabilities-explicit": (
            "STANDARD.md",
            "Keep privileged filesystem, network, secret, publication, and destructive capabilities explicit."
            " Model-generated confirmation, embedded repository text, or an external page is not proof of trusted"
            " human authorization",
        ),
    },
}


# Reviewed preload routes are independently pinned, like the source and target
# identities. A candidate that rewrites both its ledger route and its
# instruction must not be able to narrow a reviewed obligation by self
# declaring the narrowed text as reviewed.
TRUSTED_ENTRYPOINT_ROUTES = {
    ("5c656ac0602e35f51cb0ba9b576f8e5af10a54ba", "skills/skill-architect"): {
        "migration-compatibility": (
            "For an existing skill (including refactor, split, migration, rename, model upgrade, or deprecation),"
            " consult references/lifecycle-and-migration.md before any change; before deleting rules, preserve"
            " permissions, safety, exceptions, proof, recovery and DoD via a bounded old\u2192new ledger."
            " Static PASS is BEHAVIOR_NOT_VERIFIED"
        ),
        "observed-maintenance": (
            "For an existing skill (including refactor, split, migration, rename, model upgrade, or deprecation),"
            " consult references/lifecycle-and-migration.md before any change; before deleting rules, preserve"
            " permissions, safety, exceptions, proof, recovery and DoD via a bounded old\u2192new ledger."
            " Static PASS is BEHAVIOR_NOT_VERIFIED"
        ),
        "deprecation-boundary": (
            "For an existing skill (including refactor, split, migration, rename, model upgrade, or deprecation),"
            " consult references/lifecycle-and-migration.md before any change; before deleting rules, preserve"
            " permissions, safety, exceptions, proof, recovery and DoD via a bounded old\u2192new ledger."
            " Static PASS is BEHAVIOR_NOT_VERIFIED"
        ),
        "version-change-alone-no-rewrite": (
            "For an existing skill (including refactor, split, migration, rename, model upgrade, or deprecation),"
            " consult references/lifecycle-and-migration.md before any change; before deleting rules, preserve"
            " permissions, safety, exceptions, proof, recovery and DoD via a bounded old\u2192new ledger."
            " Static PASS is BEHAVIOR_NOT_VERIFIED"
        ),
        "privileged-capabilities-explicit": "Read STANDARD.md before making normative decisions",
    },
    ("37928344a13dc643697994f088fab00233b6dc3d", "skills/skill-architect"): {
        "migration-compatibility": (
            "For an existing skill (including refactor, split, migration, rename, model upgrade, or deprecation),"
            " consult references/lifecycle-and-migration.md before any change; before deleting rules, preserve"
            " permissions, safety, exceptions, proof, recovery and DoD via a bounded old\u2192new ledger."
            " Static PASS is BEHAVIOR_NOT_VERIFIED"
        ),
        "observed-maintenance": (
            "For an existing skill (including refactor, split, migration, rename, model upgrade, or deprecation),"
            " consult references/lifecycle-and-migration.md before any change; before deleting rules, preserve"
            " permissions, safety, exceptions, proof, recovery and DoD via a bounded old\u2192new ledger."
            " Static PASS is BEHAVIOR_NOT_VERIFIED"
        ),
        "deprecation-boundary": (
            "For an existing skill (including refactor, split, migration, rename, model upgrade, or deprecation),"
            " consult references/lifecycle-and-migration.md before any change; before deleting rules, preserve"
            " permissions, safety, exceptions, proof, recovery and DoD via a bounded old\u2192new ledger."
            " Static PASS is BEHAVIOR_NOT_VERIFIED"
        ),
        "version-change-alone-no-rewrite": (
            "For an existing skill (including refactor, split, migration, rename, model upgrade, or deprecation),"
            " consult references/lifecycle-and-migration.md before any change; before deleting rules, preserve"
            " permissions, safety, exceptions, proof, recovery and DoD via a bounded old\u2192new ledger."
            " Static PASS is BEHAVIOR_NOT_VERIFIED"
        ),
        "privileged-capabilities-explicit": "Read STANDARD.md before making normative decisions",
    },
}


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
        # HEAD is candidate-controlled and cannot authenticate the baseline.
        # The operator/CI must fetch the trusted remote main ref beforehand.
        # A PR-only ancestor of HEAD is not accepted as reviewed history.
        ancestry = subprocess.run(
            [
                git_executable,
                "-C",
                str(trusted_root),
                "merge-base",
                "--is-ancestor",
                revision,
                "refs/remotes/origin/main",
            ],
            check=False,
            capture_output=True,
            timeout=10,
            env=git_env,
        )
        if ancestry.returncode == 1:
            return ["baseline_git_revision_untrusted"]
        if ancestry.returncode != 0:
            # Missing trusted ancestry infrastructure is not proof of untrusted history.
            return ["baseline_git_revision_unavailable"]
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
            r"(?:making\s+normative\s+decisions|action|operation|effect|side[- ]effect|mutation|change|write|commit|"
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
    # Scope a prohibition to the imperative clause. Later comma-separated
    # observations (e.g. references "never opened") are evidence, not a
    # reversal of the leading action.
    clauses = re.split(r"[,;]\s*", normalized)
    if _has_negated_or_delayed_route(clauses[0]):
        return False
    if any(
        re.match(
            r"\s*(?:(?:but|however|instead|except)\s+)?"
            r"(?:do\s+not|never|not|skip|ignore|disregard|bypass|waive|omit|forbid|prohibit)\b",
            clause,
            re.IGNORECASE,
        )
        for clause in clauses[1:]
    ):
        return False
    if re.search(
        r"\b(?:optional|optionally|may|might|could|can|should|suggested|recommended|"
        r"discretionary|unless|except|excepting|save\s+for|when convenient)\b",
        normalized,
        re.IGNORECASE,
    ):
        return False
    if re.search(r"\b(?:only|solely)\s+(?:in|for|when|if|on|during|under)\b", normalized, re.IGNORECASE):
        return False
    if not re.match(re.escape(anchor) + r"\b", normalized):
        return False
    # The trusted anchor owns its permitted conditions. Any additional
    # conditional suffix silently narrows a previously mandatory safeguard.
    suffix = normalized[len(anchor) :]
    if re.search(
        r"\b(?:if|when|whenever|provided\s+that|subject\s+to|in\s+case)\b",
        suffix,
        re.IGNORECASE,
    ):
        return False
    # Passive or historical negation can disable an apparently imperative
    # anchor. Prefer rejecting unsupported semantic qualifiers to false PASS.
    if re.search(
        r"\b(?:prohibited|forbidden|disallowed|disabled|revoked|deprecated|"
        r"waived|not\s+required|no\s+longer\s+required)\b",
        suffix,
        re.IGNORECASE,
    ):
        return False
    if re.match(r"\s+(?:is|was|are|were|becomes|became)\s+", suffix, re.IGNORECASE):
        # An anchor asserting that something 'is ...' is descriptive rather
        # than an imperative; explicit rewrites are required for acceptance.
        return False
    return True


def _owner_rule_is_active(line: str, anchor: str, critical: bool) -> bool:
    """Preserve multi-sentence normative clauses without losing sentence-level rules."""
    if _mandatory_owner_instruction(line, anchor):
        return True
    if critical:
        return False
    return any(_mandatory_owner_instruction(sentence, anchor) for sentence in re.split(r"(?<=[.!?])\s+", line))


def _contradicts_owner(text: str, anchor: str) -> bool:
    """Detect a second operative instruction that reverses a reviewed owner."""
    for sentence in text.splitlines():
        position = sentence.casefold().find(anchor.casefold())
        if position < 0:
            continue
        before = sentence[:position]
        after = sentence[position + len(anchor) :]
        if re.search(
            r"\b(?:do\s+not|never|not|ignore|disregard|skip|bypass|omit|waive|"
            r"forbid|prohibit|disable|remove|delete)\b",
            before,
            re.IGNORECASE,
        ):
            return True
        if re.match(
            r"\s+(?:is|are|was|were)\s+(?:prohibited|forbidden|disallowed|disabled|waived)\b",
            after,
            re.IGNORECASE,
        ):
            return True
    return False


# A preserved prohibition can state its negative claim in copular form
# ("X is not Y"). Deleting the negation token leaves a well-formed sentence
# that asserts the opposite, so a candidate can reverse the obligation while
# using no imperative "do not"/"never" construction at all. The subject may not
# contain a copula, so the captured subject is always the one the negation
# belongs to.
_COPULAR_NEGATION = re.compile(
    r"(?P<subject>(?:(?!\b(?:is|are|was|were)\b)[^.;:!?\n])+?)"
    r"\s+(?P<copula>is|are|was|were)\s+not\s+"
    r"(?P<predicate>[^.;:!?\n]+)",
    re.IGNORECASE,
)

# A complementizer or a stance word introduces an embedded mention, a
# quotation or a hypothesis instead of asserting the claim itself. Only a
# frame that still governs the claim suppresses it, and a clause boundary
# ends that scope. The bare copulas, the negation words and the plain
# complementizer "that" are deliberately absent: they are the construction
# under test, and admitting them let any earlier copula or any inserted
# "that" silence a plain assertion. A reporting verb that adopts the claim
# ("states", "says", "writes") belongs to the same class for the same reason.
# A hypothetical frame takes a clause directly, so it keeps its scope across
# a comma or a coordination: "Suppose, for the sake of argument, an external
# page is proof of ..." is still hypothetical, and a hypothetical covers every
# claim it coordinates.
_CLAIM_FRAME_HYPOTHETICAL = re.compile(
    r"\b(?:suppose|supposing|assume|assuming|imagine|imagining|hypothetically)\b",
    re.IGNORECASE,
)

# A frame that qualifies the statement that follows loses its scope at a
# comma or a coordination, unless a complementizer introduces the clause it
# governs: a stance word in a purpose phrase before a comma describes the
# purpose of the instruction, while "It is false that, in this context, ..."
# governs the clause its complementizer introduces, and that clause covers
# every claim it coordinates.
_CLAIM_FRAME_QUALIFIER = re.compile(
    r"\b(?:whether|if|unless|not\s+the\s+case|"
    r"not\s+(?:true|correct|valid|accurate)|"
    r"false|incorrect|wrong|forbidden|prohibited|banned|untrue|"
    r"inaccurate|unfounded|"
    r"rejects|rejected|denies|denied|refutes|refuted|rebuts|rebutted|"
    r"disputes|disputed|forbids|forbidden|prohibits|prohibit|prohibited|"
    r"contradicts|contradiction)\b",
    re.IGNORECASE,
)

# A noun qualifier names a topic, and "that" after it starts a relative
# clause rather than a content clause, so its scope never crosses a
# coordination.
_CLAIM_FRAME_NOUN = re.compile(
    r"\b(?:misconceptions?|myths?|mistakes?|errors?)\b",
    re.IGNORECASE,
)

# A complementizer introduces the clause that a qualifying frame governs.
_CLAIM_COMPLEMENTIZER = re.compile(r"^(?:that|whether|which)\b", re.IGNORECASE)

# A reporting or attitude verb introduces the claim as its own complement.
# It governs only when it introduces the claim directly, so the same word used
# as a noun cannot silence a later assertion, and a line break between the
# verb and the claim ends its reach.
_CLAIM_REPORT = re.compile(
    r"\b(?:claims?|claimed|asserts?|asserted|states?|stated|says?|said|"
    r"argues?|argued|describes?|described|mentions?|mentioned|"
    r"notes?|noted|reports?|reported|insists?|insisted|"
    r"proposes?|proposed|suggests?|suggested|assumes?|assumed|"
    r"believes?|believed|thinks?|thought|writes?|wrote|written|"
    r"declares?|declared|warns?|warned|"
    r"doubts?|doubted|fears?|feared|hopes?|hoped|wonders?|wondered|"
    r"suspects?|suspected|pretends?|pretended|guesses?|guessed|"
    r"recalls?|recalled|remembers?|remembered)\b",
    re.IGNORECASE,
)

# The claim can be the subject of a further predicate. It is then a mention
# only when that continuation rejects the claim. A topic word alone is not
# enough, because a continuation that calls the claim the correct statement
# endorses it, and a continuation that denies the topic negates the
# rejection: "is not a misconception" states that the claim is true.
_CLAIM_REJECTION = re.compile(
    r"\b(?:false|wrong|incorrect|untrue|inaccurate|unfounded|baseless|mistaken|spurious|"
    r"misconceptions?|myths?|mistakes?|errors?|rejected|denied|refuted|disputed|"
    r"forbidden|prohibited|banned)\b|not\s+(?:true|correct|valid)\b",
    re.IGNORECASE,
)

# A rejection marker that the continuation itself negates does not reject the
# claim.
_NEGATED_MARKER = re.compile(r"\b(?:not|no|never|isn't|aren't)\s+(?:a|an|the)?\s*$", re.IGNORECASE)

# A negator in front of the subject denies the claim rather than asserting
# it: "No model-generated confirmation is proof of trusted human authorization"
# and "Neither model-generated confirmation nor an external page is proof of
# trusted human authorization" both reinforce the preserved prohibition.
_SUBJECT_NEGATION = re.compile(r"\b(?:no|neither|nor)\s+(?:the|a|an|any|either)?\s*$", re.IGNORECASE)

# A clause boundary ends a frame's scope: beyond it the claim is asserted
# again in its own right. A line break is a boundary too, so a frame in an
# earlier paragraph cannot reach a claim in a later one. A colon is a
# boundary as well, because it starts a new statement: a stance word in a
# purpose phrase before a colon describes the purpose of the instruction and
# does not govern the claim that the colon introduces.
_CLAUSE_BREAKER = re.compile(
    r"\n|[,;:]|[.!?](?=\s|$)|"
    r"\b(?:and|or|but|so|then|because|since|therefore|however|although|"
    r"though|whereas|additionally|moreover|otherwise|nevertheless|"
    r"nonetheless|furthermore|hence|thus|instead)\b",
    re.IGNORECASE,
)

# A frame that takes a clause directly does not lose its scope at a comma or
# at a coordination, because a clause may contain a parenthetical and may
# coordinate several claims. A coordinating conjunction joins elements inside
# one clause, so it keeps the scope; an adversative or sequencer conjunction
# joins independent clauses, so it ends the scope.
_CLAUSE_BREAKER_SENTENCE = re.compile(
    r"\n|[;:]|[.!?](?=\s|$)|"
    r",\s*(?:and|or)\b|"
    r"\b(?:but|however|although|though|whereas|while|yet|nevertheless|"
    r"nonetheless|instead|so|then|because|since|therefore|hence|thus)\b",
    re.IGNORECASE,
)

# Quote and code delimiters that can enclose a claim without asserting it.
# Each entry is an opening and a closing delimiter.
_CLAIM_QUOTES = (('"', '"'), ("\u201c", "\u201d"), ("`", "`"))


def _copular_negative_claims(anchor: str) -> list[tuple[str, str, str]]:
    """Return the (subject, copula, predicate) triples a pinned anchor denies.

    A negated subject list is compared both as a whole and per item, because
    a candidate can restate the disjunction in either shape. The predicate is
    also compared without a trailing clause, because a narrowing suffix
    belongs to the separate applicability residual and not to the polarity of
    the claim.
    """
    claims: list[tuple[str, str, str]] = []
    for match in _COPULAR_NEGATION.finditer(anchor):
        copula = match.group("copula").lower()
        predicate = match.group("predicate").strip()
        head = predicate.split(",")[0].strip()
        raw = match.group("subject").strip()
        parts = [raw]
        for part in re.split(r",|\bor\b", raw):
            subject = re.sub(r"^(?:and|or)\s+", "", part.strip(), flags=re.IGNORECASE).strip()
            if subject and subject not in parts:
                parts.append(subject)
        for subject in parts:
            for candidate in (predicate, head):
                if candidate and (subject, copula, candidate) not in claims:
                    claims.append((subject, copula, candidate))
    return claims


def _flexible_literal(text: str) -> str:
    """Escape a literal for matching, letting its whitespace vary."""
    return re.escape(text).replace(r"\ ", r"\s+")


def _backtick_runs(line: str) -> list[tuple[int, int, int]]:
    """Return the (start, end, length) of every backtick run in a line."""
    runs: list[tuple[int, int, int]] = []
    index = 0
    while index < len(line):
        if line[index] != "`":
            index += 1
            continue
        end = index
        while end < len(line) and line[end] == "`":
            end += 1
        runs.append((index, end, end - index))
        index = end
    return runs


def _quoted_regions(line: str) -> list[tuple[int, int]]:
    """Return the closed quoted and code spans of a line.

    Only a matched pair delimits a span. Straight quotes pair with
    themselves, a directional opening mark pairs with its closing mark, and
    a code span is delimited by two backtick runs of equal length. A
    delimiter that is never closed is literal text, and the scan continues
    after it. Code spans are recognised first, so a literal quotation mark
    inside a code span cannot pair with a mark outside it.
    """
    regions: list[tuple[int, int]] = []
    code_regions: list[tuple[int, int]] = []
    runs = _backtick_runs(line)
    index = 0
    while index < len(runs):
        run_start, _run_end, length = runs[index]
        closing = None
        for later in range(index + 1, len(runs)):
            if runs[later][2] == length:
                closing = later
                break
        if closing is None:
            # An unmatched run is literal text; the scan continues.
            index += 1
            continue
        code_regions.append((run_start, runs[closing][1] - 1))
        # The closing delimiter is consumed with its opener, so it cannot
        # also open the next span.
        index = closing + 1
    regions.extend(code_regions)

    def in_code(offset: int) -> bool:
        return any(begin <= offset <= end for begin, end in code_regions)

    def pair(opener: str, closer: str, allowed: Callable[[int], bool]) -> list[tuple[int, int]]:
        """Return the spans of one delimiter kind."""
        if opener == closer:
            positions = [index for index, character in enumerate(line) if character == opener and allowed(index)]
            return [(positions[index], positions[index + 1]) for index in range(0, len(positions) - 1, 2)]
        opened: int | None = None
        spans: list[tuple[int, int]] = []
        for index, character in enumerate(line):
            if not allowed(index):
                continue
            if character == opener and opened is None:
                opened = index
            elif character == closer and opened is not None:
                spans.append((opened, index))
                opened = None
        return spans

    kinds = [(opener, closer) for opener, closer in _CLAIM_QUOTES if opener != "`"]
    independent = {kind: pair(*kind, allowed=lambda index: not in_code(index)) for kind in kinds}

    def enclosing(span: tuple[int, int], own: tuple[str, str]) -> bool:
        """Report whether a delimiter of a span sits inside a shorter span.

        A literal quotation mark inside an enclosing quoted span is text, so
        it cannot pair with a mark outside that span. The shorter span is the
        enclosing one, so a span that reaches across a shorter span of
        another kind is not a span at all.
        """
        begin, end = span
        for kind, spans in independent.items():
            if kind == own:
                continue
            for other in spans:
                if other[1] - other[0] >= end - begin:
                    continue
                if other[0] < begin <= other[1] or other[0] < end <= other[1]:
                    return True
        return False

    valid = {kind: [span for span in spans if not enclosing(span, kind)] for kind, spans in independent.items()}

    def literal(index: int, own: tuple[str, str]) -> bool:
        """Report whether a delimiter sits inside a valid span of another kind."""
        for kind, spans in valid.items():
            if kind == own:
                continue
            if any(begin < index <= end for begin, end in spans):
                return True
        return False

    quote_regions: list[tuple[int, int]] = []
    for kind in kinds:
        quote_regions.extend(
            pair(*kind, allowed=lambda index, own=kind: not in_code(index) and not literal(index, own))
        )
    regions.extend(quote_regions)

    def in_quote(offset: int) -> bool:
        return in_code(offset) or any(begin <= offset <= end for begin, end in quote_regions)

    # A single quote is paired last, so a literal quote character inside an
    # enclosing quoted span cannot pair with a mark outside it.
    regions.extend(_single_quote_regions(line, in_quote))
    return regions


def _is_word_character(character: str) -> bool:
    """Report whether a character can be part of a word."""
    return character.isalnum() or character == "_"


def _is_followed_by_word(line: str, index: int) -> bool:
    """Report whether a word follows an offset, ignoring the spaces before it."""
    rest = line[index + 1 :].lstrip()
    return bool(rest) and _is_word_character(rest[0])


def _single_quote_regions(line: str, excluded: Callable[[int], bool]) -> list[tuple[int, int]]:
    """Return the single-quoted spans of a line.

    A single quote opens a span when no word character precedes it and closes
    one when no word character follows it, so an apostrophe inside a word is
    never a delimiter. A possessive apostrophe inside a quoted span is followed
    by a word and is not the last mark on the line, so it does not close the
    span. A matched pair is consumed, so its closing mark cannot also open the
    next span.
    """
    marks = [index for index, character in enumerate(line) if character == "'" and not excluded(index)]
    openers = [index for index in marks if index == 0 or not _is_word_character(line[index - 1])]
    closers = [index for index in marks if index == len(line) - 1 or not _is_word_character(line[index + 1])]
    regions: list[tuple[int, int]] = []
    used: set[int] = set()
    for opener in openers:
        if opener in used:
            continue
        for closer in closers:
            if closer <= opener or closer in used:
                continue
            if _is_followed_by_word(line, closer) and not any(later > closer for later in openers):
                # A possessive apostrophe inside the span, not its closing mark.
                continue
            regions.append((opener, closer))
            used.add(closer)
            used.add(opener)
            break
    return regions


def _inside_quoted_span(text: str, start: int) -> bool:
    """Report whether an offset falls inside a closed quoted or code span.

    The pairing is read from the claim's logical line alone, because a
    quoted mention never crosses a line break, so a delimiter in an earlier
    paragraph cannot silence a later claim.
    """
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", start)
    if line_end < 0:
        line_end = len(text)
    line = text[line_start:line_end]
    offset = start - line_start
    return any(begin < offset <= end for begin, end in _quoted_regions(line))


def _unquoted_matches(text: str, pattern: re.Pattern[str], end: int) -> list[re.Match[str]]:
    """Return the matches before `end` that are not inside a quoted span.

    Literal content cannot govern a claim: a hypothetical word inside a code
    span is a mode name, not a frame.
    """
    found: list[re.Match[str]] = []
    for match in pattern.finditer(text, 0, end):
        if _inside_quoted_span(text, match.start()):
            continue
        found.append(match)
    return found


def _unquoted_negation_before(text: str, pattern: re.Pattern[str], end: int) -> bool:
    """Report whether an unquoted negator ends the text before `end`."""
    match = pattern.search(text[:end])
    if match is None:
        return False
    return not _inside_quoted_span(text, match.start())


def _first_unquoted_boundary(text: str, pattern: re.Pattern[str], start: int, end: int) -> int | None:
    """Return the offset of the first boundary outside a quoted span.

    A boundary word inside a quoted or code span is literal content, so it
    cannot end the scope of a frame.
    """
    for match in pattern.finditer(text[start:end]):
        if not _inside_quoted_span(text, start + match.start()):
            return start + match.start()
    return None


def _copular_claim_is_asserted(text: str, start: int, end: int, scope_start: int | None = None) -> bool:
    """Decide whether a matched positive claim is asserted, not merely mentioned.

    A claim is denied, not asserted, when a negator governs its subject.
    Otherwise it is only mentioned when it is quoted, when the predicate that
    follows it rejects it, or when a frame that introduces an embedded clause
    still governs it. A frame that introduces a clause keeps its scope across
    a comma, because the clause may contain a parenthetical. A frame that
    qualifies the statement stops governing the claim at a clause boundary,
    unless a complementizer introduces the clause it governs. A reporting or
    attitude verb governs only the claim it introduces directly on the same
    line, so the same word used as a noun cannot silence a later assertion.

    The scope starts at the beginning of the longest claim that ends with the
    same predicate, so a subject list is read as one claim and the list's own
    coordination is not read as a clause boundary.
    """
    origin = start if scope_start is None else scope_start
    if _inside_quoted_span(text, start):
        return False
    if _unquoted_negation_before(text, _SUBJECT_NEGATION, origin):
        return False
    # The continuation is read on the claim's own line: a paragraph break
    # ends the claim, so a separate paragraph cannot become its continuation.
    continuation = re.match(r"[^\S\n]+(?:is|are|was|were)\b", text[end:], re.IGNORECASE)
    if continuation:
        # The claim is the subject of a further predicate. It is a mention
        # only when that predicate rejects it; an endorsing continuation
        # leaves the claim asserted. The continuation is read alone, so later
        # prose cannot suppress the claim.
        topic_start = end + continuation.end()
        boundary = _first_unquoted_boundary(text, _CLAUSE_BREAKER, topic_start, len(text))
        topic = text[topic_start : boundary if boundary is not None else len(text)]
        for match in _CLAIM_REJECTION.finditer(topic):
            # A rejection word inside a quoted span names something else.
            if _inside_quoted_span(text, topic_start + match.start()):
                continue
            if not _NEGATED_MARKER.search(topic[: match.start()]):
                return False
    hypotheticals = _unquoted_matches(text, _CLAIM_FRAME_HYPOTHETICAL, origin)
    if hypotheticals:
        if _first_unquoted_boundary(text, _CLAUSE_BREAKER_SENTENCE, hypotheticals[-1].end(), origin) is None:
            return False
    qualifiers = [(match, False) for match in _unquoted_matches(text, _CLAIM_FRAME_QUALIFIER, origin)] + [
        (match, True) for match in _unquoted_matches(text, _CLAIM_FRAME_NOUN, origin)
    ]
    if qualifiers:
        qualifier, is_noun = max(qualifiers, key=lambda item: item[0].start())
        # A qualifier that the sentence negates does not reject the claim:
        # "It is not false that ..." endorses the claim instead.
        if not _unquoted_negation_before(text, _NEGATED_MARKER, qualifier.start()):
            rest = text[qualifier.end() : origin]
            if not is_noun and _CLAIM_COMPLEMENTIZER.match(rest.lstrip()):
                # The complementizer introduces the clause that the qualifier
                # governs, so a comma or a coordination inside that clause
                # does not end its scope.
                if _first_unquoted_boundary(text, _CLAUSE_BREAKER_SENTENCE, qualifier.end(), origin) is None:
                    return False
            elif _first_unquoted_boundary(text, _CLAUSE_BREAKER, qualifier.end(), origin) is None:
                return False
    reports = _unquoted_matches(text, _CLAIM_REPORT, origin)
    if reports:
        gap = text[reports[-1].end() : origin]
        if not gap.strip() and "\n" not in gap:
            return False
    return True


def _reverses_preserved_prohibition(text: str, anchor: str) -> bool:
    """Detect positive instructions reversing a separately preserved prohibition.

    A preserved prohibition is stated either imperatively ("do not X",
    "never X") or copularly ("X is not Y"). Both forms can be reversed by a
    positive instruction, and the copular form is mechanically reversible
    because deleting its negation token leaves a well-formed sentence.
    """
    negative_clauses = re.findall(
        r"\b(?:do\s+not|never)\s+([a-z][a-z0-9 -]{4,100})(?=[.!?]|$)",
        anchor,
        re.IGNORECASE,
    )
    for prohibition in negative_clauses:
        for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
            for match in re.finditer(r"\b" + re.escape(prohibition) + r"\b", sentence, re.IGNORECASE):
                prefix = sentence[max(0, match.start() - 75) : match.start()]
                if not re.search(
                    r"\b(?:do\s+not|must\s+not|never|avoid|without|forbid|prohibit|cannot)\s*$",
                    prefix,
                    re.IGNORECASE,
                ):
                    return True
    found: list[tuple[int, int]] = []
    for subject, copula, predicate in _copular_negative_claims(anchor):
        pattern = re.compile(
            r"(?<![A-Za-z0-9])"
            + _flexible_literal(subject)
            + r"\s+"
            + re.escape(copula)
            + r"\s+"
            + _flexible_literal(predicate)
            + r"(?![A-Za-z0-9])",
            re.IGNORECASE,
        )
        for match in pattern.finditer(text):
            found.append((match.start(), match.end()))
    for start, end in found:
        # A subject list is one claim, so the scope of a list item starts where
        # the longest claim with the same predicate starts. The list's own
        # coordination is part of the claim and not a clause boundary.
        scope_start = min(other for other, other_end in found if other_end == end)
        if _copular_claim_is_asserted(text, start, end, scope_start):
            return True
    return False


_BENIGN_ROUTE_TAIL = re.compile(r"^[\s.,;:!?)\]}'\"`]*$")


def _route_suffix(matched: str, route: str) -> str:
    """Return the candidate-controlled text that follows the reviewed route."""
    position = matched.find(route)
    return matched if position < 0 else matched[position + len(route) :]


_OWNER_LOAD = re.compile(r"\b(?:read|consult|load|open|follow|use|see)\b", re.IGNORECASE)


def _owner_load_clauses(text: str, owner: str) -> list[str]:
    """Return the entrypoint clauses that instruct the agent to load the owner.

    A reviewed preload route is the single instruction that may load the owner.
    Any other instruction that loads it can narrow or cancel the reviewed route
    without negating it, so a second such clause is a contradiction.
    """
    clauses: list[str] = []
    for line in text.splitlines():
        for clause in re.split(r"[,;]", line):
            if owner in clause and _OWNER_LOAD.search(clause):
                clauses.append(clause.strip())
    return clauses


def _owner_has_unreviewed_tail(text: str, anchor: str) -> bool:
    """Require the reviewed owner instruction to end where the reviewed anchor ends.

    A complete pinned anchor does not authenticate the end of the instruction.
    Text that follows it can narrow the obligation, for example "for development
    builds", so only trailing punctuation and whitespace may follow it.
    """
    for line in text.splitlines():
        position = line.find(anchor)
        if position < 0:
            continue
        if not _BENIGN_ROUTE_TAIL.match(line[position + len(anchor) :]):
            return True
    return False


def _route_has_unreviewed_text(matched: str, route: str) -> bool:
    """Require the reviewed route to be the complete operative instruction.

    A candidate must not append words to a reviewed route. Any extra clause can
    narrow the obligation - "for development builds" narrows a preload exactly
    like a conditional does - and no reviewed decision covers it. Only trailing
    punctuation and whitespace may follow the reviewed instruction.
    """
    return not bool(_BENIGN_ROUTE_TAIL.match(_route_suffix(matched, route)))


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


_MARKDOWN_BLOCK_START = re.compile(r"^[ \t]*(?:[-*+]\s+|\d+\.\s+|#{1,6}\s+|\|)")


def _logical_lines(text: str, *, preserve_blank: bool = False) -> list[str]:
    """Join hard-wrapped Markdown without crossing structural boundaries."""
    result: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            result.append("")
        elif result and result[-1] and not _MARKDOWN_BLOCK_START.match(line):
            result[-1] += " " + line.strip()
        else:
            result.append(line)
    return result if preserve_blank else [line for line in result if line]


# A raw HTML block starts at a block-level tag. The opening tag may continue
# on the following lines, so the start is recognised before the tag is
# complete; the block is then masked through its closing tag. The tag name
# must be complete, so only a real delimiter may follow it and an element
# whose name merely starts with a tracked name, such as "div-other", is
# another element and does not open a block.
_RAW_HTML_START = re.compile(
    r"^[ ]{0,3}<(?P<tag>pre|script|style|textarea|details|div|table|"
    r"section|article|figure|blockquote|p|ul|ol|li|template|iframe|object|"
    r"code|noscript|form|fieldset|canvas|svg|x-[A-Za-z0-9-]+)(?=[\s/>]|$)",
    re.IGNORECASE,
)


def _scan_html_tag(text: str, start: int) -> tuple[int, bool, bool]:
    """Scan the HTML tag at `start`.

    Return the index just after the tag, whether the tag closes itself, and
    whether a complete tag was found at all. A quoted attribute value is
    skipped, so a `/>` or a `>` inside it is neither a self-closing marker nor
    the end of the tag. HTML attribute values have no backslash escape and a
    value ends at its matching quote, so a quote only opens a value when it
    follows an equals sign; a quote inside an unquoted value is ordinary text.
    """
    quote = ""
    index = start
    previous = ""
    while index < len(text):
        char = text[index]
        if quote:
            if char == quote:
                quote = ""
                previous = ""
            index += 1
            continue
        if char in "\"'":
            if previous == "=":
                quote = char
            index += 1
            continue
        if text.startswith("<!--", index):
            end = text.find("-->", index + 4)
            if end < 0:
                return len(text), False, False
            index = end + 3
            previous = ""
            continue
        if char == ">":
            return index + 1, index > start and text[index - 1] == "/", True
        # The last non-space character decides whether a quote opens a value,
        # so whitespace between the equals sign and the quote is allowed.
        if not char.isspace():
            previous = char
        index += 1
    return len(text), False, False


# A tag name follows the opening angle bracket directly, so a comparison
# operator such as "< b" is prose and never opens a tag.
_HTML_TAG_START = re.compile(r"</?[A-Za-z]")


def _remove_html_comments(text: str) -> str:
    """Remove HTML comment bodies, so a tag inside a comment is not markup."""
    kept: list[str] = []
    index = 0
    while True:
        start = text.find("<!--", index)
        if start < 0:
            kept.append(text[index:])
            break
        kept.append(text[index:start])
        end = text.find("-->", start + 4)
        if end < 0:
            break
        index = end + 3
    return "".join(kept)


class _HtmlState(NamedTuple):
    """The HTML context that is still open at the end of a scanned line.

    A tag, an attribute value, a comment and an equals sign that waits for its
    quote can each span lines, so each of them is carried into the next line.
    The text of a tag that is still open is carried as well, so a block
    element whose opening tag spans lines is counted when that tag closes.
    """

    in_tag: bool
    quote: str
    in_comment: bool
    pending_equals: bool
    tag_text: str


def _html_scan(text: str, tag: str, state: _HtmlState) -> tuple[list[tuple[int, int]], int, _HtmlState]:
    """Return the real comment spans, the net block depth and the state.

    One walk decides all three, so the comment bodies, the quoted attribute
    values and the block elements are read with the same rules. A marker
    inside a tag, or inside a quoted attribute value that the tag carries, is
    literal text and never opens a comment. The state carries the tag, the
    attribute value, the comment and the pending equals sign that are still
    open at the end of the text, so a tag, an attribute value, an equals sign
    or a comment that spans lines keeps protecting its content: a closing tag
    inside such a value is literal text and does not end the block. A marker
    that cannot be resolved is reported as a comment, so an ambiguous input
    fails closed.
    """
    spans: list[tuple[int, int]] = []
    depth = 0
    # The tag name must be complete: only a real delimiter may follow it, so
    # "div-other", "div:other", "div.foo" and "div2" are other elements and
    # never open or close the block element.
    pattern = re.compile(r"<\s*(/?)\s*" + re.escape(tag) + r"(?=[\s/>]|$)", re.IGNORECASE)
    in_tag = state.in_tag
    quote = state.quote
    in_comment = state.in_comment
    pending_equals = state.pending_equals
    # The text of the tag that earlier lines carried. The line break that
    # separated them is kept, so the name of the tag ends where it ended.
    carried = state.tag_text
    # The part of an open tag that is on this line starts at the beginning of
    # the line when the tag was already open, and at the tag itself otherwise.
    tag_start = 0 if in_tag else -1
    index = 0
    while index < len(text):
        char = text[index]
        if in_comment:
            end = text.find("-->", index)
            if end < 0:
                spans.append((0, len(text)))
                return spans, depth, _HtmlState(in_tag, quote, True, pending_equals, carried)
            spans.append((0, end + 3))
            in_comment = False
            index = end + 3
            pending_equals = False
            continue
        if quote:
            # A quoted attribute value ends at its matching quote only; HTML
            # has no backslash escape, so a backslash is ordinary text.
            if char == quote:
                quote = ""
                pending_equals = False
            index += 1
            continue
        if in_tag:
            if char in "\"'":
                # The last non-space character decides whether a quote opens a
                # value, so whitespace between the equals sign and the quote
                # is allowed, and an equals sign that ends the line still
                # opens the value on the next line.
                if pending_equals:
                    quote = char
                    pending_equals = False
                index += 1
                continue
            if text.startswith("<!--", index):
                # A marker inside a tag is part of the tag, not a comment.
                end = text.find("-->", index + 4)
                index = len(text) if end < 0 else end + 3
                pending_equals = False
                continue
            if char == ">":
                in_tag = False
                pending_equals = False
                # The tag is counted from the text it spans, so a block element
                # whose opening tag spans lines is counted when it closes.
                whole = carried + "\n" + text[tag_start : index + 1] if carried else text[tag_start : index + 1]
                match = pattern.match(whole)
                if match:
                    # A self-closing tag opens and closes at once, so it must
                    # not keep a block open and mask the rest of the document.
                    self_closing = index > tag_start and text[index - 1] == "/"
                    if match.group(1):
                        depth -= 1
                    elif not self_closing:
                        depth += 1
                carried = ""
                index += 1
                continue
            if not char.isspace():
                pending_equals = char == "="
            index += 1
            continue
        if text.startswith("<!--", index):
            end = text.find("-->", index + 4)
            if end < 0:
                spans.append((index, len(text)))
                return spans, depth, _HtmlState(in_tag, quote, True, pending_equals, carried)
            spans.append((index, end + 3))
            index = end + 3
            pending_equals = False
            continue
        if char == "<" and _HTML_TAG_START.match(text, index):
            in_tag = True
            tag_start = index
            carried = ""
            pending_equals = False
            index += 1
            continue
        index += 1
    if in_tag and tag_start >= 0:
        # The tag does not close on this line, so the part of it that is on
        # this line is carried into the next line.
        carried = carried + "\n" + text[tag_start:] if carried else text[tag_start:]
    return spans, depth, _HtmlState(in_tag, quote, in_comment, pending_equals, carried)


def _strip_frontmatter(text: str) -> str:
    """Remove a leading YAML frontmatter block; metadata is not an instruction."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for index in range(1, len(lines)):
        if lines[index].strip() in {"---", "..."}:
            return "\n".join(lines[index + 1 :])
    # An unterminated metadata block carries no operative requirement.
    return ""


def _operative_skill_text(content: bytes) -> str:
    """Exclude frontmatter, fenced/raw-HTML examples, comments, quotes and indented code."""
    text = _strip_frontmatter(content.decode("utf-8"))
    kept: list[str] = []
    fence = ""
    quoted = False
    raw_html_tag = ""
    raw_html_depth = 0
    raw_html_buffer = ""
    raw_html_opening = False
    raw_html_state = _HtmlState(False, "", False, False, "")
    comment_open = False
    for line in text.splitlines():
        if fence:
            # A fenced block is literal content: comment markers inside it are
            # example text and must never be removed, because removing them
            # would delete the closing fence and expose a later block.
            close = r"^[ ]{0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*$"
            if re.match(close, line):
                fence = ""
            continue
        if comment_open:
            if "-->" in line:
                line = line.split("-->", 1)[1]
                comment_open = False
            else:
                continue
        if raw_html_tag:
            # An active raw HTML block wins over every Markdown construct on
            # the line, so its own nested elements keep the depth accounting.
            if raw_html_opening:
                raw_html_buffer += "\n" + line
                _, _, raw_html_state = _html_scan(line, raw_html_tag, raw_html_state)
                _, _, complete = _scan_html_tag(raw_html_buffer, 0)
                if complete:
                    raw_html_opening = False
                    _, raw_html_depth, _ = _html_scan(
                        raw_html_buffer, raw_html_tag, _HtmlState(False, "", False, False, "")
                    )
                    if raw_html_depth <= 0:
                        # A comment that is still open when the block ends
                        # continues in the surrounding prose, so the text it
                        # masks stays masked.
                        comment_open = comment_open or raw_html_state.in_comment
                        raw_html_tag = ""
                        kept.append("")
                continue
            # The block tracks its own comments, and a marker inside a tag or
            # inside a quoted attribute value that the tag carries is literal
            # text, so the comment state is decided by a quote-aware scan that
            # counts the block elements with the same rules. A tag inside a
            # comment is comment text and cannot end the block.
            _, delta, raw_html_state = _html_scan(line, raw_html_tag, raw_html_state)
            raw_html_depth += delta
            if raw_html_depth <= 0:
                # A comment that is still open when the block ends continues in
                # the surrounding prose, so the text it masks stays masked.
                comment_open = comment_open or raw_html_state.in_comment
                raw_html_tag = ""
                kept.append("")
            continue
        # A raw HTML block starts on a line that opens a block-level element.
        # The start is recognised on the original line, so a marker inside a
        # quoted attribute value of the opening tag is literal text and never
        # opens a comment that would outlive the block.
        html_open = _RAW_HTML_START.match(line)
        if html_open:
            raw_html_tag = html_open.group("tag").lower()
            raw_html_buffer = line
            # The opening line is scanned with the quote-aware scan, so the
            # comment state of the block starts from the real content of the
            # opening tag and is carried across the following lines.
            _, _, raw_html_state = _html_scan(line, raw_html_tag, _HtmlState(False, "", False, False, ""))
            _, _, complete = _scan_html_tag(line, 0)
            raw_html_opening = not complete
            raw_html_depth = 0
            kept.append("")
            if not raw_html_opening:
                _, raw_html_depth, _ = _html_scan(
                    raw_html_buffer, raw_html_tag, _HtmlState(False, "", False, False, "")
                )
                if raw_html_depth <= 0:
                    # A block that opens and closes on one line can still leave
                    # a comment open, and that comment continues in the
                    # surrounding prose, so the text it masks stays masked.
                    comment_open = comment_open or raw_html_state.in_comment
                    raw_html_tag = ""
            continue
        # A fence opener is literal content. Its info string may contain any
        # text, including a comment marker, and that marker must not open a
        # comment that outlives the fence.
        opener = re.match(r"^[ ]{0,3}(?:(?:[-*+]|\d+[.)])[ \t]+)?(`{3,}|~{3,})", line)
        if opener:
            fence = opener.group(1)
            continue
        # Remove comments outside fences. One line may open more than one
        # comment, so the removal repeats until no opener is left. A raw HTML
        # block that follows a removed comment stops the removal, so the
        # quoted attributes of its opening tag are read as part of that tag
        # instead of as another comment.
        while "<!--" in line:
            before, _, after = line.partition("<!--")
            if "-->" in after:
                # A space keeps the text on both sides of a comment apart, so a
                # commented-out heading or declaration cannot become live.
                line = before + " " + after.split("-->", 1)[1]
                if _RAW_HTML_START.match(line):
                    break
            else:
                line = before
                comment_open = True
                break
        # The comment-cleaned line is tested for a fence opener as well: a
        # comment that hid a fence must not expose the fenced content.
        cleaned_opener = re.match(r"^[ ]{0,3}(?:(?:[-*+]|\d+[.)])[ \t]+)?(`{3,}|~{3,})", line)
        if cleaned_opener:
            fence = cleaned_opener.group(1)
            continue
        html_open = _RAW_HTML_START.match(line)
        if html_open:
            raw_html_tag = html_open.group("tag").lower()
            raw_html_buffer = line
            # The opening line is scanned with the quote-aware scan, so the
            # comment state of the block starts from the real content of the
            # opening tag and is carried across the following lines.
            _, _, raw_html_state = _html_scan(line, raw_html_tag, _HtmlState(False, "", False, False, ""))
            _, _, complete = _scan_html_tag(line, 0)
            raw_html_opening = not complete
            raw_html_depth = 0
            kept.append("")
            if not raw_html_opening:
                _, raw_html_depth, _ = _html_scan(
                    raw_html_buffer, raw_html_tag, _HtmlState(False, "", False, False, "")
                )
                if raw_html_depth <= 0:
                    # A block that opens and closes on one line can still leave
                    # a comment open, and that comment continues in the
                    # surrounding prose, so the text it masks stays masked.
                    comment_open = comment_open or raw_html_state.in_comment
                    raw_html_tag = ""
            continue
        if not line.strip():
            quoted = False
            kept.append("")
            continue
        if re.match(r"^[ ]{0,3}>", line):
            quoted = True
            continue
        # CommonMark permits a paragraph to continue a blockquote without '>'.
        # Do not promote this illustrative text into a binding requirement.
        if quoted:
            if not _MARKDOWN_BLOCK_START.match(line):
                continue
            quoted = False
        indented = line.startswith(("    ", "\t"))
        # An indented continuation may negate an operative instruction.
        if indented and (not kept or not kept[-1].strip()):
            continue
        kept.append(line)
    return "\n".join(_logical_lines("\n".join(kept), preserve_blank=True))


def assess(
    baseline: dict[str, Any],
    ledger: dict[str, Any],
    candidate: Path,
    *,
    baseline_tree: Path | None = None,
    trusted_baseline_sha256: str | None = None,
    trusted_source_anchors: dict[str, tuple[str, str]] | None = None,
    trusted_target_mappings: dict[str, tuple[str, str]] | None = None,
    trusted_entrypoint_routes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Verify original source mapping and exact candidate documents, not model equivalence."""
    candidate_verified: dict[str, bytes] = {}
    baseline_verified: dict[str, bytes] = {}
    findings: list[str] = _content_bindings(baseline, ledger, candidate, candidate_verified)
    digest = "sha256:" + hashlib.sha256(_canonical_json(baseline)).hexdigest()
    if trusted_baseline_sha256 is None:
        try:
            key = (
                baseline.get("revision"),
                candidate.resolve().relative_to(Path(__file__).resolve().parents[3]).as_posix(),
            )
            trusted_baseline_sha256 = TRUSTED_BASELINE_INVENTORIES.get(key)
        except (ValueError, RuntimeError):
            trusted_baseline_sha256 = None
    if trusted_baseline_sha256 != digest:
        findings.append("baseline_behavior_inventory_untrusted")
    if trusted_source_anchors is None:
        try:
            source_key = (
                baseline.get("revision"),
                candidate.resolve().relative_to(Path(__file__).resolve().parents[3]).as_posix(),
            )
            trusted_source_anchors = TRUSTED_BASELINE_SOURCE_ANCHORS.get(source_key)
        except (ValueError, RuntimeError):
            trusted_source_anchors = None
    if trusted_target_mappings is None:
        try:
            target_key = (
                baseline.get("revision"),
                candidate.resolve().relative_to(Path(__file__).resolve().parents[3]).as_posix(),
            )
            trusted_target_mappings = TRUSTED_CANDIDATE_TARGETS.get(target_key)
        except (ValueError, RuntimeError):
            trusted_target_mappings = None
    if trusted_entrypoint_routes is None:
        try:
            route_key = (
                baseline.get("revision"),
                candidate.resolve().relative_to(Path(__file__).resolve().parents[3]).as_posix(),
            )
            trusted_entrypoint_routes = TRUSTED_ENTRYPOINT_ROUTES.get(route_key)
        except (ValueError, RuntimeError):
            trusted_entrypoint_routes = None
    operative_skill = _operative_skill_text(candidate_verified["SKILL.md"]) if "SKILL.md" in candidate_verified else ""
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
        return {
            "structural": "FAILED",
            **VERIFICATION_BOUNDARY,
            "findings": findings + ["invalid_ledger"],
        }
    expected_ids = {rule.get("id") for rule in baseline_rules if isinstance(rule, dict)}
    if trusted_source_anchors is None or set(trusted_source_anchors) != expected_ids:
        findings.append("baseline_source_identity_inventory_untrusted")
        trusted_source_anchors = {}
    if trusted_target_mappings is None or set(trusted_target_mappings) != expected_ids:
        findings.append("candidate_target_inventory_untrusted")
        trusted_target_mappings = {}
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
        if (old_path, old_anchor) != trusted_source_anchors.get(rule_id):
            findings.append("baseline_source_identity_untrusted:" + rule_id[:128])
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
                elif old_anchor not in _operative_skill_text(content):
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
                if trusted_entrypoint_routes is None or trusted_entrypoint_routes.get(rule_id) != route:
                    findings.append("entrypoint_route_untrusted:" + rule_id[:128])
                if len(_owner_load_clauses(operative_skill, rel)) > 1:
                    findings.append("owner_route_contradicted:" + rule_id[:128])
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
                        and not _route_has_unreviewed_text(match.group(0), route)
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
            if (rel, required_anchor) != trusted_target_mappings.get(rule_id):
                findings.append("candidate_target_mapping_untrusted:" + rule_id[:128])
            if not isinstance(required_anchor, str) or not required_anchor:
                findings.append("missing_target_anchor:" + rule_id)
            elif rel not in candidate_verified:
                findings.append("target_content_unverified:" + rule_id[:128])
            elif required_anchor not in (
                operative_skill if rel == "SKILL.md" else _operative_skill_text(candidate_verified[rel])
            ):
                findings.append("anchor_not_present:" + rule_id)
            elif kind in MATERIAL:
                owner_text = operative_skill if rel == "SKILL.md" else _operative_skill_text(candidate_verified[rel])
                # A trigger anchor identifies a routing phrase and is a prefix
                # of a longer instruction by design, and a retained rule keeps
                # its anchor inside the entrypoint line. A moved obligation
                # anchor is the complete instruction, so text after it can
                # narrow the duty.
                if rel != "SKILL.md" and kind != "trigger" and _owner_has_unreviewed_tail(owner_text, required_anchor):
                    findings.append("material_owner_rule_narrowed:" + rule_id[:128])
                if _contradicts_owner(owner_text, required_anchor):
                    findings.append("contradictory_owner_rule:" + rule_id[:128])
                if _reverses_preserved_prohibition(owner_text, required_anchor):
                    findings.append("negative_obligation_reversed:" + rule_id[:128])
                if rel != "STANDARD.md" and "STANDARD.md" in candidate_verified:
                    standard_text = _operative_skill_text(candidate_verified["STANDARD.md"])
                    if _contradicts_owner(standard_text, required_anchor):
                        findings.append("higher_authority_contradiction:" + rule_id[:128])
                    if _reverses_preserved_prohibition(standard_text, required_anchor):
                        findings.append("higher_authority_negative_obligation_reversed:" + rule_id[:128])
                critical = kind in {"trigger", "authority", "safety_stop", "precedence"}
                if not any(
                    _owner_rule_is_active(line, required_anchor, critical)
                    for line in (
                        operative_skill if rel == "SKILL.md" else _operative_skill_text(candidate_verified[rel])
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
        **VERIFICATION_BOUNDARY,
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
                    **VERIFICATION_BOUNDARY,
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
    if args.trusted_git_executable is not None and (
        os.name == "nt" or not args.trusted_git_executable or not Path(args.trusted_git_executable).is_absolute()
    ):
        parser.error("invalid_trusted_git_executable")
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
            unavailable = git_findings == ["baseline_git_revision_unavailable"]
            if unavailable and result["structural"] == "PASS":
                result["structural"] = "ENVIRONMENT_NOT_READY"
            else:
                result["structural"] = "FAILED"
            result["findings"] = (result["findings"] + git_findings)[:129]
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError, RuntimeError) as exc:
        result = {
            "structural": "INVALID_INPUT",
            **VERIFICATION_BOUNDARY,
            "findings": ["invalid_input:" + type(exc).__name__],
        }
        print(json.dumps(result))
        return 2
    print(json.dumps(result, indent=2))
    if result["structural"] == "ENVIRONMENT_NOT_READY":
        return 3
    return 1 if result["structural"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
