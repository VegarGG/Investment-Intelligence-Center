import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";

import { api } from "../lib/api";
import { formatPct } from "../lib/format";
import { RegimeBadge } from "./RegimeBadge";
import { ToneSlider } from "./ToneSlider";
import { Badge } from "./ui/Card";

const NAV: { to: string; label: string }[] = [
  { to: "/", label: "Home" },
  { to: "/leaderboard", label: "Leaderboard" },
  { to: "/tape", label: "Trade Tape" },
  { to: "/intel", label: "Intel" },
  { to: "/quant", label: "Quant" },
  { to: "/fundamental", label: "Fundamental" },
  { to: "/personas", label: "Personas" },
  { to: "/chat", label: "Chat" },
  { to: "/health", label: "Health" },
];

export function Shell({ children }: { children: ReactNode }) {
  const digest = useQuery({ queryKey: ["intel", "digest"], queryFn: api.intelDigestToday });
  const llm = useQuery({ queryKey: ["health", "llm"], queryFn: api.llmSpend });

  const burnPct =
    llm.data && llm.data.monthly_cap_usd > 0
      ? llm.data.month_to_date_usd / llm.data.monthly_cap_usd
      : null;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <header className="border-b border-zinc-800 bg-zinc-950/95 backdrop-blur">
        <div className="mx-auto flex max-w-screen-2xl items-center justify-between gap-4 px-4 py-3">
          <Link to="/" className="flex items-center gap-2 text-sm font-semibold tracking-tight">
            <span className="rounded bg-emerald-700/40 px-2 py-1 text-xs uppercase text-emerald-200">
              IIC
            </span>
            <span>Investment Intelligence Center</span>
          </Link>
          <div className="flex items-center gap-3">
            <RegimeBadge regime={digest.data?.macro_regime} />
            {burnPct !== null && (
              <Badge
                tone={burnPct > 0.9 ? "bad" : burnPct > 0.7 ? "warn" : "good"}
              >
                LLM {formatPct(burnPct)}
              </Badge>
            )}
            <ToneSlider />
          </div>
        </div>
        <nav className="border-t border-zinc-800 bg-zinc-950">
          <ul className="mx-auto flex max-w-screen-2xl gap-2 overflow-x-auto px-4 py-2 text-sm">
            {NAV.map((n) => (
              <li key={n.to}>
                <NavLink
                  to={n.to}
                  end={n.to === "/"}
                  className={({ isActive }) =>
                    `rounded-md px-3 py-1 ${
                      isActive
                        ? "bg-emerald-900/40 text-emerald-200"
                        : "text-zinc-400 hover:text-zinc-100"
                    }`
                  }
                >
                  {n.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main className="mx-auto max-w-screen-2xl p-4">{children}</main>
      <footer className="mx-auto max-w-screen-2xl px-4 py-6 text-xs text-zinc-500">
        For personal research only. Not investment advice. /
        仅供个人研究，不构成投资建议。
      </footer>
    </div>
  );
}
