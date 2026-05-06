export function App() {
  return (
    <main className="min-h-screen p-8">
      <header className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight">IIC v2.1</h1>
        <p className="text-zinc-400">
          Investment Intelligence Center — Phase 0 dashboard placeholder.
        </p>
      </header>
      <section className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card title="Today's brief">No brief yet — Phase 1 will wire this.</Card>
        <Card title="Leaderboard">No agents live yet — Phase 6 will wire this.</Card>
        <Card title="Trade tape">No virtual fills yet — Phase 6 will wire this.</Card>
      </section>
      <footer className="mt-12 text-xs text-zinc-500">
        For personal research only. Not investment advice. /
        仅供个人研究，不构成投资建议。
      </footer>
    </main>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-5">
      <h2 className="mb-2 text-sm font-medium uppercase tracking-wider text-zinc-400">
        {title}
      </h2>
      <div className="text-zinc-200">{children}</div>
    </div>
  );
}
