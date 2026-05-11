"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import OpenAlertsPanel from "./open-alerts-panel";
import { API_BASE, buildApiHeaders } from "@/lib/api";

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
  source_name: string | null;
  basis_change: number | null;
  cash_price_bu_change: number | null;
  captured_at: string | null;
};

type PreviewRow = {
  id: string;
  captured_at: string | null;
  location: string;
  source_name: string | null;
  commodity_name: string;
  delivery_label: string | null;
  futures_month: string | null;
  futures_price: number | null;
  basis: number | null;
  basis_change: number | null;
  cash_price_bu: number | null;
  cash_price_bu_change: number | null;
  cash_price_mt: number | null;
  cash_price_mt_change: number | null;
};

type FacetsResponse = {
  commodities: string[];
  locations: string[];
  source_names: string[];
};

type SlaSummary = {
  active_sources: number;
  fresh_sources: number;
  failing_sources: number;
  latest_quality?: {
    parse_success_rate: number;
    rejected_row_count: number;
    missing_required_count: number;
  } | null;
  last_successful_ingestion_run?: {
    started_at: string | null;
  } | null;
};

const COMMODITY_TABS = ["Corn", "Soybeans", "Wheat", "All"] as const;

type FilterState = {
  commodity: string;
  location: string;
  source_name: string;
  captured_date: string;
  sort: "captured_desc" | "basis_change_desc" | "basis_desc" | "cash_bu_desc";
};

const DEFAULT_FILTERS: FilterState = {
  commodity: "Corn",
  location: "",
  source_name: "",
  captured_date: "",
  sort: "captured_desc",
};

