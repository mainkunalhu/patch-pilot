"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import DiffView from "@/components/DiffView";
import { getRun, type RunResponse } from "@/lib/api";

export default function RunPage(props: PageProps<"/runs/[id]">) {
  const { id } = use(props.params);
  const [run, setRun] = useState<RunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getRun(id).then(setRun).catch((e) => setError(String(e)));
  }, [id]);

  return (
    <div className="flex min-h-full flex-col items-center bg-zinc-50 font-sans dark:bg-black">
      <main className="flex w-full max-w-4xl flex-1 flex-col gap-4 px-6 py-12">
        <Link href="/" className="text-sm text-zinc-500 underline">
          ← PatchPilot
        </Link>
        <h1 className="font-mono text-lg text-black dark:text-zinc-50">{id}</h1>
        {error && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 font-mono text-sm text-red-700 dark:text-red-300">
            {error}
          </div>
        )}
        {!run && !error && <p className="text-zinc-500">Loading…</p>}
        {run && (
          <>
            <div className="flex flex-wrap items-center gap-3 font-mono text-xs text-zinc-600 dark:text-zinc-400">
              <span className="rounded-full bg-zinc-500/15 px-3 py-1 font-semibold">
                {run.status}
              </span>
              <span>{run.repo_id}</span>
              <span>
                {run.usage.prompt_tokens} prompt + {run.usage.completion_tokens}{" "}
                completion tokens · {run.usage.tokens_per_sec} tok/s
              </span>
              {run.flaky && <span>flaky</span>}
            </div>
            {run.diff ? (
              <DiffView diff={run.diff} />
            ) : (
              <p className="font-mono text-sm text-zinc-500">No diff stored.</p>
            )}
            <h2 className="mt-2 text-sm font-semibold uppercase tracking-wide text-zinc-500">
              Test proof
            </h2>
            <pre className="overflow-x-auto rounded-lg bg-zinc-950 p-4 font-mono text-xs leading-5 text-zinc-200">
              {run.test_log ?? "No test log."}
            </pre>
          </>
        )}
      </main>
    </div>
  );
}
