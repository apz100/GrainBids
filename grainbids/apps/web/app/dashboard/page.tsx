import Link from "next/link";

type SummaryResponse = {
  average_basis: number | null;
  row_count: number;
  active_alert_rules: number;
  open_alerts: number;
};

type TopMover = {
  id: string;
  location: string;
  commodity_name: string;
  basis_change: number | null;
  basis: number | null;
  cash_price_bu: number | null;
  cash_price_bu_change: number | null;
  cash_price_mt: number | null;
  cash_price_mt_change: number | null;
  captured_at: string | null;
};

type NormalizedRow = {
  id: string;
  location: string;
  commodity_name: string;
  source_name: string | null;
  delivery_start: string | null;
  delivery_end: string | null;
  delivery_label: string | null;
  futures_month: string | null;
  basis: number | null;
  cash_price_bu: number | null;
  cash_price_mt: number | null;
  basis_change: number | null;
  cash_price_bu_change: number | null;
  cash_price_mt_change: number | null;
  captured_at: string | null;
};

type DbHealth = {
  ok: boolean;
  database: string;
  error?: string;
};

function getApiBase() {
  return process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
}

async function fetchJson<T>(path: string): Promise<T | null> {
  const base = getApiBase();
  try {
    const res = await fetch(`${base}${path}`, { cache: "no-store" });
    if (!res.ok) {
      return null;
    }
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

type DashboardSearchParams = {
  commodity?: string;
  location?: string;
  source_name?: string;
  captured_date?: string;
};

function buildQuery(searchParams: DashboardSearchParams, limit?: number) {
  const params = new URLSearchParams();
  if (searchParams.commodity) params.set("commodity", searchParams.commodity);
  if (searchParams.location) params.set("location", searchParams.location);
  if (searchParams.source_name) params.set("source_name", searchParams.source_name);
  if (searchParams.captured_date) params.set("captured_date", searchParams.captured_date);
  if (limit) params.set("limit", String(limit));
  const query = params.toString();
  return query ? `?${query}` : "";
}

export default async function DashboardPage({ searchParams = {} }: { searchParams?: DashboardSearchParams }) {
  const query = buildQuery(searchParams);
  const limitedQuery = buildQuery(searchParams, 100);

  const [health, summary, moversData, pricesData] = await Promise.all([
    fetchJson<DbHealth>("/api/health/db"),
    fetchJson<SummaryResponse>(`/api/normalized-prices/summary${query}`),
    fetchJson<{ rows: TopMover[] }>(`/api/normalized-prices/top-movers${buildQuery(searchParams, 8)}`),
    fetchJson<{ rows: NormalizedRow[] }>(`/api/normalized-prices${limitedQuery}`),
  ]);

  const movers = moversData?.rows || [];
  const prices = pricesData?.rows || [];

  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-black/50">GrainBids / Bids</p>
          <h1 className="mt-1 font-[family-name:var(--font-serif)] text-4xl leading-tight">Market Dashboard</h1>
          <p className="mt-2 text-sm text-black/65">Live snapshot of normalized bids and basis movement.</p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge health={health} />
          <Link href="/" className="rounded-xl border border-black/15 bg-white/70 px-4 py-2 text-sm hover:border-black/30">
            Home
          </Link>
        </div>
      </header>

      <section className="mt-8 grid gap-4 md:grid-cols-4">
        <MetricCard label="Rows" value={summary?.row_count ?? 0} />
        <MetricCard label="Average Basis" value={summary?.average_basis ?? "-"} />
        <MetricCard label="Active Rules" value={summary?.active_alert_rules ?? 0} />
        <MetricCard label="Open Alerts" value={summary?.open_alerts ?? 0} />
      </section>

      <form className="mt-8 grid gap-3 rounded-lg border border-black/10 bg-white/65 p-4 backdrop-blur md:grid-cols-5">
        <FilterInput name="commodity" label="Commodity" value={searchParams.commodity} />
        <FilterInput name="location" label="Location" value={searchParams.location} />
        <FilterInput name="source_name" label="Source" value={searchParams.source_name} />
        <FilterInput name="captured_date" label="Date" value={searchParams.captured_date} type="date" />
        <div className="flex items-end gap-2">
          <button className="rounded-md border border-black/20 bg-black px-4 py-2 text-sm text-white" type="submit">
            Filter
          </button>
          <Link href="/bids" className="rounded-md border border-black/20 bg-white/80 px-4 py-2 text-sm hover:border-black/40">
            Clear
          </Link>
        </div>
      </form>

      <section className="mt-8 grid gap-6 lg:grid-cols-12">
        <div className="rounded-2xl border border-black/10 bg-white/65 p-5 backdrop-blur lg:col-span-5">
          <h2 className="text-lg font-semibold">Top Movers</h2>
          <p className="mt-1 text-xs text-black/55">Sorted by absolute basis change.</p>
          <div className="mt-4 space-y-3">
            {movers.length === 0 ? (
              <p className="text-sm text-black/55">No mover data yet. Run source-file ingestion first.</p>
            ) : (
              movers.map((mover) => (
                <div key={mover.id} className="rounded-xl border border-black/10 bg-white/70 p-3">
                  <div className="text-sm font-medium">{mover.location}</div>
                  <div className="text-xs text-black/55">{mover.commodity_name}</div>
                  <div className="mt-1 text-sm text-black/75">Basis change: {formatSignedNumber(mover.basis_change)}</div>
                  <div className="text-xs text-black/55">Cash/Bu change: {formatSignedNumber(mover.cash_price_bu_change)}</div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="rounded-2xl border border-black/10 bg-white/65 p-5 backdrop-blur lg:col-span-7">
          <h2 className="text-lg font-semibold">Latest Normalized Bids</h2>
          <p className="mt-1 text-xs text-black/55">Most recent rows from `normalized_prices`.</p>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-black/10 text-xs uppercase tracking-wide text-black/50">
                  <th className="px-2 py-2">Location</th>
                  <th className="px-2 py-2">Source</th>
                  <th className="px-2 py-2">Commodity</th>
                  <th className="px-2 py-2">Delivery</th>
                  <th className="px-2 py-2">Futures</th>
                  <th className="px-2 py-2">Basis</th>
                  <th className="px-2 py-2">Basis Chg</th>
                  <th className="px-2 py-2">Cash/Bu</th>
                  <th className="px-2 py-2">Bu Chg</th>
                  <th className="px-2 py-2">Cash/MT</th>
                  <th className="px-2 py-2">MT Chg</th>
                </tr>
              </thead>
              <tbody>
                {prices.length === 0 ? (
                  <tr>
                    <td className="px-2 py-4 text-sm text-black/55" colSpan={11}>
                      No normalized price rows yet.
                    </td>
                  </tr>
                ) : (
                  prices.map((row) => (
                    <tr key={row.id} className="border-b border-black/5">
                      <td className="px-2 py-2">{row.location}</td>
                      <td className="px-2 py-2">{row.source_name ?? "-"}</td>
                      <td className="px-2 py-2">{row.commodity_name}</td>
                      <td className="px-2 py-2">{row.delivery_label || [row.delivery_start, row.delivery_end].filter(Boolean).join(" - ") || "-"}</td>
                      <td className="px-2 py-2">{row.futures_month ?? "-"}</td>
                      <td className="px-2 py-2">{formatNumber(row.basis)}</td>
                      <td className="px-2 py-2">{formatSignedNumber(row.basis_change)}</td>
                      <td className="px-2 py-2">{formatNumber(row.cash_price_bu)}</td>
                      <td className="px-2 py-2">{formatSignedNumber(row.cash_price_bu_change)}</td>
                      <td className="px-2 py-2">{formatNumber(row.cash_price_mt)}</td>
                      <td className="px-2 py-2">{formatSignedNumber(row.cash_price_mt_change)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </main>
  );
}

function FilterInput({ name, label, value, type = "text" }: { name: string; label: string; value?: string; type?: string }) {
  return (
    <label className="text-sm">
      <span className="text-xs uppercase tracking-wide text-black/50">{label}</span>
      <input
        name={name}
        type={type}
        defaultValue={value || ""}
        className="mt-1 w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
      />
    </label>
  );
}

function StatusBadge({ health }: { health: DbHealth | null }) {
  const ok = !!health?.ok;
  const label = ok ? "DB Connected" : "DB Offline";
  const tone = ok ? "border-emerald-700/20 bg-emerald-100/70 text-emerald-900" : "border-red-700/20 bg-red-100/70 text-red-900";

  return <span className={`rounded-xl border px-3 py-2 text-xs ${tone}`}>{label}</span>;
}

function MetricCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl border border-black/10 bg-white/65 p-4 backdrop-blur">
      <div className="text-xs uppercase tracking-wide text-black/50">{label}</div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
    </div>
  );
}

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "-";
  }
  return Number(value).toFixed(2);
}

function formatSignedNumber(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "-";
  }
  const number = Number(value);
  return `${number > 0 ? "+" : ""}${number.toFixed(2)}`;
}

