import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

async function fetchSignalsHealth() {
  try {
    const res = await fetch(`${API_BASE}/api/signals/health`, { cache: "no-store" });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

async function fetchForecasts() {
  try {
    const res = await fetch(`${API_BASE}/api/signals/forecast?limit=50`, { cache: "no-store" });
    if (!res.ok) return [];
    const json = await res.json();
    return json.rows || [];
  } catch {
    return [];
  }
}

export default async function SignalsPage() {
  const [health, rows] = await Promise.all([fetchSignalsHealth(), fetchForecasts()]);

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <p className="text-xs uppercase tracking-[0.16em] text-black/50">GrainBids / Signals</p>
      <h1 className="mt-1 font-[family-name:var(--font-serif)] text-4xl leading-tight">Forecast Signals</h1>
      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Model health</h2>
        <div className="mt-2 text-sm text-black/65">
          Forecasts: {health?.forecast_count ?? 0} | Stale (min): {health?.stale_minutes ?? "-"} | Healthy:{" "}
          {health?.healthy ? "yes" : "no"}
        </div>
      </section>

      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Latest forecasts</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-black/10 text-xs uppercase tracking-wide text-black/50">
                <th className="px-2 py-2">Key</th>
                <th className="px-2 py-2">Horizon</th>
                <th className="px-2 py-2">Basis Fcst</th>
                <th className="px-2 py-2">Cash/Bu Fcst</th>
                <th className="px-2 py-2">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td className="px-2 py-4 text-black/55" colSpan={5}>
                    No forecasts yet.
                  </td>
                </tr>
              ) : (
                rows.map((row: any) => (
                  <tr key={row.id} className="border-b border-black/5">
                    <td className="px-2 py-2">{row.composite_key}</td>
                    <td className="px-2 py-2">{row.horizon_minutes}m</td>
                    <td className="px-2 py-2">{row.basis_forecast ?? "-"}</td>
                    <td className="px-2 py-2">{row.cash_price_bu_forecast ?? "-"}</td>
                    <td className="px-2 py-2">{row.confidence_score ?? "-"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <Link href="/bids" className="mt-4 inline-flex rounded-md border border-black/20 bg-white/80 px-3 py-2 text-sm hover:border-black/40">
          Back to bids
        </Link>
      </section>
    </main>
  );
}
