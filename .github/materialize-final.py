from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import time
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
from zipfile import ZipFile

REPOSITORY = os.environ["GH_REPOSITORY"]
TOKEN = os.environ["GH_TOKEN"]
PARENT_SHA = os.environ["PARENT_SHA"]
EXPECTED_TREE = "46e2e497965467713cfb77c800f24c7bdb1f9b14"
GENERATED_REVISION = "840cc5fe26605bf24eb4706e8937be4ebca7cc64"
ARTIFACTS = {
    "linux-x64-py312": (8605177378, "sha256:625dba09cca79be5d45f3510bcd1003738d0cb2fcdb4c5d9a5b17724f744ec92"),
    "linux-x64-py313": (8605178514, "sha256:bef11adbd6f9884b3cec72002c176e6b696cb56f75bf8c77bd9d14dd4b7ce6f6"),
    "linux-x64-py314": (8605180632, "sha256:3a0823af6b0d44e604f93456b80ec0eb234976bc7e58a8a13a2ef1080b23671c"),
    "macos-arm64-py312": (8605185071, "sha256:98a0da68ebd8511b7da0616e08bf948dafbeeafa4792b5761c094a79d4390881"),
    "windows-x64-py312": (8605214691, "sha256:c4d58fa2f1ff4a50fb6ed05e33cdd7d5d7ca87b27dffdc437c0f495f0b6b5c87"),
}
API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "ai-skills-final-materializer",
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


def api_json(path: str) -> dict[str, object]:
    request = Request(f"https://api.github.com/repos/{REPOSITORY}{path}", headers=API_HEADERS)
    with urlopen(request, timeout=30) as response:
        result = json.load(response)
    if not isinstance(result, dict):
        raise RuntimeError(f"GitHub API returned a non-object for {path}")
    return result


def download_artifact(artifact_id: int) -> bytes:
    request = Request(
        f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/{artifact_id}/zip",
        headers=API_HEADERS,
    )
    opener = build_opener(NoRedirect)
    try:
        opener.open(request, timeout=30)
    except HTTPError as exc:
        if exc.code not in {301, 302, 303, 307, 308}:
            raise
        location = exc.headers.get("Location")
        if not location:
            raise RuntimeError(f"artifact {artifact_id} redirect omitted Location") from exc
    else:
        raise RuntimeError(f"artifact {artifact_id} download did not use a signed redirect")

    signed_request = Request(location, headers={"User-Agent": "ai-skills-final-materializer"})
    with urlopen(signed_request, timeout=120) as response:
        return response.read()


def stage_final_tree() -> None:
    requirements_path = Path("requirements-dev.in")
    requirements = requirements_path.read_text(encoding="utf-8").splitlines()
    stub_requirement = "types-jsonschema==4.26.0.20260518"
    if stub_requirement not in requirements:
        requirements.insert(requirements.index("setuptools==83.0.0") + 1, stub_requirement)
    requirements_path.write_text("\n".join(requirements) + "\n", encoding="utf-8")

    for lock_id, (artifact_id, expected_digest) in ARTIFACTS.items():
        metadata = api_json(f"/actions/artifacts/{artifact_id}")
        if metadata.get("expired") is True or metadata.get("digest") != expected_digest:
            raise RuntimeError(f"artifact metadata mismatch: {lock_id}")
        workflow_run = metadata.get("workflow_run")
        if not isinstance(workflow_run, dict) or workflow_run.get("head_sha") != GENERATED_REVISION:
            raise RuntimeError(f"artifact revision mismatch: {lock_id}")

        archive = download_artifact(artifact_id)
        observed_digest = "sha256:" + hashlib.sha256(archive).hexdigest()
        if observed_digest != expected_digest:
            raise RuntimeError(f"downloaded artifact digest mismatch: {lock_id}: {observed_digest}")

        expected_names = {
            f"requirements-dev-{lock_id}.lock",
            f"runtime-{lock_id}.lock",
            f"dev-{lock_id}.lock",
        }
        with ZipFile(BytesIO(archive)) as zip_file:
            names = {name for name in zip_file.namelist() if not name.endswith("/")}
            if names != expected_names:
                raise RuntimeError(f"artifact file set mismatch: {lock_id}: {sorted(names)}")
            for name in sorted(names):
                data = zip_file.read(name).decode("utf-8").replace("\r\n", "\n").encode("utf-8")
                target = Path(name) if name.startswith("requirements-dev-") else Path("skills/mcp-server-architect/locks") / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)

    for path in (
        "requirements-dev-linux.lock",
        "requirements-dev-macos.lock",
        "requirements-dev-windows.lock",
    ):
        Path(path).unlink(missing_ok=True)
    for prefix in ("runtime", "dev"):
        for platform_name in ("linux", "macos", "windows"):
            Path(f"skills/mcp-server-architect/locks/{prefix}-{platform_name}.lock").unlink(missing_ok=True)

    temporary_paths = [
        ".github/workflows/_audit-export.yml",
        ".github/workflows/_audit-export-pr.yml",
        ".github/workflows/_generate-target-locks.yml",
        ".github/workflows/_apply-final-fixes.yml",
        ".github/workflows/_diagnose-lock-artifacts.yml",
        ".github/workflows/_apply-final-v2.yml",
        ".github/workflows/_format-final-files.yml",
        ".github/materialize-final.py",
        ".github/final-code.patch.gz.b64",
    ]
    temporary_paths.extend(f".github/final-code.patch.part{index:02d}" for index in range(8))
    for path in temporary_paths:
        Path(path).unlink(missing_ok=True)

    formatted_paths = [
        "contracts/validate_adoption.py",
        "skills/mcp-server-architect/tools/generate_python_server.py",
    ]
    subprocess.run([sys.executable, "-m", "ruff", "format", *formatted_paths], check=True)
    subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check", *formatted_paths],
        check=True,
    )

    subprocess.run(["git", "add", "-A"], check=True)
    subprocess.run(["git", "diff", "--cached", "--check"], check=True)
    observed_tree = subprocess.check_output(["git", "write-tree"], text=True).strip()
    if observed_tree != EXPECTED_TREE:
        subprocess.run(["git", "diff", "--cached", "--stat"], check=False)
        raise RuntimeError(f"staged tree mismatch: {observed_tree} != {EXPECTED_TREE}")
    print(f"verified staged tree {observed_tree}")


