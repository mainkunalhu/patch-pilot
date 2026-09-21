"""Isolated pytest runner: temp copy → git apply → docker run.

Hardening: --network=none, 1g RAM, 2 CPUs, pid limit, per-run timeout,
--rm containers, temp-dir cleanup always. One flaky retry: a failed run
is executed once more; pass-on-retry is reported as flaky, not fixed.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

IMAGE = "patchpilot-sandbox-py:1"
_DOCKERFILE_DIR = Path(__file__).resolve().parent


class SandboxError(RuntimeError):
    pass


@dataclass
class TestResult:
    passed: bool
    returncode: int
    log: str
    timed_out: bool = False
    flaky: bool = False
    runs: int = 1
    env_error: bool = False
    extra: dict = field(default_factory=dict)


def _snapshot_root() -> str | None:
    """Temp root that the Docker VM can bind-mount. Colima shares $HOME
    but NOT macOS /var/folders temp dirs (they mount as empty)."""
    root = Path.home() / ".cache" / "patchpilot" / "tmp"
    try:
        root.mkdir(parents=True, exist_ok=True)
        return str(root)
    except OSError:
        return None


def _docker(
    args: list[str], timeout: int, input_text: str | None = None
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["docker", *args],
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as e:
        raise SandboxError("docker CLI not found") from e
    except subprocess.TimeoutExpired as e:
        raise SandboxError(f"docker command timed out: {e}") from e


def ensure_image() -> None:
    r = _docker(["images", "-q", IMAGE], timeout=30)
    if r.returncode != 0:
        raise SandboxError(f"docker images failed: {r.stderr.strip()}")
    if r.stdout.strip():
        return
    r = _docker(
        [
            "build",
            "-t",
            IMAGE,
            "-f",
            str(_DOCKERFILE_DIR / "Dockerfile.target"),
            str(_DOCKERFILE_DIR),
        ],
        timeout=300,
    )
    if r.returncode != 0:
        raise SandboxError(f"sandbox image build failed: {r.stderr.strip()}")


def _run_once(
    snapshot: Path, test_cmd: list[str], timeout_s: int, image: str
) -> TestResult:
    r = _docker(
        [
            "run",
            "--rm",
            "--network=none",
            "--memory=1g",
            "--cpus=2",
            "--pids-limit=256",
            "-v",
            f"{snapshot}:/work",
            "-w",
            "/work",
            image,
            *test_cmd,
        ],
        timeout=timeout_s + 30,
    )
    log = ((r.stdout or "") + (r.stderr or "")).strip()
    return TestResult(passed=r.returncode == 0, returncode=r.returncode, log=log)


def run_tests(
    repo_source: Path,
    diff: str | None = None,
    test_cmd: list[str] | None = None,
    timeout_s: int = 180,
) -> TestResult:
    """Apply diff (if given) to a temp copy of repo_source and test it.

    Resolves a per-repo image when dependency files are detected
    (Track B); node runtimes are detected but not yet executable.
    """
    from patchpilot.sandbox.detect import detect_runtime

    try:
        ensure_image()
    except SandboxError as e:
        return TestResult(passed=False, returncode=-1, log=str(e), env_error=True)
    spec = detect_runtime(repo_source)
    if spec.runtime == "node":
        return TestResult(
            passed=False,
            returncode=-1,
            log="node runtime detected but not supported yet (vitest sandbox is next)",
            env_error=True,
        )
    image = IMAGE
    if spec.dep_files:
        from patchpilot.sandbox.images import ensure_repo_image

        try:
            image = ensure_repo_image(repo_source, spec.dep_files)
        except SandboxError as e:
            return TestResult(passed=False, returncode=-1, log=str(e), env_error=True)
    cmd = test_cmd or ["python", "-m", "pytest", "-q"]
    tmp = Path(tempfile.mkdtemp(prefix="patchpilot-sandbox-", dir=_snapshot_root()))
    try:
        snap = tmp / "repo"
        shutil.copytree(
            repo_source,
            snap,
            ignore=shutil.ignore_patterns(
                ".git",
                "__pycache__",
                ".venv",
                ".pytest_cache",
                ".next",
                "node_modules",
            ),
        )
        if diff:
            r = subprocess.run(
                ["git", "apply", "-"],
                input=diff,
                text=True,
                capture_output=True,
                cwd=snap,
                timeout=30,
                check=False,
            )
            if r.returncode != 0:
                return TestResult(
                    passed=False,
                    returncode=r.returncode,
                    log=f"diff did not apply in sandbox: "
                    f"{(r.stderr or r.stdout).strip()}",
                )
        try:
            first = _run_once(snap, cmd, timeout_s, image)
        except SandboxError as e:
            if "timed out" in str(e):
                return TestResult(
                    passed=False, returncode=-1, log=str(e), timed_out=True
                )
            return TestResult(passed=False, returncode=-1, log=str(e))
        if first.passed:
            first.extra["image"] = image
            return first
        # Flaky policy: one retry; pass-on-retry is flaky, not proof.
        try:
            second = _run_once(snap, cmd, timeout_s, image)
        except SandboxError as e:
            first.log += f"\n[retry aborted: {e}]"
            return first
        second.extra["image"] = image
        second.runs = 2
        if second.passed:
            # Pass-on-retry counts (like pytest-rerunfailures) but is flagged
            # so evals can exclude flaky proofs.
            second.flaky = True
            second.log = f"{first.log}\n--- retry passed (FLAKY) ---\n{second.log}"
        else:
            second.log = f"{first.log}\n--- retry (same failure) ---\n{second.log}"
        return second
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
