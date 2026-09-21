"""Sandbox runner tests. Need a working Docker daemon; skipped otherwise."""

import subprocess
from pathlib import Path

import pytest

from patchpilot.sandbox.runner import run_tests

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "python-demo"

GOOD_DIFF = """--- a/calc.py
+++ b/calc.py
@@ -1,3 +1,2 @@
 def add(a: int, b: int) -> int:
-    # BUG: off-by-one for demo purposes (Phase 1 fixture)
-    return a + b + 1
+    return a + b
"""

NON_APPLYING_DIFF = """--- a/nope.py
+++ b/nope.py
@@ -1 +1 @@
-old
+new
"""


def _need_docker():
    r = subprocess.run(
        ["docker", "info"], capture_output=True, timeout=30, check=False
    )
    if r.returncode != 0:
        pytest.skip("Docker daemon unreachable")


def test_unpatched_fixture_fails_in_sandbox():
    _need_docker()
    r = run_tests(FIXTURE, diff=None, timeout_s=60)
    assert r.passed is False
    assert "assert 4 == 3" in r.log


def test_patched_fixture_passes_in_sandbox():
    _need_docker()
    r = run_tests(FIXTURE, diff=GOOD_DIFF, timeout_s=60)
    assert r.passed is True, r.log
    assert r.flaky is False
    assert "1 passed" in r.log


def test_non_applying_diff_reported():
    _need_docker()
    r = run_tests(FIXTURE, diff=NON_APPLYING_DIFF, timeout_s=60)
    assert r.passed is False
    assert "did not apply" in r.log