def post(path: str, payload: object) -> dict[str, object]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {**API_HEADERS, "Content-Type": "application/json"}
    for attempt in range(6):
        request = Request(
            f"https://api.github.com/repos/{REPOSITORY}{path}",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=120) as response:
                result = json.load(response)
            if not isinstance(result, dict):
                raise RuntimeError(f"GitHub API returned a non-object for {path}")
            return result
        except HTTPError as exc:
            if exc.code not in {403, 409, 422, 429, 500, 502, 503, 504} or attempt == 5:
                raise
            time.sleep(min(2**attempt, 20))
    raise RuntimeError("unreachable")


def create_commit() -> None:
    local_tree = subprocess.check_output(["git", "write-tree"], text=True).strip()
    if local_tree != EXPECTED_TREE:
        raise RuntimeError(f"local tree changed after validation: {local_tree}")

    temporary_paths = [
        ".github/workflows/_audit-export.yml",
        ".github/workflows/_audit-export-pr.yml",
        ".github/workflows/_generate-target-locks.yml",
        ".github/workflows/_apply-final-fixes.yml",
        ".github/workflows/_diagnose-lock-artifacts.yml",
        ".github/workflows/_apply-final-v2.yml",
        ".github/workflows/_format-final-files.yml",
        ".github/materialize-final.py",
        ".github/final-code.patch.gz.b64",
    ]
    temporary_paths.extend(f".github/final-code.patch.part{index:02d}" for index in range(8))
    subprocess.run(
        ["git", "restore", f"--source={PARENT_SHA}", "--staged", "--worktree", "--", *temporary_paths],
        check=True,
    )
    subprocess.run(["git", "add", "-A"], check=True)

    subprocess.run(["git", "config", "user.name", "ai-skills-audit-bot"], check=True)
    subprocess.run(
        ["git", "config", "user.email", "ai-skills-audit-bot@users.noreply.github.com"],
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "fix: verify production adoption evidence"],
        check=True,
    )
    commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    commit_parent = subprocess.check_output(["git", "rev-parse", "HEAD^"], text=True).strip()
    if commit_parent != PARENT_SHA:
        raise RuntimeError(f"commit parent mismatch: {commit_parent}")
    changed_paths = set(
        subprocess.check_output(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
            text=True,
        ).splitlines()
    )
    leaked = sorted(changed_paths.intersection(temporary_paths))
    if leaked:
        raise RuntimeError(f"intermediate commit unexpectedly changes temporary files: {leaked}")

    subprocess.run(
        ["git", "config", "--local", "--unset-all", "http.https://github.com/.extraheader"],
        check=False,
    )
    push_url = f"https://x-access-token:{TOKEN}@github.com/{REPOSITORY}.git"
    subprocess.run(
        [
            "git",
            "push",
            f"--force-with-lease=refs/heads/refactor/skills-cleanup:{PARENT_SHA}",
            push_url,
            "HEAD:refs/heads/refactor/skills-cleanup",
        ],
        check=True,
    )
    Path("final-commit.txt").write_text(
        f"commit={commit_sha}\nfinal_tree={EXPECTED_TREE}\nparent={commit_parent}\n",
        encoding="utf-8",
    )
    print(f"pushed verified intermediate commit {commit_sha}")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "stage":
        stage_final_tree()
    elif command == "commit":
        create_commit()
    else:
        raise SystemExit("usage: materialize-final.py <stage|commit>")
