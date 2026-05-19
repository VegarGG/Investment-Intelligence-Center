// Settings → Connectors (P3.4). One row per known provider + test button.
import { useQuery, useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { Card } from "../../components/ui/Card";
import { admin, type AdminConnectorStatus } from "../../lib/api";

export function ConnectorsAdmin() {
  const connectors = useQuery({
    queryKey: ["admin", "connectors"],
    queryFn: admin.listConnectors,
  });
  const secrets = useQuery({
    queryKey: ["admin", "secrets"],
    queryFn: admin.listSecrets,
  });
  const [status, setStatus] = useState<Record<string, AdminConnectorStatus>>({});
  const test = useMutation({
    mutationFn: (name: string) => admin.testConnector(name),
    onSuccess: (data, name) => setStatus((s) => ({ ...s, [name]: data })),
  });

  if (connectors.isLoading) return <p>Loading…</p>;
  const present = new Set(
    (secrets.data?.secrets ?? []).filter((s) => s.present).map((s) => s.name),
  );

  return (
    <Card title="Settings → Connectors">
      <p className="mb-3 text-xs text-zinc-500">
        Each connector reads its credential from `secrets/sealed/&lt;name&gt;.yaml.enc`.
        Rotating a secret routes through `/admin/secrets/&lt;name&gt;/rotate`. The
        plaintext is never returned to the dashboard once stored.
      </p>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800 text-left text-xs uppercase tracking-wider text-zinc-500">
            <th className="py-2">Connector</th>
            <th>Credential</th>
            <th>Last test</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {(connectors.data?.connectors ?? []).map((name) => {
            const credentialKey = `${name}_api_key`;
            const has = present.has(credentialKey) || present.has(`${name}_password`);
            const st = status[name];
            return (
              <tr key={name} className="border-b border-zinc-900/60">
                <td className="py-2 font-mono">{name}</td>
                <td>{has ? "•••• stored" : <span className="text-amber-400">unset</span>}</td>
                <td>
                  {st ? (
                    <span
                      className={
                        st.state === "ok"
                          ? "text-emerald-400"
                          : st.state === "error"
                            ? "text-rose-400"
                            : "text-zinc-400"
                      }
                    >
                      {st.state} {st.detail ? `— ${st.detail}` : ""}
                    </span>
                  ) : (
                    <span className="text-zinc-500">—</span>
                  )}
                </td>
                <td>
                  <button
                    onClick={() => test.mutate(name)}
                    className="rounded bg-zinc-800 px-3 py-1 text-xs hover:bg-zinc-700"
                  >
                    Test
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}
