"use client";

import Link from "next/link";
import { useState } from "react";
import DiffView from "@/components/DiffView";
import {
  createRun,
  indexRepo,
  type IndexResponse,
  type RunResponse,
} from "@/lib/api";

const inputCls =
  "w-full rounded-lg border border-black/10 bg-white px-3 py-2 font-mono text-sm text-zinc-900 placeholder:text-zinc-400 dark:border-white/10 dark:bg-zinc-900 dark:text-zinc-100";
const btnCls =
  "rounded-full bg-foreground px-5 py-2.5 text-sm font-medium text-background transition-colors hover:bg-[#383838] disabled:opacity-50 dark:hover:bg-[#ccc]";
const cardCls =
  "rounded-xl border border-black/10 bg-white p-5 dark:border-white/10 dark:bg-zinc-900";

function StatusBadge({ status }: { status: string }) {
  const color =
    status === "fixed"
      ? "bg-green-500/15 text-green-700 dark:text-green-300"
      : status === "tests_failed" || status === "patch_invalid"
        ? "bg-red-500/15 text-red-700 dark:text-red-300"
        : "bg-zinc-500/15 text-zinc-700 dark:text-zinc-300";
  return (
    <span className={`rounded-full px-3 py-1 font-mono text-xs font-semibold ${color}`}>
      {status}
    </span>
  );
}

export default function Home() {
  const [source, setSource] = useState("");
  const [useGit, setUseGit] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [indexed, setIndexed] = useState<IndexResponse | null>(null);
  const [bug, setBug] = useState("");
  const [running, setRunning] = useState(false);
  const [run, setRun] = useState<RunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onIndex() {
    setError(null);
    setIndexed(null);
    setIndexing(true);
    try {
      const res = await indexRepo(
        useGit ? { git_url: source } : { local_path: source },
      );
      setIndexed(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setIndexing(false);
    }
  }

  async function onRun() {
    if (!indexed) return;
    setError(null);
    setRun(null);
    setRunning(true);
    try {
      const res = await createRun({
        repo_id: indexed.repo_id,
        bug_text: bug,
        timeout_s: 180,
      });
      setRun(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col items-center bg-zinc-50 font-sans dark:bg-black">
      <main className="flex w-full max-w-4xl flex-1 flex-col gap-6 px-6 py-12">
        <header>
          <h1 className="text-3xl font-semibold tracking-tight text-black dark:text-zinc-50">
            PatchPilot
          </h1>
          <p className="mt-1 text-zinc-600 dark:text-zinc-400">
            Index a repo → describe the bug → get a sandbox-verified diff.
          </p>
        </header>

        {error && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 font-mono text-sm text-red-700 dark:text-red-300">
            {error}
          </div>
        )}

        <section className={cardCls}>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
            1. Index repo
          </h2>
          <div className="mb-3 flex gap-4 text-sm">
            <label className="flex items-center gap-1.5">
              <input
                type="radio"
                checked={!useGit}
                onChange={() => setUseGit(false)}
              />
              Local path
            </label>
            <label className="flex items-center gap-1.5">
              <input type="radio" checked={useGit} onChange={() => setUseGit(true)} />
              Git URL
            </label>
          </div>
          <div className="flex gap-2">
            <input
              className={inputCls}
              placeholder={
                useGit ? "https://github.com/org/repo" : "/abs/path/to/repo"
              }
              value={source}
              onChange={(e) => setSource(e.target.value)}
            />
            <button className={btnCls} disabled={indexing || !source} onClick={onIndex}>
              {indexing ? "Indexing…" : "Index"}
            </button>
          </div>
          {indexed && (
            <p className="mt-3 font-mono text-xs text-zinc-600 dark:text-zinc-400">
              {indexed.repo_id} · {indexed.stats.files} files ·{" "}
              {indexed.stats.functions} functions · {indexed.stats.tests} tests
            </p>
          )}
        </section>

        <section className={cardCls}>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
            2. Describe bug &amp; run fix
          </h2>
          <textarea
            className={`${inputCls} min-h-24 font-sans`}
            placeholder="e.g. add(a, b) returns a+b+1 instead of a+b…"
            value={bug}
            onChange={(e) => setBug(e.target.value)}
          />
          <div className="mt-3">
            <button
              className={btnCls}
              disabled={running || !indexed || !bug.trim()}
              onClick={onRun}
            >
              {running ? "Fixing… (up to 3 attempts, may take minutes)" : "Run fix"}
            </button>
          </div>
          {!indexed && (
            <p className="mt-2 text-sm text-zinc-500">Index a repo first.</p>
          )}
        </section>

        {run && (
          <section className={cardCls}>
            <div className="mb-3 flex items-center gap-3">
              <StatusBadge status={run.status} />
              <Link
                href={`/runs/${run.run_id}`}
                className="font-mono text-xs text-blue-600 underline dark:text-blue-400"
              >
                {run.run_id} →
              </Link>
              <span className="font-mono text-xs text-zinc-500">
                {run.attempts} attempt(s) · {run.usage.tokens_per_sec} tok/s
                {run.flaky ? " · flaky" : ""}
              </span>
            </div>
            {run.diff ? (
              <DiffView diff={run.diff} />
            ) : (
              <p className="font-mono text-sm text-zinc-500">
                {run.status === "patch_invalid"
                  ? "No valid diff produced."
                  : "No diff."}
              </p>
            )}
            {run.test_log && (
              <pre className="mt-3 overflow-x-auto rounded-lg bg-zinc-950 p-4 font-mono text-xs leading-5 text-zinc-200">
                {run.test_log}
              </pre>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