export default function DashboardPage() {
  const headers = useMemo(() => buildApiHeaders(), []);
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [facets, setFacets] = useState<FacetsResponse>({ commodities: [], locations: [], source_names: [] });
  const [previewRows, setPreviewRows] = useState<PreviewRow[]>([]);
  const [movers, setMovers] = useState<TopMover[]>([]);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [sla, setSla] = useState<SlaSummary | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [loadingMeta, setLoadingMeta] = useState(false);
  const [error, setError] = useState("");

  const topLocations = useMemo(() => facets.locations.slice(0, 8), [facets.locations]);
  const topSources = useMemo(() => facets.source_names.slice(0, 8), [facets.source_names]);

  useEffect(() => {
    void loadMeta();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void loadMarketData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters]);

  async function loadMeta() {
    setLoadingMeta(true);
    setError("");
    try {
      const [slaRes, facetsRes] = await Promise.all([
        fetch(`${API_BASE}/api/ingestion/sla`, { cache: "no-store", headers }),
        fetch(`${API_BASE}/api/normalized-prices/facets`, { cache: "no-store", headers }),
      ]);

      if (!slaRes.ok) throw new Error(await readFailure(slaRes));
      if (!facetsRes.ok) throw new Error(await readFailure(facetsRes));

      setSla(await slaRes.json());
      setFacets(await facetsRes.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoadingMeta(false);
    }
  }

  async function loadMarketData() {
    setLoadingPreview(true);
    setError("");
    try {
      const query = buildMarketQuery(filters);
      const [previewRes, moversRes, summaryRes] = await Promise.all([
        fetch(`${API_BASE}/api/normalized-prices/preview${query}&limit=120`, { cache: "no-store", headers }),
        fetch(`${API_BASE}/api/normalized-prices/top-movers${query}&limit=8`, { cache: "no-store", headers }),
        fetch(`${API_BASE}/api/normalized-prices/summary${query}`, { cache: "no-store", headers }),
      ]);

      if (!previewRes.ok) throw new Error(await readFailure(previewRes));
      if (!moversRes.ok) throw new Error(await readFailure(moversRes));
      if (!summaryRes.ok) throw new Error(await readFailure(summaryRes));

      setPreviewRows((await previewRes.json()).rows ?? []);
      setMovers((await moversRes.json()).rows ?? []);
      setSummary(await summaryRes.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoadingPreview(false);
    }
  }

  function setCommodityTab(tab: (typeof COMMODITY_TABS)[number]) {
    setFilters((prev) => ({ ...prev, commodity: tab === "All" ? "" : tab }));
  }

  function resetFilters() {
    setFilters(DEFAULT_FILTERS);
  }

  return (
    <main className="mx-auto max-w-7xl px-6 py-7">
      <header className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.16em] text-black/50">GrainBids / Market</p>
          <h1 className="mt-1 font-[family-name:var(--font-serif)] text-4xl leading-tight">Bid Intelligence Dashboard</h1>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <StatusBadge summary={sla} />
          <Link href="/sources" className="rounded-md border border-black/20 bg-white px-3 py-2 hover:border-black/40">
            Admin
          </Link>
          <Link href="/sources" className="rounded-xl border border-black/15 bg-white/70 px-4 py-2 text-sm hover:border-black/30">
            Sources
          </Link>
        </div>
      </header>

      <section className="sticky top-14 z-20 rounded-xl border border-black/10 bg-white/90 p-4 shadow-sm backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            {COMMODITY_TABS.map((tab) => {
              const active = (filters.commodity || "All").toLowerCase() === tab.toLowerCase();
              return (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setCommodityTab(tab)}
                  className={`rounded-md border px-3 py-1.5 text-xs font-medium ${
                    active ? "border-black bg-black text-white" : "border-black/20 bg-white text-black/70"
                  }`}
                >
                  {tab}
                </button>
              );
            })}
          </div>
          <div className="flex items-center gap-2 text-xs text-black/65">
            <span>Rows: {summary?.row_count ?? 0}</span>
            <span>|</span>
            <span>Avg basis: {formatNumber(summary?.average_basis)}</span>
            <span>|</span>
            <span>Open alerts: {summary?.open_alerts ?? 0}</span>
          </div>
        </div>

        <div className="mt-3 grid gap-2 md:grid-cols-[1fr_1fr_1fr_160px_160px]">
          <select
            value={filters.location}
            onChange={(event) => setFilters((prev) => ({ ...prev, location: event.target.value }))}
            className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
          >
            <option value="">All locations</option>
            {facets.locations.map((location) => (
              <option key={location} value={location}>
                {location}
              </option>
            ))}
          </select>
          <select
            value={filters.source_name}
            onChange={(event) => setFilters((prev) => ({ ...prev, source_name: event.target.value }))}
            className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
          >
            <option value="">All companies</option>
            {facets.source_names.map((source) => (
              <option key={source} value={source}>
                {source}
              </option>
            ))}
          </select>
          <select
            value={filters.sort}
            onChange={(event) => setFilters((prev) => ({ ...prev, sort: event.target.value as FilterState["sort"] }))}
            className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
          >
            <option value="captured_desc">Newest first</option>
            <option value="basis_change_desc">Biggest basis change</option>
            <option value="basis_desc">Highest basis</option>
            <option value="cash_bu_desc">Highest cash/bu</option>
          </select>
          <input
            type="date"
            value={filters.captured_date}
            onChange={(event) => setFilters((prev) => ({ ...prev, captured_date: event.target.value }))}
            className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
          />
          <button type="button" onClick={resetFilters} className="rounded-md border border-black/20 bg-white px-3 py-2 text-sm">
            Reset
          </button>
        </div>

        <FacetChips
          label="Location"
          values={topLocations}
          activeValue={filters.location}
          onSelect={(value) => setFilters((prev) => ({ ...prev, location: value === prev.location ? "" : value }))}
        />
        <FacetChips
          label="Company"
          values={topSources}
          activeValue={filters.source_name}
          onSelect={(value) => setFilters((prev) => ({ ...prev, source_name: value === prev.source_name ? "" : value }))}
        />
      </section>

      <section className="mt-4 rounded-xl border border-black/10 bg-white/85 shadow-sm">
        <div className="flex items-center justify-between border-b border-black/10 px-4 py-3">
          <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-black/70">Live Price Preview</h2>
          {loadingPreview ? <span className="text-xs text-black/60">Refreshing…</span> : null}
        </div>
        {error ? <p className="px-4 py-2 text-sm text-red-700">{error}</p> : null}
        <div className="max-h-[520px] overflow-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="sticky top-0 bg-white">
              <tr className="border-b border-black/10 text-xs uppercase tracking-wide text-black/55">
                <th className="px-3 py-2">Location</th>
                <th className="px-3 py-2">Company</th>
                <th className="px-3 py-2">Commodity</th>
                <th className="px-3 py-2">Delivery</th>
                <th className="px-3 py-2">Futures</th>
                <th className="px-3 py-2 text-right">Fut Px</th>
                <th className="px-3 py-2 text-right">Basis</th>
                <th className="px-3 py-2 text-right">Basis Chg</th>
                <th className="px-3 py-2 text-right">Cash/Bu</th>
                <th className="px-3 py-2 text-right">Bu Chg</th>
                <th className="px-3 py-2 text-right">Cash/MT</th>
                <th className="px-3 py-2 text-right">MT Chg</th>
              </tr>
            </thead>
            <tbody>
              {previewRows.length === 0 ? (
                <tr>
                  <td colSpan={12} className="px-3 py-8 text-center text-sm text-black/55">
                    No rows for the selected filters.
                  </td>
                </tr>
              ) : (
                previewRows.map((row) => (
                  <tr key={row.id} className="border-b border-black/5">
                    <td className="px-3 py-2">{row.location}</td>
                    <td className="px-3 py-2">{row.source_name || "-"}</td>
                    <td className="px-3 py-2">{row.commodity_name}</td>
                    <td className="px-3 py-2">{row.delivery_label || "-"}</td>
                    <td className="px-3 py-2">{row.futures_month || "-"}</td>
                    <td className="px-3 py-2 text-right">{formatNumber(row.futures_price)}</td>
                    <td className="px-3 py-2 text-right">{formatNumber(row.basis)}</td>
                    <td className={`px-3 py-2 text-right ${toneForDelta(row.basis_change)}`}>{formatSigned(row.basis_change)}</td>
                    <td className="px-3 py-2 text-right">{formatNumber(row.cash_price_bu)}</td>
                    <td className={`px-3 py-2 text-right ${toneForDelta(row.cash_price_bu_change)}`}>{formatSigned(row.cash_price_bu_change)}</td>
                    <td className="px-3 py-2 text-right">{formatNumber(row.cash_price_mt)}</td>
                    <td className={`px-3 py-2 text-right ${toneForDelta(row.cash_price_mt_change)}`}>{formatSigned(row.cash_price_mt_change)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-4 rounded-xl border border-black/10 bg-white/85 p-4 shadow-sm">
        <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-black/70">Top Basis Movers</h2>
        <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {movers.length === 0 ? (
            <p className="text-sm text-black/55">No mover data available for the current filters.</p>
          ) : (
            movers.map((mover) => (
              <article key={mover.id} className="rounded-md border border-black/10 bg-white p-3">
                <p className="text-sm font-semibold">{mover.location}</p>
                <p className="text-xs text-black/60">{mover.source_name || "-"} / {mover.commodity_name}</p>
                <p className={`mt-2 text-sm ${toneForDelta(mover.basis_change)}`}>Basis: {formatSigned(mover.basis_change)}</p>
                <p className={`text-xs ${toneForDelta(mover.cash_price_bu_change)}`}>Cash/Bu: {formatSigned(mover.cash_price_bu_change)}</p>
              </article>
            ))
          )}
        </div>
      </section>

      <OpenAlertsPanel />

      {(loadingMeta || loadingPreview) && !error ? (
        <p className="mt-3 text-xs text-black/60">
          Last successful ingestion:{" "}
          {sla?.last_successful_ingestion_run?.started_at
            ? new Date(sla.last_successful_ingestion_run.started_at).toLocaleString()
            : "-"}
        </p>
      ) : null}
    </main>
  );
}

function FacetChips({
  label,
  values,
  activeValue,
  onSelect,
}: {
  label: string;
  values: string[];
  activeValue: string;
  onSelect: (value: string) => void;
}) {
  if (values.length === 0) {
    return null;
  }
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <span className="text-xs uppercase tracking-[0.1em] text-black/55">{label}</span>
      {values.map((value) => {
        const active = value === activeValue;
        return (
          <button
            key={value}
            type="button"
            onClick={() => onSelect(value)}
            className={`rounded-full border px-2.5 py-1 text-xs ${
              active ? "border-black bg-black text-white" : "border-black/15 bg-white text-black/70"
            }`}
          >
            {value}
          </button>
        );
      })}
    </div>
  );
}

function StatusBadge({ summary }: { summary: SlaSummary | null }) {
  if (!summary || summary.active_sources === 0) {
    return <span className="rounded-md border border-black/15 bg-white px-2 py-1">No sources</span>;
  }
  const healthy = summary.failing_sources === 0 && summary.fresh_sources === summary.active_sources;
  const tone = healthy ? "border-emerald-700/20 bg-emerald-100 text-emerald-900" : "border-amber-700/20 bg-amber-100 text-amber-900";
  return (
    <span className={`rounded-md border px-2 py-1 ${tone}`}>
      Fresh {summary.fresh_sources}/{summary.active_sources} | Fail {summary.failing_sources}
    </span>
  );
}

function buildMarketQuery(filters: FilterState) {
  const params = new URLSearchParams();
  if (filters.commodity) params.set("commodity", filters.commodity);
  if (filters.location) params.set("location", filters.location);
  if (filters.source_name) params.set("source_name", filters.source_name);
  if (filters.captured_date) params.set("captured_date", filters.captured_date);
  if (filters.sort) params.set("sort", filters.sort);
  const query = params.toString();
  return query ? `?${query}` : "";
}

async function readFailure(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    return JSON.stringify(body.detail || body);
  } catch {
    return `${res.status} ${res.statusText}`;
  }
}

function toneForDelta(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value) || value === 0) return "text-black/70";
  return value > 0 ? "text-emerald-700" : "text-rose-700";
}

function formatNumber(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "-";
  return value.toFixed(2);
}

function formatSigned(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}`;
}
