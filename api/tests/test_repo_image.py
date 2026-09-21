"""Per-repo image tests. Need Docker + network for the image build."""

import subprocess
from pathlib import Path

import pytest

from patchpilot.sandbox.runner import run_tests

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "python-deps"

FIX_DIFF = """--- a/dt.py
+++ b/dt.py
@@ -1,6 +1,5 @@
 from dateutil.parser import parse


 def parse_day(s: str) -> int:
-    # BUG: returns the month instead of the day
-    return parse(s).month
+    return parse(s).day
"""


def _need_docker():
    r = subprocess.run(["docker", "info"], capture_output=True, timeout=30, check=False)
    if r.returncode != 0:
        pytest.skip("Docker daemon unreachable")


def test_deps_fixture_fails_without_fix():
    _need_docker()
    r = run_tests(FIXTURE, diff=None, timeout_s=120)
    assert r.passed is False, r.log
    assert r.extra.get("image", "").startswith("patchpilot-repo-")


def test_deps_fixture_fixed_on_repo_image():
    _need_docker()
    r = run_tests(FIXTURE, diff=FIX_DIFF, timeout_s=120)
    assert r.passed is True, r.log
    assert "1 passed" in r.log
    assert r.extra.get("image", "").startswith("patchpilot-repo-")
