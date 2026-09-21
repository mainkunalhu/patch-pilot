CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS repos (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  sha TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  repo_id TEXT NOT NULL REFERENCES repos(id) ON DELETE CASCADE,
  path TEXT NOT NULL,
  lang TEXT NOT NULL,
  name TEXT NOT NULL,
  content TEXT NOT NULL,
  is_test BOOLEAN NOT NULL DEFAULT FALSE,
  start_line INT,
  end_line INT,
  embedding vector(768)
);

CREATE INDEX IF NOT EXISTS chunks_repo_idx ON chunks(repo_id);
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
  ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  repo_id TEXT REFERENCES repos(id) ON DELETE SET NULL,
  bug_text TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  diff TEXT,
  test_log TEXT,
  prompt_tokens INT DEFAULT 0,
  completion_tokens INT DEFAULT 0,
  tokens_per_sec DOUBLE PRECISION,
  created_at TIMESTAMPTZ DEFAULT now()
);
