function lineClass(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---")) {
    return "text-zinc-500 dark:text-zinc-400";
  }
  if (line.startsWith("@@")) {
    return "bg-blue-500/10 text-blue-700 dark:text-blue-300";
  }
  if (line.startsWith("+")) {
    return "bg-green-500/10 text-green-800 dark:text-green-300";
  }
  if (line.startsWith("-")) {
    return "bg-red-500/10 text-red-800 dark:text-red-300";
  }
  return "text-zinc-700 dark:text-zinc-300";
}

export default function DiffView({ diff }: { diff: string }) {
  return (
    <pre className="overflow-x-auto rounded-lg border border-black/10 bg-zinc-50 p-4 font-mono text-[13px] leading-6 dark:border-white/10 dark:bg-zinc-950">
      {diff.split("\n").map((line, i) => (
        <div key={i} className={lineClass(line)}>
          {line || " "}
        </div>
      ))}
    </pre>
  );
}
