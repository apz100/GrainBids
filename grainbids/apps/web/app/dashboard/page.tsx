"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import OpenAlertsPanel from "./open-alerts-panel";
import { API_BASE, buildApiHeaders, getApiConfigError, isAdminRole } from "@/lib/api";

type SummaryResponse = {
  average_basis: number | null;
  row_count: number;
  active_alert_rules: number;
  open_alerts: number;
};

type TopMover = {
  id: string;
  location: string;
  company_name?: string | null;
  commodity_name: string;
  source_name: string | null;
  source_attribution?: string | null;
  basis_change: number | null;
  cash_price_bu_change: number | null;
  captured_at: string | null;
};

type PreviewRow = {
  id: string;
  company_id?: string | null;
  location_id?: string | null;
  captured_at: string | null;
  location: string;
  company_name?: string | null;
  source_name: string | null;
  source_attribution?: string | null;
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
  candidate_count?: number;
  selected_source_key?: string | null;
  canonical_reason?: string | null;
  is_canonical?: boolean;
  canonical_rank?: number | null;
};

type MonthlyPreviewGroup = {
  label: string;
  row_count: number;
  top_cash_price_bu: number | null;
  rows: PreviewRow[];
};

type FacetsResponse = {
  commodities: string[];
  locations: string[];
  source_names: string[];
  company_names: string[];
  region_names: string[];
  company_rows?: { id: string; name: string; market_count?: number }[];
  location_rows?: { id: string; name: string; region: string | null; market_count?: number }[];
};

type WatchlistRow = {
  id: string;
  name: string;
  filters_json: Record<string, string>;
  is_active: boolean;
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
  location_id: string;
  company_id: string;
  region: string;
  captured_date: string;
  sort: "captured_desc" | "basis_change_desc" | "basis_desc" | "cash_bu_desc";
  include_non_canonical: boolean;
};

const DEFAULT_FILTERS: FilterState = {
  commodity: "Corn",
  location_id: "",
  company_id: "",
  region: "",
  captured_date: "",
  sort: "captured_desc",
  include_non_canonical: false,
};

