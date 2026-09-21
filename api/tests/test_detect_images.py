from pathlib import Path

from patchpilot.sandbox.detect import RuntimeSpec, detect_runtime
from patchpilot.sandbox.images import fingerprint, render_dockerfile

ROOT = Path(__file__).resolve().parents[2]
DEPS_FIXTURE = ROOT / "fixtures" / "python-deps"
DEMO_FIXTURE = ROOT / "fixtures" / "python-demo"


def test_detect_python_with_deps():
    spec = detect_runtime(DEPS_FIXTURE)
    assert spec.runtime == "python"
    assert "requirements.txt" in spec.dep_files


def test_detect_python_without_deps():
    spec = detect_runtime(DEMO_FIXTURE)
    assert spec.runtime == "python"
    assert spec.dep_files == []


def test_detect_node(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts": {"test": "vitest run"}}')
    spec = detect_runtime(tmp_path)
    assert isinstance(spec, RuntimeSpec)
    assert spec.runtime == "node"


def test_fingerprint_stable_and_sensitive():
    a = fingerprint(DEPS_FIXTURE, ["requirements.txt"])
    b = fingerprint(DEPS_FIXTURE, ["requirements.txt"])
    assert a == b and len(a) == 12


def test_render_dockerfile_installs_requirements():
    dockerfile = render_dockerfile(["requirements.txt"])
    assert "pip install" in dockerfile and "requirements.txt" in dockerfile
    assert "WORKDIR /work" in dockerfile
