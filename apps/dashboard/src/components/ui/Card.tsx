import type { ReactNode } from "react";

export function Card({
  title,
  children,
  className = "",
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-2xl border border-zinc-800 bg-zinc-900/40 p-5 ${className}`}
    >
      {title && (
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wider text-zinc-400">
          {title}
        </h2>
      )}
      <div className="text-zinc-200">{children}</div>
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-md bg-zinc-800/60 ${className}`}
      aria-hidden="true"
    />
  );
}

export function Badge({
  children,
  tone = "default",
}: {
  children: ReactNode;
  tone?: "default" | "good" | "warn" | "bad";
}) {
  const palette: Record<string, string> = {
    default: "bg-zinc-800 text-zinc-200",
    good: "bg-emerald-900/60 text-emerald-200",
    warn: "bg-amber-900/60 text-amber-200",
    bad: "bg-rose-900/60 text-rose-200",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${palette[tone]}`}
    >
      {children}
    </span>
  );
}
