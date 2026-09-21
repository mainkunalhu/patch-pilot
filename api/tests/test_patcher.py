from pathlib import Path

from patchpilot.agent.patcher import changed_paths, extract_diff, validate_patch

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "python-demo"

GOOD_DIFF = """--- a/calc.py
+++ b/calc.py
@@ -1,3 +1,2 @@
 def add(a: int, b: int) -> int:
-    # BUG: off-by-one for demo purposes (Phase 1 fixture)
-    return a + b + 1
+    return a + b
"""

BAD_DIFF = """--- a/nope.py
+++ b/nope.py
@@ -1 +1 @@
-old
+new
"""

SYNTAX_BREAKING_DIFF = """--- a/calc.py
+++ b/calc.py
@@ -1,3 +1,2 @@
 def add(a: int, b: int) -> int:
-    # BUG: off-by-one for demo purposes (Phase 1 fixture)
-    return a + b + 1
+    return a +
"""


def test_extract_diff_from_fence():
    raw = "Here you go:\n```diff\n" + GOOD_DIFF + "```\nDone."
    assert extract_diff(raw) == GOOD_DIFF


def test_extract_diff_strips_prose():
    raw = "I fixed it:\n" + GOOD_DIFF
    assert extract_diff(raw) == GOOD_DIFF


def test_extract_diff_raw_passthrough():
    assert extract_diff(GOOD_DIFF) == GOOD_DIFF


def test_changed_paths():
    assert changed_paths(GOOD_DIFF) == ["calc.py"]


def test_validate_good_diff():
    v = validate_patch(FIXTURE, GOOD_DIFF)
    assert v.ok, v.error
    assert v.changed_files == ["calc.py"]
    assert "return a + b" in v.diff


def test_validate_bad_diff_rejected():
    v = validate_patch(FIXTURE, BAD_DIFF)
    assert not v.ok
    assert v.error


def test_validate_syntax_breaking_diff_rejected():
    v = validate_patch(FIXTURE, SYNTAX_BREAKING_DIFF)
    assert not v.ok
    assert "syntax error" in v.error


def test_validate_empty_diff_rejected():
    v = validate_patch(FIXTURE, "just some prose, no diff")
    assert not v.ok
