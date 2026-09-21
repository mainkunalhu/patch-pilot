# PatchPilot — Repo-Native Bug Fixer

Point it at any Python repo, describe a bug, and it finds the faulty functions, writes a patch, runs the tests in an isolated Docker sandbox, and shows a proven diff. A tiny Groq-powered Cursor/SWE-agent.

![PatchPilot live demo: index → retrieve → sandbox-verified fix](docs/demo.gif)

*Live demo (15s): index a buggy repo, retrieve faulty hunks, fixer loop returns a validated diff plus the sandbox test proof. Reproduce it: `bash docs/demo.sh` with the stack running.*

> Hiring line: Groq code agent, 100% fix-rate on 50 curated bugs (sandbox-verified diffs), ~340 tok/s via Groq.

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

- Full set, 2026-09-21: **50/50 fixed (100%), median ~340 tok/s** (reports in `evals/results/`, git-ignored). 46 fixed on attempt 1, 4 needed retries. DeepEval GEval correctness mean 0.96 (min 0.6) as secondary signal.
- Honest limits: micro-repos (1–2 files each). Sandbox builds per-repo images from `requirements*.txt`/`pyproject.toml` (cached by dep hash); dep-free repos use the base image. Every case verified: fail_to_pass red + pass_to_pass green at baseline — so the 100% is real but on small bugs, not SWE-bench scale. Node/vitest support is next.

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
