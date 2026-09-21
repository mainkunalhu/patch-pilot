from pathlib import Path

from patchpilot.agent.patcher import (
    changed_paths,
    extract_diff,
    normalize_hunk_headers,
    validate_patch,
)

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


def test_normalize_fixes_wrong_counts():
    bad = GOOD_DIFF.replace("@@ -1,3 +1,2 @@", "@@ -1,3 +1,3 @@")
    assert normalize_hunk_headers(bad) == GOOD_DIFF


def test_normalize_fixes_bare_header():
    bad = GOOD_DIFF.replace("@@ -1,3 +1,2 @@", "@@")
    assert normalize_hunk_headers(bad) == GOOD_DIFF


def test_normalize_keeps_correct_diff():
    assert normalize_hunk_headers(GOOD_DIFF) == GOOD_DIFF


def test_validate_accepts_wrong_count_diff():
    bad = GOOD_DIFF.replace("@@ -1,3 +1,2 @@", "@@ -1,9 +1,9 @@")
    v = validate_patch(FIXTURE, bad)
    assert v.ok, v.error
    assert "@@ -1,3 +1,2 @@" in v.diff
