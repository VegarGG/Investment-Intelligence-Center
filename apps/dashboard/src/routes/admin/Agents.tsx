// Settings → Agents (P3.8). Read/edit featureflags YAML.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Card } from "../../components/ui/Card";
import { admin } from "../../lib/api";

const REL = "packages/featureflags/flags.yaml";

export function AgentsAdmin() {
  const qc = useQueryClient();
  const file = useQuery({
    queryKey: ["admin", "file", REL],
    queryFn: () => admin.readFile(REL),
  });
  const [content, setContent] = useState<string>("");
  useEffect(() => {
    if (file.data) setContent(file.data.content);
  }, [file.data]);

  const apply = useMutation({
    mutationFn: () => admin.applyFile(REL, content, "agents/flags update via UI"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "file", REL] }),
  });

  return (
    <Card title="Settings → Agents / Feature Flags">
      <p className="mb-3 text-xs text-zinc-500">
        Direct editor on <code>{REL}</code>. Per-agent enable/disable and per-caller
        concurrency overrides live as YAML keys here.
      </p>
      <textarea
        className="h-96 w-full rounded bg-zinc-900 p-2 font-mono text-xs"
        value={content}
        onChange={(e) => setContent(e.target.value)}
      />
      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={() => apply.mutate()}
          className="rounded bg-emerald-700 px-3 py-1 text-xs hover:bg-emerald-600"
          disabled={apply.isPending}
        >
          {apply.isPending ? "Saving…" : "Save flags.yaml"}
        </button>
        {apply.isSuccess && (
          <span className="text-xs text-zinc-400">
            audit_id={apply.data.audit_id.slice(0, 8)}…
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