export default function DashboardPage() {
  const headers = useMemo(() => buildApiHeaders(), []);
  const configError = useMemo(() => getApiConfigError({ requireOrg: true }), []);
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [facets, setFacets] = useState<FacetsResponse>({
    commodities: [],
    locations: [],
    source_names: [],
    company_names: [],
    region_names: [],
    company_rows: [],
    location_rows: [],
  });
  const [previewRows, setPreviewRows] = useState<PreviewRow[]>([]);
  const [monthlyPreview, setMonthlyPreview] = useState<MonthlyPreviewGroup[]>([]);
  const [movers, setMovers] = useState<TopMover[]>([]);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [sla, setSla] = useState<SlaSummary | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [loadingMeta, setLoadingMeta] = useState(false);
  const [error, setError] = useState("");
  const [selectedRowId, setSelectedRowId] = useState<string>("");
  const selectedRow = useMemo(
    () => previewRows.find((row) => row.id === selectedRowId) ?? previewRows[0] ?? null,
    [previewRows, selectedRowId]
  );
  const [watchlistName, setWatchlistName] = useState("");
  const [alertMetric, setAlertMetric] = useState<"cash_price_bu" | "basis">("cash_price_bu");
  const [alertOperator, setAlertOperator] = useState(">=");
  const [alertThreshold, setAlertThreshold] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [actionError, setActionError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const canManageAlerts = useMemo(() => isAdminRole(), []);
  const [watchlists, setWatchlists] = useState<WatchlistRow[]>([]);
  const [selectedWatchlistId, setSelectedWatchlistId] = useState("");
  const [watchlistPreviewRows, setWatchlistPreviewRows] = useState<PreviewRow[]>([]);
  const [watchlistPreviewLoading, setWatchlistPreviewLoading] = useState(false);
  const [watchlistPreviewError, setWatchlistPreviewError] = useState("");
  const canUseDebugView = canManageAlerts;

  useEffect(() => {
    if (configError) {
      setError(configError);
      return;
    }
    void loadMeta();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [configError]);

  useEffect(() => {
    if (configError) {
      return;
    }
    void loadMarketData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, configError]);

  useEffect(() => {
    if (!selectedRow) return;
    setWatchlistName(`${selectedRow.location} ${selectedRow.commodity_name}`.trim());
    const preferredThreshold = selectedRow.cash_price_bu ?? selectedRow.basis ?? null;
    setAlertThreshold(preferredThreshold == null ? "" : preferredThreshold.toFixed(2));
  }, [selectedRow]);

  async function loadMeta() {
    setLoadingMeta(true);
    setError((prev) => (prev.startsWith("Missing NEXT_PUBLIC_") ? prev : ""));
    try {
      const slaRes = await fetch(`${API_BASE}/api/ingestion/sla`, { cache: "no-store", headers });
      if (slaRes.ok) {
        setSla(await slaRes.json());
      } else {
        setError(`SLA unavailable: ${await readFailure(slaRes)}`);
      }

      const facetsRes = await fetch(`${API_BASE}/api/normalized-prices/facets`, { cache: "no-store", headers });
      if (!facetsRes.ok) {
        setError(`Facets unavailable: ${await readFailure(facetsRes)}`);
      } else {
        const rawFacets = await facetsRes.json();
        const sourceNames = normalizeFacetValues(rawFacets?.source_names);
        const companyNames = normalizeFacetValues(rawFacets?.company_names?.length ? rawFacets.company_names : sourceNames);
        const regionNames = normalizeFacetValues(rawFacets?.region_names);
        setFacets({
          commodities: normalizeFacetValues(rawFacets?.commodities),
          locations: normalizeFacetValues(rawFacets?.locations),
          source_names: sourceNames,
          company_names: companyNames,
          region_names: regionNames,
          company_rows: Array.isArray(rawFacets?.company_rows) ? rawFacets.company_rows : [],
          location_rows: Array.isArray(rawFacets?.location_rows) ? rawFacets.location_rows : [],
        });
      }

      await loadWatchlists(selectedWatchlistId || undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoadingMeta(false);
    }
  }

  async function loadMarketData() {
    setLoadingPreview(true);
    setError((prev) => (prev.startsWith("Missing NEXT_PUBLIC_") ? prev : ""));
    try {
      const query = buildMarketQuery(filters);
      const previewRes = await fetch(`${API_BASE}/api/normalized-prices/preview${query}&limit=120`, { cache: "no-store", headers });
      if (!previewRes.ok) throw new Error(await readFailure(previewRes));
      const preview = (await previewRes.json()).rows ?? [];
      setPreviewRows(sortPreviewRowsForDisplay(preview));

      const [groupedRes, moversRes, summaryRes] = await Promise.all([
        fetch(`${API_BASE}/api/normalized-prices/preview-grouped${query}&limit=120&rows_per_group=8`, { cache: "no-store", headers }),
        fetch(`${API_BASE}/api/normalized-prices/top-movers${query}&limit=8`, { cache: "no-store", headers }),
        fetch(`${API_BASE}/api/normalized-prices/summary${query}`, { cache: "no-store", headers }),
      ]);
      if (groupedRes.ok) {
        setMonthlyPreview((await groupedRes.json()).groups ?? []);
      } else {
        setError(`Monthly preview unavailable: ${await readFailure(groupedRes)}`);
      }
      if (moversRes.ok) {
        setMovers((await moversRes.json()).rows ?? []);
      } else {
        setError(`Top movers unavailable: ${await readFailure(moversRes)}`);
      }
      if (summaryRes.ok) {
        setSummary(await summaryRes.json());
      } else {
        setError(`Summary unavailable: ${await readFailure(summaryRes)}`);
      }
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

  async function runWatchlistPreview() {
    if (!selectedWatchlistId) return;
    await runWatchlistPreviewFor(selectedWatchlistId);
  }

  async function runWatchlistPreviewFor(watchlistId: string) {
    if (!watchlistId) return;
    setWatchlistPreviewLoading(true);
    setWatchlistPreviewError("");
    try {
      const res = await fetch(`${API_BASE}/api/watchlists/${watchlistId}/preview?limit=30`, {
        cache: "no-store",
        headers,
      });
      if (!res.ok) throw new Error(await readFailure(res));
      const payload = await res.json();
      const rows = Array.isArray(payload?.rows) ? payload.rows : [];
      setWatchlistPreviewRows(sortPreviewRowsForDisplay(rows));
    } catch (err) {
      setWatchlistPreviewError(err instanceof Error ? err.message : String(err));
    } finally {
      setWatchlistPreviewLoading(false);
    }
  }

  async function loadWatchlists(preferredId?: string) {
    const watchlistsRes = await fetch(`${API_BASE}/api/watchlists`, { cache: "no-store", headers });
    if (!watchlistsRes.ok) {
      setWatchlists([]);
      setSelectedWatchlistId("");
      return null;
    }
    const payload = await watchlistsRes.json();
    const rows: WatchlistRow[] = Array.isArray(payload?.rows) ? payload.rows : [];
    setWatchlists(rows);
    if (rows.length === 0) {
      setSelectedWatchlistId("");
      return null;
    }
    const resolvedId = preferredId && rows.some((row) => row.id === preferredId) ? preferredId : rows[0].id;
    setSelectedWatchlistId(resolvedId);
    return resolvedId;
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

        <div className="mt-3 grid gap-2 md:grid-cols-[1fr_1fr_1fr_1fr_160px_160px]">
          <select
            value={filters.location_id}
            onChange={(event) => setFilters((prev) => ({ ...prev, location_id: event.target.value }))}
            className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
          >
            <option value="">All locations</option>
            {(facets.location_rows || []).map((location) => (
              <option key={location.id} value={location.id}>
                {location.name}
              </option>
            ))}
          </select>
          <select
            value={filters.company_id}
            onChange={(event) => setFilters((prev) => ({ ...prev, company_id: event.target.value }))}
            className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
          >
            <option value="">All companies</option>
            {(facets.company_rows || []).map((source) => (
              <option key={source.id} value={source.id}>
                {source.name}
              </option>
            ))}
          </select>
          <select
            value={filters.region}
            onChange={(event) => setFilters((prev) => ({ ...prev, region: event.target.value }))}
            className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
          >
            <option value="">All regions</option>
            {facets.region_names.map((regionName) => (
              <option key={regionName} value={regionName}>
                {regionName}
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
        {canUseDebugView ? (
          <label className="mt-2 inline-flex items-center gap-2 text-xs text-black/65">
            <input
              type="checkbox"
              checked={filters.include_non_canonical}
              onChange={(event) =>
                setFilters((prev) => ({ ...prev, include_non_canonical: event.target.checked }))
              }
              className="h-4 w-4 rounded border border-black/20"
            />
            Show alternates (non-canonical rows)
          </label>
        ) : null}
      </section>

      <section className="mt-4 rounded-xl border border-black/10 bg-white/85 shadow-sm">
        <div className="flex items-center justify-between border-b border-black/10 px-4 py-3">
          <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-black/70">Live Price Preview</h2>
          {loadingPreview ? <span className="text-xs text-black/60">Refreshing...</span> : null}
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
                <th className="px-3 py-2 text-right">Futures Price</th>
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
                  <tr
                    key={row.id}
                    className={`cursor-pointer border-b border-black/5 ${selectedRow?.id === row.id ? "bg-amber-50/50" : ""}`}
                    onClick={() => setSelectedRowId(row.id)}
                  >
                    <td className="px-3 py-2">{row.location}</td>
                    <td className="px-3 py-2">{row.company_name || "-"}</td>
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
        <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-black/70">Top Bids by Delivery Month</h2>
        <p className="mt-1 text-xs text-black/55">Best cash bids after filters, grouped by delivery month.</p>
        <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {monthlyPreview.length === 0 ? (
            <p className="text-sm text-black/55">No monthly preview data available.</p>
          ) : (
            monthlyPreview.map((group) => (
              <article key={group.label} className="rounded-md border border-black/10 bg-white p-3">
                <h3 className="text-sm font-semibold">{group.label}</h3>
                <div className="mt-2 space-y-2">
                  {group.rows.map((row) => (
                    <div key={`${group.label}-${row.id}`} className="flex items-start justify-between gap-2 text-xs">
                      <div>
                        <p className="font-medium">{row.location}</p>
                        <p className="text-black/60">
                          {row.company_name || "Unknown buyer"} / {row.commodity_name}
                          {row.source_attribution ? ` · Source: ${row.source_attribution}` : ""}
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="font-semibold">{formatNumber(row.cash_price_bu)}</p>
                        <p className="text-black/60">basis {formatSigned(row.basis)}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </article>
            ))
          )}
        </div>
      </section>

      <section className="mt-4 rounded-xl border border-black/10 bg-white/85 p-4 shadow-sm">
        <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-black/70">Selected Bid Actions</h2>
        {!selectedRow ? (
          <p className="mt-2 text-sm text-black/55">Pick a row from Live Price Preview to create watchlists and alerts.</p>
        ) : (
          <div className="mt-3 grid gap-4 lg:grid-cols-2">
            <article className="rounded-md border border-black/10 bg-white p-3 text-sm">
              <p className="font-semibold">{selectedRow.location}</p>
              <p className="text-black/60">
                {selectedRow.company_name || "Unknown buyer"} / {selectedRow.commodity_name}
                {selectedRow.source_attribution ? ` · Source: ${selectedRow.source_attribution}` : ""}
              </p>
              <p className="mt-1 text-black/60">Delivery: {selectedRow.delivery_label || "-"}</p>
              <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                <p>Cash/Bu: <span className="font-semibold">{formatNumber(selectedRow.cash_price_bu)}</span></p>
                <p>Basis: <span className="font-semibold">{formatNumber(selectedRow.basis)}</span></p>
                <p>Futures: <span className="font-semibold">{selectedRow.futures_month || "-"}</span></p>
                <p>Futures Price: <span className="font-semibold">{formatNumber(selectedRow.futures_price)}</span></p>
              </div>
            </article>

            <div className="space-y-3">
              <div className="rounded-md border border-black/10 bg-white p-3">
                <h3 className="text-sm font-medium">Add to watchlist</h3>
                <div className="mt-2 flex gap-2">
                  <input
                    value={watchlistName}
                    onChange={(event) => setWatchlistName(event.target.value)}
                    placeholder="Watchlist name"
                    className="w-full rounded-md border border-black/15 px-3 py-2 text-sm"
                  />
                  <button
                    type="button"
                    disabled={submitting || !watchlistName.trim()}
                    onClick={async () => {
                      if (!selectedRow) return;
                      setSubmitting(true);
                      setActionError("");
                      setActionMessage("");
                      try {
                        const params = new URLSearchParams({
                          name: watchlistName.trim(),
                          location: selectedRow.location,
                          commodity_name: selectedRow.commodity_name,
                          source_name: selectedRow.company_name || "",
                        });
                        const res = await fetch(`${API_BASE}/api/watchlists?${params.toString()}`, {
                          method: "POST",
                          headers,
                        });
                        if (!res.ok) throw new Error(await readFailure(res));
                        const createdWatchlist = await res.json();
                        const createdId = String(createdWatchlist?.id || "");
                        const resolvedId = (await loadWatchlists(createdId || undefined)) || createdId;
                        if (resolvedId) {
                          await runWatchlistPreviewFor(resolvedId);
                        }
                        setActionMessage(`Watchlist created: ${watchlistName.trim()}`);
                      } catch (err) {
                        setActionError(err instanceof Error ? err.message : String(err));
                      } finally {
                        setSubmitting(false);
                      }
                    }}
                    className="rounded-md border border-black bg-black px-3 py-2 text-sm text-white disabled:opacity-60"
                  >
                    Save
                  </button>
                </div>
              </div>

              <div className="rounded-md border border-black/10 bg-white p-3">
                <h3 className="text-sm font-medium">Create alert rule from this bid</h3>
                {!canManageAlerts ? (
                  <p className="mt-2 text-xs text-black/55">Admin role required to create alert rules.</p>
                ) : (
                  <div className="mt-2 grid gap-2 md:grid-cols-[1fr_1fr_1fr_auto]">
                    <select
                      value={alertMetric}
                      onChange={(event) => {
                        const metric = event.target.value as "cash_price_bu" | "basis";
                        setAlertMetric(metric);
                        const base = metric === "cash_price_bu" ? selectedRow.cash_price_bu : selectedRow.basis;
                        setAlertThreshold(base == null ? "" : base.toFixed(2));
                      }}
                      className="rounded-md border border-black/15 px-2 py-2 text-sm"
                    >
                      <option value="cash_price_bu">Cash/Bu</option>
                      <option value="basis">Basis</option>
                    </select>
                    <select
                      value={alertOperator}
                      onChange={(event) => setAlertOperator(event.target.value)}
                      className="rounded-md border border-black/15 px-2 py-2 text-sm"
                    >
                      <option value=">=">&gt;=</option>
                      <option value=">">&gt;</option>
                      <option value="<=">&lt;=</option>
                      <option value="<">&lt;</option>
                    </select>
                    <input
                      type="number"
                      step="0.01"
                      value={alertThreshold}
                      onChange={(event) => setAlertThreshold(event.target.value)}
                      placeholder="Threshold"
                      className="rounded-md border border-black/15 px-2 py-2 text-sm"
                    />
                    <button
                      type="button"
                      disabled={submitting || !alertThreshold.trim()}
                      onClick={async () => {
                        if (!selectedRow) return;
                        setSubmitting(true);
                        setActionError("");
                        setActionMessage("");
                        try {
                          const params = new URLSearchParams({
                            rule_type: alertMetric,
                            threshold_value: Number(alertThreshold).toString(),
                            comparison_operator: alertOperator,
                            location: selectedRow.location,
                          });
                          const res = await fetch(`${API_BASE}/api/alerts/rules?${params.toString()}`, {
                            method: "POST",
                            headers,
                          });
                          if (!res.ok) throw new Error(await readFailure(res));
                          setActionMessage(`Alert rule created: ${alertMetric} ${alertOperator} ${alertThreshold}`);
                        } catch (err) {
                          setActionError(err instanceof Error ? err.message : String(err));
                        } finally {
                          setSubmitting(false);
                        }
                      }}
                      className="rounded-md border border-black bg-black px-3 py-2 text-sm text-white disabled:opacity-60"
                    >
                      Create
                    </button>
                  </div>
                )}
              </div>

              {actionMessage ? <p className="text-xs text-emerald-700">{actionMessage}</p> : null}
              {actionError ? <p className="text-xs text-rose-700">{actionError}</p> : null}
            </div>
          </div>
        )}
      </section>

      <section className="mt-4 rounded-xl border border-black/10 bg-white/85 p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-black/70">Watchlist Run-Now Preview</h2>
            <p className="mt-1 text-xs text-black/55">Run a saved watchlist and preview matching current bids.</p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={selectedWatchlistId}
              onChange={(event) => setSelectedWatchlistId(event.target.value)}
              className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
            >
              <option value="">Select watchlist</option>
              {watchlists.map((watchlist) => (
                <option key={watchlist.id} value={watchlist.id}>
                  {watchlist.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={runWatchlistPreview}
              disabled={watchlistPreviewLoading || !selectedWatchlistId}
              className="rounded-md border border-black bg-black px-3 py-2 text-sm text-white disabled:opacity-60"
            >
              {watchlistPreviewLoading ? "Running..." : "Run now"}
            </button>
          </div>
        </div>

        {watchlistPreviewError ? <p className="mt-2 text-sm text-rose-700">{watchlistPreviewError}</p> : null}

        <div className="mt-3 max-h-[320px] overflow-auto rounded-md border border-black/10 bg-white">
          <table className="min-w-full text-left text-sm">
            <thead className="sticky top-0 bg-white">
              <tr className="border-b border-black/10 text-xs uppercase tracking-wide text-black/55">
                <th className="px-3 py-2">Location</th>
                <th className="px-3 py-2">Company</th>
                <th className="px-3 py-2">Commodity</th>
                <th className="px-3 py-2">Delivery</th>
                <th className="px-3 py-2 text-right">Cash/Bu</th>
                <th className="px-3 py-2 text-right">Basis</th>
              </tr>
            </thead>
            <tbody>
              {watchlistPreviewRows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-center text-sm text-black/55">
                    {selectedWatchlistId ? "No rows for selected watchlist." : "Select a watchlist and click Run now."}
                  </td>
                </tr>
              ) : (
                watchlistPreviewRows.map((row) => (
                  <tr key={`watchlist-preview-${row.id}`} className="border-b border-black/5">
                    <td className="px-3 py-2">{row.location}</td>
                    <td className="px-3 py-2">{row.company_name || "-"}</td>
                    <td className="px-3 py-2">{row.commodity_name}</td>
                    <td className="px-3 py-2">{row.delivery_label || "-"}</td>
                    <td className="px-3 py-2 text-right">{formatNumber(row.cash_price_bu)}</td>
                    <td className="px-3 py-2 text-right">{formatNumber(row.basis)}</td>
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
                <p className="text-xs text-black/60">
                  {mover.company_name || "Unknown buyer"} / {mover.commodity_name}
                  {mover.source_attribution ? ` · Source: ${mover.source_attribution}` : ""}
                </p>
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

function normalizeFacetValues(values: unknown): string[] {
  if (!Array.isArray(values)) {
    return [];
  }
  const unique = new Map<string, string>();
  for (const raw of values) {
    if (typeof raw !== "string") {
      continue;
    }
    const cleaned = raw.trim().replace(/\s+/g, " ");
    if (!cleaned || cleaned.toLowerCase() === "nan") {
      continue;
    }
    const key = cleaned.toLowerCase();
    if (!unique.has(key)) {
      unique.set(key, cleaned);
    }
  }
  return Array.from(unique.values()).sort((a, b) => a.localeCompare(b));
}

function sortPreviewRowsForDisplay(rows: PreviewRow[]): PreviewRow[] {
  return [...rows].sort((a, b) => {
    const locationCompare = compareString(a.location, b.location);
    if (locationCompare !== 0) return locationCompare;
    const companyCompare = compareString(a.company_name ?? "", b.company_name ?? "");
    if (companyCompare !== 0) return companyCompare;
    const commodityCompare = compareString(a.commodity_name, b.commodity_name);
    if (commodityCompare !== 0) return commodityCompare;
    const deliveryCompare = compareMonthLabel(a.delivery_label, b.delivery_label);
    if (deliveryCompare !== 0) return deliveryCompare;
    const futuresCompare = compareMonthLabel(a.futures_month, b.futures_month);
    if (futuresCompare !== 0) return futuresCompare;
    return compareString(a.id, b.id);
  });
}

function compareString(a: string, b: string): number {
  return a.localeCompare(b, undefined, { sensitivity: "base" });
}

function compareMonthLabel(a: string | null, b: string | null): number {
  const aKey = monthSortKey(a);
  const bKey = monthSortKey(b);
  if (aKey == null && bKey == null) return 0;
  if (aKey == null) return 1;
  if (bKey == null) return -1;
  return aKey - bKey;
}

function monthSortKey(value: string | null): number | null {
  if (!value) return null;
  const label = value.trim();
  if (!label) return null;
  const monthMap: Record<string, number> = {
    jan: 1,
    january: 1,
    feb: 2,
    february: 2,
    mar: 3,
    march: 3,
    apr: 4,
    april: 4,
    may: 5,
    jun: 6,
    june: 6,
    jul: 7,
    july: 7,
    aug: 8,
    august: 8,
    sep: 9,
    sept: 9,
    september: 9,
    oct: 10,
    october: 10,
    nov: 11,
    november: 11,
    dec: 12,
    december: 12,
  };
  const normalized = label.toLowerCase();

  // Handle season labels often used in bids (example: "Harvest 26 Farm").
  const harvestMatch = normalized.match(/\bharvest\b[^0-9]*(\d{2,4})?/);
  if (harvestMatch) {
    const year = parseYearToken(harvestMatch[1]);
    if (year != null) return year * 12 + 10; // Oct as harvest proxy month
  }

  // Handle futures contract codes (e.g. ZCN26, ZSX27).
  const futuresCodeMatch = normalized.match(/\b([fghjkmnquvxz])(?:c|s|w)?(\d{1,2})\b/);
  if (futuresCodeMatch) {
    const codeMonthMap: Record<string, number> = {
      f: 1,
      g: 2,
      h: 3,
      j: 4,
      k: 5,
      m: 6,
      n: 7,
      q: 8,
      u: 9,
      v: 10,
      x: 11,
      z: 12,
    };
    const month = codeMonthMap[futuresCodeMatch[1]];
    const year = parseYearToken(futuresCodeMatch[2]);
    if (month && year != null) return year * 12 + month;
  }

  const match = normalized.match(
    /\b(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\b[^0-9]*(\d{2,4})?/
  );
  if (!match) return null;
  const month = monthMap[match[1]];
  if (!month) return null;
  const year = parseYearToken(match[2]) ?? 0;
  return year * 12 + month;
}

function parseYearToken(token?: string): number | null {
  if (!token) return null;
  const rawYear = Number.parseInt(token, 10);
  if (Number.isNaN(rawYear)) return null;
  if (rawYear < 100) return 2000 + rawYear;
  return rawYear;
}

function buildMarketQuery(filters: FilterState) {
  const params = new URLSearchParams();
  if (filters.commodity) params.set("commodity", filters.commodity);
  if (filters.location_id) params.set("location_id", filters.location_id);
  if (filters.company_id) params.set("company_id", filters.company_id);
  if (filters.region) params.set("region", filters.region);
  if (filters.captured_date) params.set("captured_date", filters.captured_date);
  if (filters.sort) params.set("sort", filters.sort);
  if (filters.include_non_canonical) params.set("include_non_canonical", "true");
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
