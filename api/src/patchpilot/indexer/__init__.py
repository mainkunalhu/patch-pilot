"""AST chunking: functions + tests, not raw files.

Uses tree-sitter to extract top-level function / async-function /
class-method definitions from Python sources. Falls back to an empty
list on parse failure so one bad file never breaks indexing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Parser

PY_LANGUAGE = Language(tspython.language())


def _parser() -> Parser:
    return Parser(PY_LANGUAGE)


@dataclass
class Chunk:
    path: str
    lang: str
    name: str
    signature: str
    content: str
    is_test: bool
    start_line: int
    end_line: int


def is_test_path(path: str) -> bool:
    p = Path(path)
    name = p.name
    parts = set(p.parts)
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or "tests" in parts
        or "test" in parts
    )


def _node_text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _iter_function_nodes(root, source: bytes):
    """Yield (node, name, signature) for functions incl. methods + nested."""
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in ("function_definition",):
            name = ""
            signature = ""
            for child in node.children:
                if child.type == "identifier" and not name:
                    name = _node_text(child, source)
                elif child.type == "parameters" and not signature:
                    signature = _node_text(child, source)
            yield node, name or "<anonymous>", signature
        stack.extend(node.children)


def chunk_python_file(abs_path: Path, rel_path: str) -> list[Chunk]:
    try:
        source = abs_path.read_bytes()
    except OSError:
        return []
    if not source.strip():
        return []
    parser = _parser()
    try:
        tree = parser.parse(source)
    except Exception:  # noqa: BLE001 - one bad file must not break indexing
        return []
    root = tree.root_node
    if root.has_error and len(source) > 1_000_000:
        return []

    test_file = is_test_path(rel_path)
    chunks: list[Chunk] = []
    for node, name, signature in _iter_function_nodes(root, source):
        content = _node_text(node, source)
        is_test = test_file or name.startswith("test_")
        chunks.append(
            Chunk(
                path=rel_path,
                lang="python",
                name=name,
                signature=signature,
                content=content,
                is_test=is_test,
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
            )
        )
    return chunks


def chunk_workdir(workdir: Path, files: list[Path]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for f in files:
        rel = str(f.relative_to(workdir))
        chunks.extend(chunk_python_file(f, rel))
    return chunks


def naive_chunk(text: str, size: int = 3200, overlap: int = 200) -> list[str]:
    """Fixed-window baseline (~800 tokens ≈ 3200 chars) for README comparison."""
    if not text:
        return []
    out: list[str] = []
    step = max(1, size - overlap)
    for i in range(0, len(text), step):
        out.append(text[i : i + size])
        if i + size >= len(text):
            break
    return out
