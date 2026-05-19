// Settings → Notifications (P3.9). Pure YAML editor over preferences.yaml.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Card } from "../../components/ui/Card";
import { admin } from "../../lib/api";

const REL = "infra/notifier/preferences.yaml";
const DEFAULT_BODY = `# Notifier preferences (P3.9).
quiet_hours:
  start: "22:00"
  end:   "07:00"
  timezone: "America/Los_Angeles"

push_frequency: "brief+events"   # one of: brief_only | brief+events | everything

channels:
  wecom_group:
    enabled: true
    severities: [ALERT, WARN, INFO]
  wecom_dm:
    enabled: true
    severities: [ALERT]
  ntfy:
    enabled: false
    severities: []
`;

export function NotificationsAdmin() {
  const qc = useQueryClient();
  const file = useQuery({
    queryKey: ["admin", "file", REL],
    queryFn: () => admin.readFile(REL),
  });
  const [content, setContent] = useState<string>("");
  useEffect(() => {
    if (file.data) setContent(file.data.content || DEFAULT_BODY);
  }, [file.data]);

  const apply = useMutation({
    mutationFn: () => admin.applyFile(REL, content, "notifier prefs via UI"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "file", REL] }),
  });

  return (
    <Card title="Settings → Notifications">
      <p className="mb-3 text-xs text-zinc-500">
        Quiet hours, per-channel severities, push frequency. The secretary
        reads this file before composing each push.
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
          {apply.isPending ? "Saving…" : "Save preferences"}
        </button>
        {apply.isError && (
          <span className="text-xs text-rose-400">{(apply.error as Error).message}</span>
        )}
      </div>
    </Card>
  );
}
