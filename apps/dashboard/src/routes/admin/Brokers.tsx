// Settings → Brokers (P4.2). FUTU OpenD bindings + read-only verify button.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Card } from "../../components/ui/Card";

interface Broker {
  id: string;
  host: string;
  port: number;
  tls_cert: string | null;
  quotation_tier: string;
  max_subscriptions: number;
  notes: string;
}

async function fetchBrokers(): Promise<{ brokers: Broker[] }> {
  const r = await fetch("/api/admin/brokers");
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function applyBrokers(brokers: Broker[]) {
  const r = await fetch("/api/admin/brokers/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ brokers }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

async function verifyBroker(id: string) {
  const r = await fetch(`/api/admin/brokers/${id}/verify`, { method: "POST" });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ ok: boolean; error?: string; data?: unknown }>;
}

export function BrokersAdmin() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["admin", "brokers"], queryFn: fetchBrokers });
  const [rows, setRows] = useState<Broker[]>([]);
  const [statuses, setStatuses] = useState<Record<string, string>>({});

  useEffect(() => {
    if (list.data?.brokers) setRows(list.data.brokers);
  }, [list.data]);

  const apply = useMutation({
    mutationFn: () => applyBrokers(rows),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "brokers"] }),
  });

  const verify = useMutation({
    mutationFn: verifyBroker,
    onSuccess: (data, id) =>
      setStatuses((s) => ({ ...s, [id]: data.ok ? "ok" : `error: ${data.error ?? "?"}` })),
  });

  const addRow = () =>
    setRows((r) => [
      ...r,
      {
        id: `futu-${r.length + 1}`,
        host: "127.0.0.1",
        port: 11111,
        tls_cert: null,
        quotation_tier: "free",
        max_subscriptions: 100,
        notes: "",
      },
    ]);

  const update = (i: number, patch: Partial<Broker>) =>
    setRows((r) => r.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));

  return (
    <Card title="Settings → Brokers (FUTU)">
      <p className="mb-3 text-xs text-zinc-500">
        Per-Futu-ID OpenD endpoint. Verify performs a read-only{" "}
        <code>get_global_state</code> round-trip — never an order-touching call.
        Read-only is enforced at the wrapper, lake.futu_audit trigger, and the
        revoked UPDATE/DELETE grants.
      </p>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800 text-left text-xs uppercase tracking-wider text-zinc-500">
            <th className="py-2">FutuID</th>
            <th>host:port</th>
            <th>Tier</th>
            <th>Subs cap</th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((b, i) => (
            <tr key={b.id} className="border-b border-zinc-900/60">
              <td className="py-2 font-mono">
                <input
                  className="w-32 rounded bg-zinc-900 px-2 py-1 font-mono text-xs"
                  value={b.id}
                  onChange={(e) => update(i, { id: e.target.value })}
                />
              </td>
              <td>
                <input
                  className="w-32 rounded bg-zinc-900 px-2 py-1 font-mono text-xs"
                  value={b.host}
                  onChange={(e) => update(i, { host: e.target.value })}
                />
                {" : "}
                <input
                  className="w-16 rounded bg-zinc-900 px-2 py-1 font-mono text-xs"
                  type="number"
                  value={b.port}
                  onChange={(e) => update(i, { port: Number(e.target.value) || 11111 })}
                />
              </td>
              <td>
                <select
                  className="rounded bg-zinc-900 px-2 py-1 text-xs"
                  value={b.quotation_tier}
                  onChange={(e) => update(i, { quotation_tier: e.target.value })}
                >
                  <option value="free">free</option>
                  <option value="level2">level2</option>
                  <option value="level2_plus_a">level2_plus_a</option>
                </select>
              </td>
              <td>
                <input
                  className="w-20 rounded bg-zinc-900 px-2 py-1 font-mono text-xs"
                  type="number"
                  value={b.max_subscriptions}
                  onChange={(e) =>
                    update(i, { max_subscriptions: Number(e.target.value) || 100 })
                  }
                />
              </td>
              <td className="text-xs">{statuses[b.id] ?? "—"}</td>
              <td>
                <button
                  className="rounded bg-zinc-800 px-3 py-1 text-xs hover:bg-zinc-700"
                  onClick={() => verify.mutate(b.id)}
                >
                  Verify
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={addRow}
          className="rounded bg-zinc-800 px-3 py-1 text-xs hover:bg-zinc-700"
        >
          + Add broker
        </button>
        <button
          onClick={() => apply.mutate()}
          className="rounded bg-emerald-700 px-3 py-1 text-xs hover:bg-emerald-600"
          disabled={apply.isPending}
        >
          {apply.isPending ? "Saving…" : "Save brokers"}
        </button>
        <p className="ml-3 text-xs text-amber-400">
          READ-ONLY ENFORCED — the trade-unlock surface is permanently disabled.
        </p>
      </div>
    </Card>
  );
}
