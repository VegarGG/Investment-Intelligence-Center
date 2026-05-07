import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import type { BiasBalance } from "../types/iic";

const PALETTE = [
  "#34d399",
  "#60a5fa",
  "#fbbf24",
  "#f472b6",
  "#a78bfa",
  "#f87171",
  "#22d3ee",
];

export function BiasBalanceChart({ balance }: { balance: BiasBalance | undefined }) {
  if (!balance || Object.keys(balance.by_region).length === 0) {
    return <p className="text-sm text-zinc-500">No bias balance yet.</p>;
  }
  const data = Object.entries(balance.by_region).map(([region, share]) => ({
    name: region,
    value: share,
  }));
  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" outerRadius={80} stroke="#0f0f12">
          {data.map((entry, idx) => (
            <Cell key={entry.name} fill={PALETTE[idx % PALETTE.length]} />
          ))}
        </Pie>
        <Tooltip
          formatter={(v: number) => `${(v * 100).toFixed(1)}%`}
          contentStyle={{ background: "#0f0f12", border: "1px solid #27272a" }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
