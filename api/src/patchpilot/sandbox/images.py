"""Per-repo sandbox images: base Python image + target dependencies.

Images are content-addressed (`patchpilot-repo-<hash>`) from the sorted
(relpath, content) of dependency files, so rebuilds happen only when
deps change. Builds run WITH network (only test *runs* are offline).
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from patchpilot.sandbox.runner import IMAGE as BASE_IMAGE
from patchpilot.sandbox.runner import SandboxError, _docker

TAG_PREFIX = "patchpilot-repo-"


def fingerprint(workdir: Path, dep_files: list[str]) -> str:
    h = hashlib.sha256()
    for rel in sorted(dep_files):
        p = workdir / rel
        h.update(rel.encode())
        try:
            h.update(p.read_bytes())
        except OSError as e:
            raise SandboxError(f"cannot read dep file {rel}: {e}") from e
    return h.hexdigest()[:12]


def render_dockerfile(dep_files: list[str]) -> str:
    """pip-install each requirements file; `pip install .` when the repo
    is a package (pyproject) without pinned requirements."""
    lines = [f"FROM {BASE_IMAGE}"]
    reqs = [f for f in dep_files if Path(f).name.startswith("requirements")]
    for r in reqs:
        lines.append(f"COPY {r} /tmp/{Path(r).name}")
    if "pyproject.toml" in dep_files:
        lines.append("COPY pyproject.toml /tmp/build/pyproject.toml")
    for r in reqs:
        lines.append(f"RUN pip install --no-cache-dir -r /tmp/{Path(r).name}")
    if "pyproject.toml" in dep_files and not reqs:
        lines.append("COPY . /tmp/build/repo")
        lines.append("RUN pip install --no-cache-dir /tmp/build/repo")
    lines.append("WORKDIR /work")
    return "\n".join(lines) + "\n"


def ensure_repo_image(workdir: Path, dep_files: list[str]) -> str:
    """Build (if needed) and return the image tag for these dependencies."""
    tag = TAG_PREFIX + fingerprint(workdir, dep_files)
    r = _docker(["images", "-q", tag], timeout=30)
    if r.returncode != 0:
        raise SandboxError(f"docker images failed: {r.stderr.strip()}")
    if r.stdout.strip():
        return tag
    with tempfile.TemporaryDirectory(prefix="patchpilot-image-") as ctx:
        ctxp = Path(ctx)
        (ctxp / "Dockerfile").write_text(render_dockerfile(dep_files))
        for rel in dep_files:
            dest = ctxp / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((workdir / rel).read_bytes())
            if rel == "pyproject.toml" and "pyproject.toml" in dep_files:
                # Full source needed for `pip install .` fallback.
                for src in workdir.rglob("*.py"):
                    try:
                        if ".venv" in src.parts or "__pycache__" in src.parts:
                            continue
                        d = ctxp / src.relative_to(workdir)
                        d.parent.mkdir(parents=True, exist_ok=True)
                        d.write_bytes(src.read_bytes())
                    except OSError:
                        continue
        r = _docker(["build", "-t", tag, str(ctxp)], timeout=600)
    if r.returncode != 0:
        raise SandboxError(
            f"repo image build failed for {dep_files}: {r.stderr.strip()[-2000:]}"
        )
    return tag
