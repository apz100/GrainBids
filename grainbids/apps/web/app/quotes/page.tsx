import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

async function fetchQuoteRuns() {
  try {
    const res = await fetch(`${API_BASE}/api/quotes/runs?limit=25`, { cache: "no-store" });
    if (!res.ok) return [];
    const json = await res.json();
    return json.rows || [];
  } catch {
    return [];
  }
}

export default async function QuotesPage() {
  const rows = await fetchQuoteRuns();
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <p className="text-xs uppercase tracking-[0.16em] text-black/50">GrainBids / Quotes</p>
      <h1 className="mt-1 font-[family-name:var(--font-serif)] text-4xl leading-tight">Quotes</h1>
      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Quote builder foundation</h2>
        <p className="mt-2 text-sm text-black/65">Recent quote generation runs and export status.</p>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-black/10 text-xs uppercase tracking-wide text-black/50">
                <th className="px-2 py-2">Generated</th>
                <th className="px-2 py-2">Status</th>
                <th className="px-2 py-2">Output</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td className="px-2 py-4 text-black/55" colSpan={3}>
                    No quote runs yet.
                  </td>
                </tr>
              ) : (
                rows.map((row: any) => (
                  <tr key={row.id} className="border-b border-black/5">
                    <td className="px-2 py-2">{row.generated_at ? new Date(row.generated_at).toLocaleString() : "-"}</td>
                    <td className="px-2 py-2">{row.status}</td>
                    <td className="px-2 py-2">{row.output_file_url || "-"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <Link href="/bids" className="mt-4 inline-flex rounded-md border border-black/20 bg-white/80 px-3 py-2 text-sm hover:border-black/40">
          View market bids
        </Link>
      </section>
    </main>
  );
}
