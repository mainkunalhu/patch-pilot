"""Postgres + pgvector persistence for repos and AST chunks.

Thin wrapper over psycopg v3. All DB errors surface as StoreError so
routers can map them to 503 (DB down) instead of leaking tracebacks.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import psycopg
from pgvector.psycopg import register_vector

from patchpilot.config import settings
from patchpilot.indexer import Chunk


class StoreError(RuntimeError):
    pass


@dataclass
class StoredChunk:
    id: int
    path: str
    lang: str
    name: str
    content: str
    signature: str
    is_test: bool
    start_line: int | None
    end_line: int | None
    distance: float | None = None


@dataclass
class StoredRepo:
    id: str
    source: str
    sha: str | None


def connect() -> psycopg.Connection:
    try:
        conn = psycopg.connect(settings.database_url, connect_timeout=5)
        register_vector(conn)
        return conn
    except psycopg.OperationalError as e:
        raise StoreError(
            f"cannot connect to Postgres at {settings.database_url}: {e}. "
            "Is it running? `make up` or `make db-direct`"
        ) from e


def embed_text_for(c: Chunk) -> str:
    return f"{c.path}\n{c.name}{c.signature}\n{c.content}"


def upsert_repo(
    conn: psycopg.Connection, repo_id: str, source: str, sha: str | None
) -> None:
    try:
        conn.execute(
            """
            INSERT INTO repos (id, source, sha)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET source = EXCLUDED.source,
                                           sha = EXCLUDED.sha
            """,
            (repo_id, source, sha),
        )
    except psycopg.Error as e:
        raise StoreError(f"upsert_repo failed: {e}") from e


def replace_chunks(
    conn: psycopg.Connection,
    repo_id: str,
    chunks: Sequence[Chunk],
    embeddings: Sequence[Sequence[float]],
) -> int:
    try:
        conn.execute("DELETE FROM chunks WHERE repo_id = %s", (repo_id,))
        for c, emb in zip(chunks, embeddings):
            conn.execute(
                """
                INSERT INTO chunks
                  (repo_id, path, lang, name, content, is_test,
                   start_line, end_line, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    repo_id,
                    c.path,
                    c.lang,
                    c.name,
                    c.content,
                    c.is_test,
                    c.start_line,
                    c.end_line,
                    list(emb),
                ),
            )
        conn.commit()
        return len(chunks)
    except psycopg.Error as e:
        conn.rollback()
        raise StoreError(f"replace_chunks failed: {e}") from e


def _row_to_chunk(r) -> StoredChunk:
    return StoredChunk(
        id=r[0],
        path=r[1],
        lang=r[2],
        name=r[3],
        content=r[4],
        signature="",
        is_test=r[5],
        start_line=r[6],
        end_line=r[7],
        distance=r[8] if len(r) > 8 else None,
    )


def fetch_chunks(conn: psycopg.Connection, repo_id: str) -> list[StoredChunk]:
    try:
        rows = conn.execute(
            """
            SELECT id, path, lang, name, content, is_test, start_line, end_line
            FROM chunks WHERE repo_id = %s ORDER BY id
            """,
            (repo_id,),
        ).fetchall()
    except psycopg.Error as e:
        raise StoreError(f"fetch_chunks failed: {e}") from e
    return [_row_to_chunk(r) for r in rows]


def vector_search(
    conn: psycopg.Connection,
    repo_id: str,
    query_vec: Sequence[float],
    limit: int = 20,
) -> list[StoredChunk]:
    try:
        rows = conn.execute(
            """
            SELECT id, path, lang, name, content, is_test,
                   start_line, end_line,
                   embedding <=> %s::vector AS distance
            FROM chunks WHERE repo_id = %s
            ORDER BY embedding <=> %s::vector LIMIT %s
            """,
            (list(query_vec), repo_id, list(query_vec), limit),
        ).fetchall()
    except psycopg.Error as e:
        raise StoreError(f"vector_search failed: {e}") from e
    return [_row_to_chunk(r) for r in rows]


def get_repo(conn: psycopg.Connection, repo_id: str) -> StoredRepo | None:
    try:
        row = conn.execute(
            "SELECT id, source, sha FROM repos WHERE id = %s", (repo_id,)
        ).fetchone()
    except psycopg.Error as e:
        raise StoreError(f"get_repo failed: {e}") from e
    if row is None:
        return None
    return StoredRepo(id=row[0], source=row[1], sha=row[2])


def save_run(
    conn: psycopg.Connection,
    run_id: str,
    repo_id: str,
    bug_text: str,
    status: str,
    diff: str | None = None,
    test_log: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    tokens_per_sec: float | None = None,
) -> None:
    try:
        conn.execute(
            """
            INSERT INTO runs
              (id, repo_id, bug_text, status, diff, test_log,
               prompt_tokens, completion_tokens, tokens_per_sec)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                repo_id,
                bug_text,
                status,
                diff,
                test_log,
                prompt_tokens,
                completion_tokens,
                tokens_per_sec,
            ),
        )
        conn.commit()
    except psycopg.Error as e:
        conn.rollback()
        raise StoreError(f"save_run failed: {e}") from e


@dataclass
class RunRow:
    id: str
    repo_id: str | None
    bug_text: str
    status: str
    diff: str | None
    test_log: str | None
    prompt_tokens: int
    completion_tokens: int
    tokens_per_sec: float | None


def get_run(conn: psycopg.Connection, run_id: str) -> RunRow | None:
    try:
        row = conn.execute(
            """
            SELECT id, repo_id, bug_text, status, diff, test_log,
                   prompt_tokens, completion_tokens, tokens_per_sec
            FROM runs WHERE id = %s
            """,
            (run_id,),
        ).fetchone()
    except psycopg.Error as e:
        raise StoreError(f"get_run failed: {e}") from e
    if row is None:
        return None
    return RunRow(
        id=row[0],
        repo_id=row[1],
        bug_text=row[2],
        status=row[3],
        diff=row[4],
        test_log=row[5],
        prompt_tokens=row[6] or 0,
        completion_tokens=row[7] or 0,
        tokens_per_sec=row[8],
    )
