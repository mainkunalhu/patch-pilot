from patchpilot.retrieval.bm25 import bm25_scores
from patchpilot.retrieval.hybrid import rank_best_first, rrf_fuse
from patchpilot.retrieval.rewrite import maybe_rewrite_query


def test_bm25_prefers_matching_doc():
    # NOTE: needs 3+ docs — with only 2 docs a term in one doc gets IDF 0.
    docs = [
        "def add(a, b): return a + b",
        "def greet(name): print hello",
        "class Config: host port",
        "def main(): parse args",
    ]
    scores = bm25_scores("add function returns sum", docs)
    assert scores[0] > scores[1]


def test_bm25_empty_inputs():
    assert bm25_scores("", ["a", "b"]) == [0.0, 0.0]
    assert bm25_scores("q", []) == []


def test_rank_best_first():
    assert rank_best_first([1.0, 5.0, 3.0]) == [1, 2, 0]
    assert rank_best_first([1.0, 5.0, 3.0], limit=2) == [1, 2]


def test_rrf_fuse_agrees_on_top():
    fused = rrf_fuse([[0, 1, 2], [0, 2, 1]])
    assert fused[0][0] == 0
    assert [i for i, _ in fused] == [0, 1, 2]


def test_rrf_fuse_partial_rankings():
    fused = dict(rrf_fuse([[5], [5, 6]]))
    assert set(fused) == {5, 6}
    assert fused[5] > fused[6]


def test_rewrite_falls_back_without_key():
    q, rewritten = maybe_rewrite_query("add returns wrong sum")
    assert q == "add returns wrong sum"
    assert rewritten is False
