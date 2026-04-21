import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

async function fetchRules() {
  try {
    const res = await fetch(`${API_BASE}/api/alerts/rules`, { cache: "no-store" });
    if (!res.ok) return [];
    const json = await res.json();
    return json.rows || [];
  } catch {
    return [];
  }
}

export default async function AlertsPage() {
  const rows = await fetchRules();
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <p className="text-xs uppercase tracking-[0.16em] text-black/50">GrainBids / Alerts</p>
      <h1 className="mt-1 font-[family-name:var(--font-serif)] text-4xl leading-tight">Alerts</h1>
      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Alert rules</h2>
        <p className="mt-2 text-sm text-black/65">Configured basis and delivered-value thresholds.</p>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-black/10 text-xs uppercase tracking-wide text-black/50">
                <th className="px-2 py-2">Type</th>
                <th className="px-2 py-2">Operator</th>
                <th className="px-2 py-2">Threshold</th>
                <th className="px-2 py-2">Last Trigger</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td className="px-2 py-4 text-black/55" colSpan={4}>
                    No alert rules yet.
                  </td>
                </tr>
              ) : (
                rows.map((row: any) => (
                  <tr key={row.id} className="border-b border-black/5">
                    <td className="px-2 py-2">{row.rule_type}</td>
                    <td className="px-2 py-2">{row.comparison_operator}</td>
                    <td className="px-2 py-2">{row.threshold_value}</td>
                    <td className="px-2 py-2">{row.last_triggered_at ? new Date(row.last_triggered_at).toLocaleString() : "-"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <Link href="/bids" className="mt-4 inline-flex rounded-md border border-black/20 bg-white/80 px-3 py-2 text-sm hover:border-black/40">
          Review bids
        </Link>
      </section>
    </main>
  );
}
