export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ChunkOut {
  path: string;
  lang: string;
  name: string;
  content: string;
  is_test: boolean;
  start_line: number | null;
  end_line: number | null;
  score: number;
  sources: string[];
}

export interface IndexResponse {
  repo_id: string;
  sha: string | null;
  source: string;
  persisted: boolean;
  chunks: ChunkOut[];
  stats: { files: number; functions: number; tests: number; naive_chunks: number };
}

export interface UsageOut {
  prompt_tokens: number;
  completion_tokens: number;
  latency_s: number;
  tokens_per_sec: number;
}

export interface RunResponse {
  run_id: string;
  repo_id: string;
  status: string;
  diff: string | null;
  test_log: string | null;
  attempts: number;
  flaky: boolean;
  usage: UsageOut;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      (body as { detail?: string }).detail ?? `API ${res.status} on ${path}`,
    );
  }
  return res.json() as Promise<T>;
}

export function indexRepo(body: {
  git_url?: string;
  local_path?: string;
  sha?: string;
  persist?: boolean;
}): Promise<IndexResponse> {
  return request<IndexResponse>("/repos/index", {
    method: "POST",
    body: JSON.stringify({ persist: true, ...body }),
  });
}

export function createRun(body: {
  repo_id: string;
  bug_text: string;
  top_k?: number;
  max_attempts?: number;
  timeout_s?: number;
}): Promise<RunResponse> {
  return request<RunResponse>("/runs", {
    method: "POST",
    body: JSON.stringify({ top_k: 5, max_attempts: 3, ...body }),
  });
}

export function getRun(runId: string): Promise<RunResponse> {
  return request<RunResponse>(`/runs/${runId}`);
}
