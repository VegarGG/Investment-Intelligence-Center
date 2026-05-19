// Settings → Schedules (P3.5). One row per registered cron job + apply.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Card } from "../../components/ui/Card";
import { admin, type AdminScheduleEntry } from "../../lib/api";

export function SchedulesAdmin() {
  const qc = useQueryClient();
  const crons = useQuery({ queryKey: ["admin", "crons"], queryFn: admin.listCrons });
  const sched = useQuery({ queryKey: ["admin", "schedules"], queryFn: admin.getSchedules });
  const [rows, setRows] = useState<AdminScheduleEntry[]>([]);

  useEffect(() => {
    if (sched.data?.schedules?.length) {
      setRows(sched.data.schedules);
      return;
    }
    if (crons.data?.crons?.length) {
      setRows(
        crons.data.crons.map((c) => ({
          job_id: c.name,
          enabled: true,
          cron: null,
          timezone: null,
        })),
      );
    }
  }, [crons.data, sched.data]);

  const apply = useMutation({
    mutationFn: (entries: AdminScheduleEntry[]) => admin.applySchedules(entries),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "schedules"] }),
  });

  const onToggle = (idx: number) =>
    setRows((rs) => rs.map((r, i) => (i === idx ? { ...r, enabled: !r.enabled } : r)));
  const onCron = (idx: number, v: string) =>
    setRows((rs) => rs.map((r, i) => (i === idx ? { ...r, cron: v || null } : r)));

  return (
    <Card title="Settings → Schedules">
      <p className="mb-3 text-xs text-zinc-500">
        Override cron expressions for the orchestrator's registered jobs. An
        empty `cron` keeps the in-code default. Saving writes `infra/cron/schedules.yaml`
        and chains a row to `lake.config_audit`.
      </p>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800 text-left text-xs uppercase tracking-wider text-zinc-500">
            <th className="py-2">Job ID</th>
            <th>Enabled</th>
            <th>Cron override</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.job_id} className="border-b border-zinc-900/60">
              <td className="py-2 font-mono">{r.job_id}</td>
              <td>
                <input
                  type="checkbox"
                  checked={r.enabled}
                  onChange={() => onToggle(i)}
                />
              </td>
              <td>
                <input
                  className="w-48 rounded bg-zinc-900 px-2 py-1 font-mono text-xs"
                  placeholder="(default)"
                  value={r.cron ?? ""}
                  onChange={(e) => onCron(i, e.target.value)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={() => apply.mutate(rows)}
          className="rounded bg-emerald-700 px-3 py-1 text-xs hover:bg-emerald-600"
          disabled={apply.isPending}
        >
          {apply.isPending ? "Saving…" : "Save schedules"}
        </button>
        {apply.isSuccess && (
          <span className="text-xs text-zinc-400">
            Saved. chain_hash={apply.data.chain_hash.slice(0, 12)}…
          </span>
        )}
        {apply.isError && (
          <span className="text-xs text-rose-400">
            {(apply.error as Error).message}
          </span>
        )}
      </div>
    </Card>
  );
}
