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
EXPECTED_TREE = "7ab39e0764fc3b0d54f10acd4f947a1c1134c27a"
GENERATED_REVISION = "c93a728e572ad9260555707cd46d0a6db42ca09f"
ARTIFACTS = {
    "linux-x64-py312": (8602866324, "sha256:3c0c75f2cc49d2c4a3f53604abd3504987152ffa753b105a9a0cc479ba6e1b6c"),
    "linux-x64-py313": (8602853663, "sha256:f318a2f6d9b401b8b9cbb4e7f0ddd89be2011a231d782976aaf5111e0fddc6df"),
    "linux-x64-py314": (8602860005, "sha256:df3ff7d3b9d0858770da223daceb1b23f58940c56f6b005775db814130746e06"),
    "macos-arm64-py312": (8602859605, "sha256:09d29193580287dedc3f354e967121f7a58fa40e7e9be78dc677afb891031df1"),
    "windows-x64-py312": (8602875685, "sha256:3d1a6c056d051f396b37307eccb9ceb03335f0c16003d771b0306cc40d1bee93"),
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
        ".github/materialize-final.py",
        ".github/final-code.patch.gz.b64",
    ]
    temporary_paths.extend(f".github/final-code.patch.part{index:02d}" for index in range(8))
    for path in temporary_paths:
        Path(path).unlink(missing_ok=True)

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

    base_tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], text=True).strip()
    entries: list[dict[str, object]] = []
    status_output = subprocess.check_output(
        ["git", "diff", "--cached", "--name-status", "-z", "HEAD"],
    )
    fields = status_output.split(b"\0")
    index = 0
    while index < len(fields) - 1:
        status = fields[index].decode("utf-8")
        path = fields[index + 1].decode("utf-8")
        index += 2
        if status.startswith("R") or status.startswith("C"):
            path = fields[index].decode("utf-8")
            index += 1
        if status == "D":
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
            continue
        mode_line = subprocess.check_output(["git", "ls-files", "-s", "--", path], text=True).strip()
        mode = mode_line.split(None, 1)[0]
        content = Path(path).read_text(encoding="utf-8")
        entries.append({"path": path, "mode": mode, "type": "blob", "content": content})

    tree = post("/git/trees", {"base_tree": base_tree, "tree": entries})
    tree_sha = str(tree.get("sha") or "")
    if tree_sha != EXPECTED_TREE:
        raise RuntimeError(f"GitHub tree mismatch: {tree_sha} != {EXPECTED_TREE}")
    commit = post(
        "/git/commits",
        {
            "message": "fix: verify production adoption evidence",
            "tree": tree_sha,
            "parents": [PARENT_SHA],
        },
    )
    commit_sha = str(commit.get("sha") or "")
    if len(commit_sha) != 40:
        raise RuntimeError("GitHub did not return a commit SHA")
    Path("final-commit.txt").write_text(
        f"commit={commit_sha}\ntree={tree_sha}\nparent={PARENT_SHA}\n",
        encoding="utf-8",
    )
    print(f"created verified commit {commit_sha}")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "stage":
        stage_final_tree()
    elif command == "commit":
        create_commit()
    else:
        raise SystemExit("usage: materialize-final.py <stage|commit>")
