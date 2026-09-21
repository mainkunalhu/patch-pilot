# PatchPilot — Repo-Native Bug Fixer

Point it at any Python repo, describe a bug, and it finds the faulty functions, writes a patch, runs the tests in an isolated Docker sandbox, and shows a proven diff. A tiny Groq-powered Cursor/SWE-agent.

> Hiring line: Groq code agent, sandbox-verified diffs, ~360 tok/s via Groq, 5/5 on the starter eval set (target: 42% fix-rate on 50 curated bugs — dataset in progress).

## How it works

```text
repo (git URL | local path)
  │  POST /repos/index — tree-sitter AST chunking (functions + tests, not raw files)
  ▼
pgvector (nomic-embed vectors) + BM25
  │  POST /query — hybrid retrieval (RRF fusion) + query rewrite
  ▼  top-k faulty hunks
gpt-oss-120b coder — strict unified-diff prompt, few-shot format guard
  │  POST /patch — git apply --check + tree-sitter re-parse on a copy
  ▼  valid diff
Docker sandbox (no network, 1g RAM, 2 CPU, timeout) — pytest on patched copy
  │  POST /runs — fixer loop, max 3 attempts, failure fed back to coder
  ▼
proven diff + test log  →  Next.js UI (index → run → /runs/[id])
```

## Setup (fresh clone → demo)

Prerequisites: `uv`, `bun`, `docker`, `ollama`, `gh` optional.

```bash
git clone https://github.com/mainkunalhu/patch-pilot.git && cd patch-pilot
cp .env.example .env          # add GROQ_API_KEY

# Services: Postgres+pgvector + Ollama
make up                       # needs Docker Compose plugin; else:
make db-direct && make db-schema   # fallback without the plugin
ollama pull nomic-embed-text

# Dev servers
make dev-api                  # http://localhost:8000 (docs at /docs)
make dev-web                  # http://localhost:3000

# Checks
make lint && make test
make eval-quick               # 5 curated bugs vs the live stack
```

Demo in the UI: index `/abs/path/to/repo` (or any public git URL), describe the bug, Run fix — first green run returns a diff plus the sandbox test log. `GET /runs/{id}` replays any proof.

No-Docker quick look: `POST /repos/index` with `"persist": false` indexes without DB/Ollama.

## API

| Method | Path | What |
|---|---|---|
| `GET` | `/health` | liveness |
| `POST` | `/repos/index` | `{git_url \| local_path, sha?, persist?}` → chunks + stats |
| `POST` | `/query` | `{repo_id, bug_text, top_k?}` → ranked hunks (`score`, `sources`) |
| `POST` | `/patch` | `{repo_id, bug_text, top_k?}` → validated diff + token usage |
| `POST` | `/runs` | `{repo_id, bug_text, top_k?, max_attempts? ≤3, timeout_s?}` → fix loop + proof |
| `GET` | `/runs/{id}` | stored proof (diff, test log, usage) |

Error contract: `404` unknown repo/run, `422` repo files not local, `503` DB/Ollama/Groq unavailable (message says what to start), all without leaking tracebacks.

## Evals (measured, not claimed)

```bash
make eval-quick   # --limit 5;  make eval  runs the full dataset
```

- Starter set, 2026-09-21: **5/5 fixed (100%), median ~360 tok/s** (reports in `evals/results/`, git-ignored).
- Harness: each case must fail at baseline (`invalid_case` otherwise) → full-stack `/runs` → sandbox proof is the verdict. DeepEval GEval correctness (Groq-judged, 0.7–1.0 here) is a secondary signal only.
- Honest limits: micro-repos, stdlib-only sandbox image, 5 cases so far. The 42%-on-50 line stays a target until the dataset reaches 50.

## Layout

```text
api/      # uv FastAPI: ingest, indexer, retrieval, agent, sandbox, routers
web/      # bun Next.js diff UI (calls FastAPI directly; NEXT_PUBLIC_API_URL)
infra/    # docker-compose (pgvector + ollama) + sql schema
fixtures/ # sample buggy targets
evals/    # dataset.jsonl + DeepEval harness + Groq judge
```

## Roadmap / non-goals (MVP)

- `gateway/` Hono BFF (auth, rate-limit, streaming) — deferred; web calls FastAPI directly.
- TS/vitest sandbox + TS exec — deferred; TS parses, Python executes.
- 50-case dataset, per-repo sandbox images with deps, pass-to-pass quarantine.

## Env

| Var | Default | What |
|---|---|---|
| `GROQ_API_KEY` | — | required for coder/rewrite/judge |
| `DATABASE_URL` | `postgresql://patchpilot:patchpilot@localhost:5432/patchpilot` | pgvector |
| `OLLAMA_HOST` | `http://localhost:11434` | embeddings |
| `EMBED_MODEL` | `nomic-embed-text` | 768-dim, must match schema |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | web → api |
