# PatchPilot — Build Phases (temp plan file)

> Stack: uv Python 3.12 FastAPI + bun Next.js + Ollama nomic-embed + BM25 + Postgres pgvector + Groq + Docker sandbox + DeepEval
> Locks: monorepo api/+web/, FastAPI-only MVP (Hono deferred), Docker Compose pgvector, Python-only sandbox MVP, Ollama local embed, public gh repo `patch-pilot`

## Target layout
patch-pilot/
├── api/  # uv-managed FastAPI
│   └── src/patchpilot/
│       ├── ingest/     # git URL/local path, shallow clone, SHA-pin
│       ├── indexer/    # tree-sitter AST func+test chunks + naive baseline
│       ├── retrieval/  # ollama nomic-embed + BM25 + RRF + llama-3.1-8b rerank
│       ├── agent/      # gpt-oss-120b coder + diff-validate + fixer max-3x
│       ├── sandbox/    # hardened pytest-only runner
│       └── routers/    # repos, query, patch, runs, health (+SSE)
├── web/  # bun create-next-app diff UI
├── infra/docker-compose.yml + sql/
├── fixtures/python-demo/
├── evals/dataset.jsonl + run_evals.py
└── .env.example

## Phase 0 — Scaffold + git + gh push
- `uv init --python 3.12 api`; `uv add fastapi "uvicorn[standard]" pydantic-settings tree-sitter tree-sitter-python rank-bm25 psycopg[binary] pgvector groq httpx deepeval ruff --project api`
- `bunx create-next-app@latest web --typescript --tailwind --eslint --app --src-dir --import-alias "@/*"`
- Root: .gitignore, .env.example (GROQ_API_KEY, DATABASE_URL, OLLAMA_HOST, EMBED_MODEL=nomic-embed-text), infra/docker-compose.yml (postgres:16-pgvector + ollama), Makefile, README
- Verify: `uv run --project api ruff check .`, `uv run --project api uvicorn patchpilot.main:app --reload`, `bun --cwd web dev`, `docker compose -f infra/docker-compose.yml up -d`, `ollama pull nomic-embed-text`
- `git init -b main && git add . && git commit -m "feat: scaffold FastAPI api/ + Next.js web/ monorepo"`
- `gh auth status && gh repo create patch-pilot --public --source=. --remote=origin --push`
- Exit: public repo has commit, both servers boot.

## Phase 1 — Ingest + AST indexer
- POST /repos/index {git_url|local_path, sha?} → content-addressed clone
- tree-sitter py func/test extract: path, lines, name, signature, body, is_test + naive 800-token baseline
- Exit: fixture → N funcs + M tests via API.

## Phase 2 — Hybrid retrieval + pgvector
- Tables repos/chunks/runs; embedding dim 768 HNSW; Ollama batch+cache; BM25+RRF; openai/gpt-oss-20b query-rewrite/rerank
- POST /query → top-k hunks. Exit: faulty func in top-5.

## Phase 3 — Coder + reliability guardrails
- gpt-oss-120b strict unified-diff prompt → git apply --check → tree-sitter re-parse → repair prompt; log tokens + tok/s to runs table
- Exit: 1 bug → valid diff + tok/s logged.

## Phase 4 — Hardened sandbox + fixer loop max 3x
- POST /runs: apply diff → docker run --network=none --memory=1g --cpus=2 --timeout=180s pytest -q → log → retry ≤3
- Flaky: rerun fails 1x, split fail_to_pass vs pass_to_pass, mark flaky; always cleanup
- Exit: fail→pass log stored.

## Phase 5 — Next.js diff UI
- / + /runs/[id], SSE/polling, diff viewer + test log, direct fetch to FastAPI
- Exit: click-through demo recorded.

## Phase 6 — DeepEval 50-bug evals
- dataset.jsonl with fail_to_pass/pass_to_pass/gold patch; run_evals.py via sandbox; report fix-rate + median tok/s
- Exit: make eval-quick (5 bugs) green; README number measured.

## Phase 7 — Polish + CI
- ci.yml: ruff+pytest, bun lint/build, compose health; README arch + demo + hiring line; roadmap: Hono BFF (gateway/), TS/vitest sandbox
- Exit: green CI, clone→make up→demo works.

## Deferred (explicit non-goals MVP)
- gateway/ Hono BFF, TS AST exec + vitest sandbox, HF fallback embed, auth/rate-limit.

## Original spec reference
About: Point it at any Python/TS repo, describe a bug, and it finds the faulty functions, writes a patch, runs the tests in an isolated container, and shows a proven diff. A tiny Groq-powered Cursor/SWE-agent.
Tech: Python (FastAPI, Tree-sitter AST chunking, Docker sandbox pytest runner), TypeScript (Next.js diff UI, Hono API), Groq (openai/gpt-oss-120b coder, openai/gpt-oss-20b retriever), local nomic-embed + BM25, Postgres + pgvector, DeepEval
Flow: Index any repo (AST functions + tests, not raw files) -> query bug -> retrieve relevant hunks -> coder agent proposes patch -> runs in Docker sandbox -> test log -> fixer loop max 3x -> outputs unified diff + test proof.
Skills: code chunking (AST vs naive), hybrid code search, agentic code loop, sandbox exec, SWE-style evals.
Hiring line: Groq code agent, 42% fix-rate on 50 curated bugs, sandbox-verified diffs, 500+ tok/s via Groq.
Hard: AST indexing, sandbox security/timeouts, flaky-test handling, small-model code tool reliability.
