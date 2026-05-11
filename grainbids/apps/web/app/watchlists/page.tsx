import Link from "next/link";
import { API_BASE, buildApiHeaders } from "@/lib/api";

const headers = buildApiHeaders();

async function fetchWatchlists() {
  try {
    const res = await fetch(`${API_BASE}/api/watchlists`, { cache: "no-store", headers });
    if (!res.ok) return [];
    const json = await res.json();
    return json.rows || [];
  } catch {
    return [];
  }
}

export default async function WatchlistsPage() {
  const rows = await fetchWatchlists();
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <p className="text-xs uppercase tracking-[0.16em] text-black/50">GrainBids / Watchlists</p>
      <h1 className="mt-1 font-[family-name:var(--font-serif)] text-4xl leading-tight">Watchlists</h1>
      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Tracked bids</h2>
        <p className="mt-2 text-sm text-black/65">Saved views of the market data users track frequently.</p>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-black/10 text-xs uppercase tracking-wide text-black/50">
                <th className="px-2 py-2">Name</th>
                <th className="px-2 py-2">Active</th>
                <th className="px-2 py-2">Updated</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td className="px-2 py-4 text-black/55" colSpan={3}>
                    No watchlists yet.
                  </td>
                </tr>
              ) : (
                rows.map((row: any) => (
                  <tr key={row.id} className="border-b border-black/5">
                    <td className="px-2 py-2">{row.name}</td>
                    <td className="px-2 py-2">{row.is_active ? "yes" : "no"}</td>
                    <td className="px-2 py-2">{row.updated_at ? new Date(row.updated_at).toLocaleString() : "-"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <Link href="/bids" className="mt-4 inline-flex rounded-md border border-black/20 bg-white/80 px-3 py-2 text-sm hover:border-black/40">
          Start from bids
        </Link>
      </section>
    </main>
  );
}
