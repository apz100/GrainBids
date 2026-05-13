"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { API_BASE, buildApiHeaders } from "@/lib/api";

type WatchlistRow = {
  id: string;
  name: string;
  is_active: boolean;
  updated_at: string | null;
  filters_json?: Record<string, string>;
};

type PreviewRow = {
  id: string;
  captured_at: string | null;
  location: string | null;
  source_name: string | null;
  commodity_name: string | null;
  delivery_label: string | null;
  futures_month: string | null;
  basis: number | null;
  cash_price_bu: number | null;
};

const headers = buildApiHeaders();

function formatNumber(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return "-";
  return value.toFixed(2);
}

function formatDate(value: string | null | undefined) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "-";
  return parsed.toLocaleString();
}

export default function WatchlistsPage() {
  const [watchlists, setWatchlists] = useState<WatchlistRow[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [previewRows, setPreviewRows] = useState<PreviewRow[]>([]);
  const [previewLabel, setPreviewLabel] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadWatchlists() {
      try {
        const res = await fetch(`${API_BASE}/api/watchlists`, {
          cache: "no-store",
          headers,
        });
        if (!res.ok) throw new Error(`Failed to fetch watchlists (${res.status})`);
        const json = await res.json();
        const rows: WatchlistRow[] = Array.isArray(json.rows) ? json.rows : [];
        if (cancelled) return;
        setWatchlists(rows);
        if (rows.length > 0) setSelectedId(rows[0].id);
      } catch (fetchErr) {
        if (!cancelled) setError(fetchErr instanceof Error ? fetchErr.message : "Failed to fetch watchlists");
      }
    }
    loadWatchlists();
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedWatchlist = useMemo(
    () => watchlists.find((row) => row.id === selectedId) ?? null,
    [watchlists, selectedId],
  );

  async function runPreview() {
    if (!selectedId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/watchlists/${selectedId}/preview?limit=30`, {
        cache: "no-store",
        headers,
      });
      if (!res.ok) throw new Error(`Preview failed (${res.status})`);
      const json = await res.json();
      const rows: PreviewRow[] = Array.isArray(json.rows) ? json.rows : [];
      setPreviewRows(rows);
      setPreviewLabel(json.watchlist?.name || "Watchlist");
    } catch (previewErr) {
      setError(previewErr instanceof Error ? previewErr.message : "Preview request failed");
      setPreviewRows([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <p className="text-xs uppercase tracking-[0.16em] text-black/50">GrainBids / Watchlists</p>
      <h1 className="mt-1 font-[family-name:var(--font-serif)] text-4xl leading-tight">Watchlists</h1>
      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Run-now preview</h2>
        <p className="mt-2 text-sm text-black/65">Run one saved watchlist and preview matching bids instantly.</p>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <select
            value={selectedId}
            onChange={(event) => setSelectedId(event.target.value)}
            className="min-w-[260px] rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
          >
            {watchlists.length === 0 ? (
              <option value="">No watchlists</option>
            ) : (
              watchlists.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name}
                </option>
              ))
            )}
          </select>
          <button
            type="button"
            onClick={runPreview}
            disabled={!selectedId || loading}
            className="rounded-md bg-black px-4 py-2 text-sm text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? "Running..." : "Run now preview"}
          </button>
          <Link href="/bids" className="rounded-md border border-black/20 bg-white px-3 py-2 text-sm hover:border-black/40">
            Open market
          </Link>
        </div>
        {selectedWatchlist?.filters_json ? (
          <p className="mt-3 text-xs text-black/55">
            Filters: {Object.entries(selectedWatchlist.filters_json).map(([k, v]) => `${k}=${v}`).join(", ") || "none"}
          </p>
        ) : null}
        {error ? <p className="mt-3 text-sm text-red-600">{error}</p> : null}
        <div className="mt-5 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-black/10 text-xs uppercase tracking-wide text-black/50">
                <th className="px-2 py-2">Location</th>
                <th className="px-2 py-2">Company</th>
                <th className="px-2 py-2">Commodity</th>
                <th className="px-2 py-2">Delivery</th>
                <th className="px-2 py-2">Futures</th>
                <th className="px-2 py-2 text-right">Basis</th>
                <th className="px-2 py-2 text-right">Cash/Bu</th>
                <th className="px-2 py-2">Captured</th>
              </tr>
            </thead>
            <tbody>
              {previewRows.length === 0 ? (
                <tr>
                  <td className="px-2 py-4 text-black/55" colSpan={8}>
                    {previewLabel ? `No rows matched "${previewLabel}".` : "Run preview to see rows."}
                  </td>
                </tr>
              ) : (
                previewRows.map((row) => (
                  <tr key={row.id} className="border-b border-black/5">
                    <td className="px-2 py-2">{row.location || "-"}</td>
                    <td className="px-2 py-2">{row.source_name || "-"}</td>
                    <td className="px-2 py-2">{row.commodity_name || "-"}</td>
                    <td className="px-2 py-2">{row.delivery_label || "-"}</td>
                    <td className="px-2 py-2">{row.futures_month || "-"}</td>
                    <td className="px-2 py-2 text-right">{formatNumber(row.basis)}</td>
                    <td className="px-2 py-2 text-right">{formatNumber(row.cash_price_bu)}</td>
                    <td className="px-2 py-2">{formatDate(row.captured_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
