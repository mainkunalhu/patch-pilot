from pathlib import Path

from patchpilot.indexer import chunk_python_file, naive_chunk

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "python-demo"


def test_chunk_calc():
    chunks = chunk_python_file(FIXTURE / "calc.py", "calc.py")
    assert len(chunks) == 1
    c = chunks[0]
    assert c.name == "add"
    assert "(a: int, b: int)" in c.signature
    assert c.is_test is False
    assert c.start_line == 1
    assert "return a + b + 1" in c.content


def test_chunk_test_file_marked_is_test():
    chunks = chunk_python_file(FIXTURE / "test_calc.py", "test_calc.py")
    assert len(chunks) == 1
    assert chunks[0].name == "test_add"
    assert chunks[0].is_test is True


def test_naive_baseline_splits():
    text = "x" * 7000
    parts = naive_chunk(text)
    assert len(parts) == 3
    assert all(len(p) <= 3200 for p in parts)
