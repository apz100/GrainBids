"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { API_BASE, buildApiHeaders } from "@/lib/api";
import {
  formatNotificationTimestamp,
  formatNotificationValue,
  notificationStatusClass,
} from "@/lib/alerts-history.mjs";

type WatchlistRow = {
  id: string;
  name: string;
  is_active: boolean;
  updated_at: string | null;
  filters_json?: Record<string, string>;
  automation?: WatchlistAutomationSummary | null;
};

type SavedSearchRow = {
  id: string;
  name: string;
  is_active: boolean;
  filters_json: Record<string, string>;
  delivery_months: string[];
  target_cash_price_bu: number | null;
  target_basis: number | null;
  updated_at: string | null;
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

type NotificationLogRow = {
  id: string;
  alert_id: string | null;
  channel: string;
  recipient: string | null;
  status: string;
  provider_message_id: string | null;
  error_message: string | null;
  created_at: string | null;
  payload_json: Record<string, unknown>;
};

type WatchlistAutomationSummary = {
  id: string | null;
  watchlist_id: string;
  is_enabled: boolean;
  digest_enabled: boolean;
  alert_promotion_enabled: boolean;
  linked_saved_search_id: string | null;
  linked_alert_rule_id: string | null;
  last_run_at: string | null;
  last_digest_row_count: number | null;
  last_error_message: string | null;
  created_at: string | null;
  updated_at: string | null;
};

type WatchlistAutomationDetails = {
  watchlist: {
    id: string;
    org_id: string;
    name: string;
    filters_json: Record<string, string>;
    is_active: boolean;
  };
  automation: WatchlistAutomationSummary;
  saved_search: {
    id: string;
    name: string;
    filters_json: Record<string, string>;
    delivery_months: string[];
    is_active: boolean;
  } | null;
  alert_rule: {
    id: string;
    rule_type: string;
    comparison_operator: string;
    threshold_value: number;
    saved_search_id: string | null;
    location: string | null;
    delivery_months: string[];
    is_active: boolean;
  } | null;
  recent_notifications: NotificationLogRow[];
  preview_rows: PreviewRow[];
};

type FacetsResponse = {
  commodities: string[];
  company_names: string[];
  locations: string[];
};

type SavedSearchForm = {
  name: string;
  commodity_name: string;
  location: string;
  source_name: string;
  delivery_months: string;
  target_cash_price_bu: string;
  target_basis: string;
  is_active: boolean;
};

const headers = buildApiHeaders();

const EMPTY_FORM: SavedSearchForm = {
  name: "",
  commodity_name: "",
  location: "",
  source_name: "",
  delivery_months: "",
  target_cash_price_bu: "",
  target_basis: "",
  is_active: true,
};

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
  const [selectedWatchlistId, setSelectedWatchlistId] = useState<string>("");
  const [watchlistPreviewRows, setWatchlistPreviewRows] = useState<PreviewRow[]>([]);
  const [watchlistPreviewLabel, setWatchlistPreviewLabel] = useState<string>("");
  const [watchlistLoading, setWatchlistLoading] = useState(false);
  const [watchlistError, setWatchlistError] = useState<string | null>(null);
  const [watchlistAutomation, setWatchlistAutomation] = useState<WatchlistAutomationDetails | null>(null);
  const [watchlistAutomationLoading, setWatchlistAutomationLoading] = useState(false);
  const [watchlistAutomationError, setWatchlistAutomationError] = useState<string | null>(null);
  const [watchlistAutomationAction, setWatchlistAutomationAction] = useState<string>("");

  const [savedSearches, setSavedSearches] = useState<SavedSearchRow[]>([]);
  const [selectedSavedSearchId, setSelectedSavedSearchId] = useState<string>("");
  const [savedPreviewRows, setSavedPreviewRows] = useState<PreviewRow[]>([]);
  const [savedPreviewLabel, setSavedPreviewLabel] = useState<string>("");
  const [savedLoading, setSavedLoading] = useState(false);
  const [savedError, setSavedError] = useState<string | null>(null);
  const [savedAction, setSavedAction] = useState<string>("");
  const [savedForm, setSavedForm] = useState<SavedSearchForm>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [facets, setFacets] = useState<FacetsResponse>({
    commodities: [],
    company_names: [],
    locations: [],
  });

  useEffect(() => {
    let cancelled = false;
    async function init() {
      try {
        const [watchlistRes, savedRes, facetsRes] = await Promise.all([
          fetch(`${API_BASE}/api/watchlists`, { cache: "no-store", headers }),
          fetch(`${API_BASE}/api/saved-searches`, { cache: "no-store", headers }),
          fetch(`${API_BASE}/api/normalized-prices/facets`, { cache: "no-store", headers }),
        ]);
        if (cancelled) return;

        if (watchlistRes.ok) {
          const json = await watchlistRes.json();
          const rows: WatchlistRow[] = Array.isArray(json.rows) ? json.rows : [];
          setWatchlists(rows);
          if (rows.length > 0) setSelectedWatchlistId(rows[0].id);
        }
        if (savedRes.ok) {
          const json = await savedRes.json();
          const rows: SavedSearchRow[] = Array.isArray(json.rows) ? json.rows : [];
          setSavedSearches(rows);
          if (rows.length > 0) setSelectedSavedSearchId(rows[0].id);
        }
        if (facetsRes.ok) {
          const json = await facetsRes.json();
          setFacets({
            commodities: normalizeFacetValues(json?.commodities),
            company_names: normalizeFacetValues(json?.company_names),
            locations: normalizeFacetValues(json?.locations),
          });
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : "Failed to initialize watchlists page";
          setWatchlistError(message);
          setSavedError(message);
        }
      }
    }
    void init();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedSavedSearchId) {
      setSavedForm(EMPTY_FORM);
      return;
    }
    const row = savedSearches.find((item) => item.id === selectedSavedSearchId);
    if (!row) return;
    setSavedForm({
      name: row.name || "",
      commodity_name: row.filters_json?.commodity_name || "",
      location: row.filters_json?.location || "",
      source_name: row.filters_json?.source_name || "",
      delivery_months: (row.delivery_months || []).join(", "),
      target_cash_price_bu: row.target_cash_price_bu == null ? "" : row.target_cash_price_bu.toString(),
      target_basis: row.target_basis == null ? "" : row.target_basis.toString(),
      is_active: row.is_active,
    });
  }, [selectedSavedSearchId, savedSearches]);

  useEffect(() => {
    if (!selectedWatchlistId) {
      setWatchlistAutomation(null);
      return;
    }
    void refreshWatchlistAutomation(selectedWatchlistId);
  }, [selectedWatchlistId]);

  const selectedWatchlist = useMemo(
    () => watchlists.find((row) => row.id === selectedWatchlistId) ?? null,
    [watchlists, selectedWatchlistId]
  );

  const selectedWatchlistAutomation = useMemo(
    () => (watchlistAutomation?.watchlist.id === selectedWatchlistId ? watchlistAutomation : null),
    [selectedWatchlistId, watchlistAutomation]
  );

  async function refreshSavedSearches(preferredId?: string) {
    const res = await fetch(`${API_BASE}/api/saved-searches`, { cache: "no-store", headers });
    if (!res.ok) throw new Error(`Failed to fetch saved searches (${res.status})`);
    const json = await res.json();
    const rows: SavedSearchRow[] = Array.isArray(json.rows) ? json.rows : [];
    setSavedSearches(rows);
    if (rows.length === 0) {
      setSelectedSavedSearchId("");
      return "";
    }
    const resolved = preferredId && rows.some((row) => row.id === preferredId) ? preferredId : rows[0].id;
    setSelectedSavedSearchId(resolved);
    return resolved;
  }

  async function runWatchlistPreview() {
    if (!selectedWatchlistId) return;
    setWatchlistLoading(true);
    setWatchlistError(null);
    try {
      const res = await fetch(`${API_BASE}/api/watchlists/${selectedWatchlistId}/preview?limit=30`, {
        cache: "no-store",
        headers,
      });
      if (!res.ok) throw new Error(`Preview failed (${res.status})`);
      const json = await res.json();
      const rows: PreviewRow[] = Array.isArray(json.rows) ? json.rows : [];
      setWatchlistPreviewRows(rows);
      setWatchlistPreviewLabel(json.watchlist?.name || "Watchlist");
    } catch (previewErr) {
      setWatchlistError(previewErr instanceof Error ? previewErr.message : "Preview request failed");
      setWatchlistPreviewRows([]);
    } finally {
      setWatchlistLoading(false);
    }
  }

  async function refreshWatchlistAutomation(id = selectedWatchlistId) {
    if (!id) return;
    setWatchlistAutomationLoading(true);
    setWatchlistAutomationError(null);
    try {
      const res = await fetch(`${API_BASE}/api/watchlists/${id}/automation`, {
        cache: "no-store",
        headers,
      });
      if (!res.ok) throw new Error(`Automation lookup failed (${res.status})`);
      const json = (await res.json()) as WatchlistAutomationDetails;
      setWatchlistAutomation(json);
    } catch (err) {
      setWatchlistAutomationError(err instanceof Error ? err.message : "Automation lookup failed");
      setWatchlistAutomation(null);
    } finally {
      setWatchlistAutomationLoading(false);
    }
  }

  async function updateWatchlistAutomation(overrides?: Partial<Record<"is_enabled" | "digest_enabled" | "alert_promotion_enabled", boolean>>) {
    if (!selectedWatchlistId) return;
    setWatchlistAutomationAction("");
    setWatchlistAutomationError(null);
    try {
      const current = selectedWatchlistAutomation?.automation;
      const params = new URLSearchParams();
      params.set("is_enabled", String(overrides?.is_enabled ?? current?.is_enabled ?? false));
      params.set("digest_enabled", String(overrides?.digest_enabled ?? current?.digest_enabled ?? false));
      params.set(
        "alert_promotion_enabled",
        String(overrides?.alert_promotion_enabled ?? current?.alert_promotion_enabled ?? false)
      );
      const res = await fetch(`${API_BASE}/api/watchlists/${selectedWatchlistId}/automation?${params.toString()}`, {
        method: "PUT",
        headers,
      });
      if (!res.ok) throw new Error(`Automation update failed (${res.status})`);
      await refreshWatchlistAutomation(selectedWatchlistId);
      setWatchlistAutomationAction("Watchlist automation updated.");
    } catch (err) {
      setWatchlistAutomationError(err instanceof Error ? err.message : "Automation update failed");
    }
  }

  async function runWatchlistAutomation() {
    if (!selectedWatchlistId) return;
    setWatchlistAutomationAction("");
    setWatchlistAutomationError(null);
    try {
      const res = await fetch(`${API_BASE}/api/watchlists/${selectedWatchlistId}/automation/run?limit=50`, {
        method: "POST",
        headers,
      });
      if (!res.ok) throw new Error(`Automation run failed (${res.status})`);
      await refreshWatchlistAutomation(selectedWatchlistId);
      setWatchlistAutomationAction("Digest run completed.");
    } catch (err) {
      setWatchlistAutomationError(err instanceof Error ? err.message : "Automation run failed");
    }
  }

  async function runSavedSearchPreview(id = selectedSavedSearchId) {
    if (!id) return;
    setSavedLoading(true);
    setSavedError(null);
    try {
      const res = await fetch(`${API_BASE}/api/saved-searches/${id}/preview?limit=50`, {
        cache: "no-store",
        headers,
      });
      if (!res.ok) throw new Error(`Preview failed (${res.status})`);
      const json = await res.json();
      const rows: PreviewRow[] = Array.isArray(json.rows) ? json.rows : [];
      setSavedPreviewRows(rows);
      setSavedPreviewLabel(json.saved_search?.name || "Saved search");
    } catch (err) {
      setSavedError(err instanceof Error ? err.message : "Saved search preview failed");
      setSavedPreviewRows([]);
    } finally {
      setSavedLoading(false);
    }
  }

  async function createSavedSearch() {
    if (!savedForm.name.trim()) {
      setSavedError("Saved search name is required.");
      return;
    }
    setSubmitting(true);
    setSavedError(null);
    setSavedAction("");
    try {
      const params = new URLSearchParams();
      params.set("name", savedForm.name.trim());
      setOptionalFilterParams(params, savedForm);
      const res = await fetch(`${API_BASE}/api/saved-searches?${params.toString()}`, {
        method: "POST",
        headers,
      });
      if (!res.ok) throw new Error(`Create failed (${res.status})`);
      const json = await res.json();
      const newId = String(json.id || "");
      const resolvedId = await refreshSavedSearches(newId || undefined);
      if (resolvedId) await runSavedSearchPreview(resolvedId);
      setSavedAction(`Saved search created: ${savedForm.name.trim()}`);
    } catch (err) {
      setSavedError(err instanceof Error ? err.message : "Create failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function updateSavedSearch() {
    if (!selectedSavedSearchId) return;
    setSubmitting(true);
    setSavedError(null);
    setSavedAction("");
    try {
      const params = new URLSearchParams();
      if (savedForm.name.trim()) params.set("name", savedForm.name.trim());
      setOptionalFilterParams(params, savedForm);
      params.set("is_active", savedForm.is_active ? "true" : "false");
      const res = await fetch(`${API_BASE}/api/saved-searches/${selectedSavedSearchId}?${params.toString()}`, {
        method: "PATCH",
        headers,
      });
      if (!res.ok) throw new Error(`Update failed (${res.status})`);
      const resolvedId = await refreshSavedSearches(selectedSavedSearchId);
      if (resolvedId) await runSavedSearchPreview(resolvedId);
      setSavedAction("Saved search updated.");
    } catch (err) {
      setSavedError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function deleteSavedSearch() {
    if (!selectedSavedSearchId) return;
    setSubmitting(true);
    setSavedError(null);
    setSavedAction("");
    try {
      const res = await fetch(`${API_BASE}/api/saved-searches/${selectedSavedSearchId}`, {
        method: "DELETE",
        headers,
      });
      if (!res.ok) throw new Error(`Delete failed (${res.status})`);
      setSavedPreviewRows([]);
      setSavedPreviewLabel("");
      await refreshSavedSearches();
      setSavedAction("Saved search deleted.");
    } catch (err) {
      setSavedError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setSubmitting(false);
    }
  }

  function clearSavedSearchForm() {
    setSelectedSavedSearchId("");
    setSavedForm(EMPTY_FORM);
    setSavedPreviewRows([]);
    setSavedPreviewLabel("");
    setSavedError(null);
    setSavedAction("");
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <p className="text-xs uppercase tracking-[0.16em] text-black/50">GrainBids / Watchlists</p>
      <h1 className="mt-1 font-[family-name:var(--font-serif)] text-4xl leading-tight">Watchlists & Saved Searches</h1>

      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Watchlist run-now preview</h2>
        <p className="mt-2 text-sm text-black/65">Run one saved watchlist and preview matching bids instantly.</p>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <select
            value={selectedWatchlistId}
            onChange={(event) => setSelectedWatchlistId(event.target.value)}
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
            onClick={runWatchlistPreview}
            disabled={!selectedWatchlistId || watchlistLoading}
            className="rounded-md bg-black px-4 py-2 text-sm text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            {watchlistLoading ? "Running..." : "Run now preview"}
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
        {watchlistError ? <p className="mt-3 text-sm text-red-600">{watchlistError}</p> : null}
        <PreviewTable rows={watchlistPreviewRows} emptyMessage={watchlistPreviewLabel ? `No rows matched "${watchlistPreviewLabel}".` : "Run preview to see rows."} />

        <div className="mt-5 rounded-md border border-black/10 bg-white/80 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold">Automation</h3>
              <p className="text-sm text-black/60">Daily digest and alert promotion for this watchlist.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void refreshWatchlistAutomation()}
                disabled={!selectedWatchlistId || watchlistAutomationLoading}
                className="rounded-md border border-black/20 bg-white px-3 py-2 text-xs disabled:opacity-60"
              >
                {watchlistAutomationLoading ? "Loading..." : "Refresh automation"}
              </button>
              <button
                type="button"
                onClick={() => void runWatchlistAutomation()}
                disabled={!selectedWatchlistId || watchlistAutomationLoading}
                className="rounded-md border border-black bg-black px-3 py-2 text-xs text-white disabled:opacity-60"
              >
                Run digest now
              </button>
            </div>
          </div>

          {watchlistAutomationError ? <p className="mt-3 text-sm text-rose-700">{watchlistAutomationError}</p> : null}
          {watchlistAutomationAction ? <p className="mt-3 text-sm text-emerald-700">{watchlistAutomationAction}</p> : null}

          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <AutomationStat label="Enabled" value={booleanLabel(selectedWatchlistAutomation?.automation.is_enabled)} />
            <AutomationStat label="Digest" value={booleanLabel(selectedWatchlistAutomation?.automation.digest_enabled)} />
            <AutomationStat
              label="Alert promotion"
              value={booleanLabel(selectedWatchlistAutomation?.automation.alert_promotion_enabled)}
            />
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <AutomationDetail
              label="Linked saved search"
              value={selectedWatchlistAutomation?.saved_search?.name || "None"}
            />
            <AutomationDetail label="Linked alert rule" value={selectedWatchlistAutomation?.alert_rule?.rule_type || "None"} />
            <AutomationDetail
              label="Last digest"
              value={
                selectedWatchlistAutomation?.automation.last_run_at
                  ? `${formatNotificationTimestamp(selectedWatchlistAutomation.automation.last_run_at)} (${selectedWatchlistAutomation.automation.last_digest_row_count ?? 0} rows)`
                  : "Never"
              }
            />
            <AutomationDetail
              label="Last error"
              value={selectedWatchlistAutomation?.automation.last_error_message || "None"}
            />
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void updateWatchlistAutomation({ is_enabled: true })}
              className="rounded-md border border-black/20 bg-white px-3 py-2 text-xs"
            >
              Enable
            </button>
            <button
              type="button"
              onClick={() => void updateWatchlistAutomation({ is_enabled: false })}
              className="rounded-md border border-black/20 bg-white px-3 py-2 text-xs"
            >
              Disable
            </button>
          </div>

          <div className="mt-5 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-black/10 text-xs uppercase tracking-wide text-black/50">
                  <th className="px-2 py-2">When</th>
                  <th className="px-2 py-2">Status</th>
                  <th className="px-2 py-2">Channel</th>
                  <th className="px-2 py-2">Recipient</th>
                  <th className="px-2 py-2">Error</th>
                </tr>
              </thead>
              <tbody>
                {(selectedWatchlistAutomation?.recent_notifications || []).length === 0 ? (
                  <tr>
                    <td className="px-2 py-4 text-black/55" colSpan={5}>
                      No digest history yet.
                    </td>
                  </tr>
                ) : (
                  (selectedWatchlistAutomation?.recent_notifications || []).map((row) => (
                    <tr key={row.id} className="border-b border-black/5">
                      <td className="px-2 py-2">{formatNotificationTimestamp(row.created_at)}</td>
                      <td className="px-2 py-2">
                        <span className={`inline-flex rounded-full border px-2 py-1 text-xs ${notificationStatusClass(row.status)}`}>
                          {formatNotificationValue(row.status)}
                        </span>
                      </td>
                      <td className="px-2 py-2">{formatNotificationValue(row.channel)}</td>
                      <td className="px-2 py-2">{formatNotificationValue(row.recipient)}</td>
                      <td className="px-2 py-2 text-xs text-black/70">{formatNotificationValue(row.error_message)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="mt-6 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Saved searches</h2>
        <p className="mt-2 text-sm text-black/65">
          Save reusable market filters with month scopes and target values for alerts.
        </p>

        <div className="mt-4 grid gap-3 md:grid-cols-[1fr_auto_auto_auto]">
          <select
            value={selectedSavedSearchId}
            onChange={(event) => setSelectedSavedSearchId(event.target.value)}
            className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
          >
            <option value="">New saved search</option>
            {savedSearches.map((row) => (
              <option key={row.id} value={row.id}>
                {row.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => void runSavedSearchPreview()}
            disabled={!selectedSavedSearchId || savedLoading}
            className="rounded-md border border-black bg-black px-3 py-2 text-sm text-white disabled:opacity-60"
          >
            {savedLoading ? "Running..." : "Run preview"}
          </button>
          <button
            type="button"
            onClick={() => void updateSavedSearch()}
            disabled={!selectedSavedSearchId || submitting}
            className="rounded-md border border-black/20 bg-white px-3 py-2 text-sm disabled:opacity-60"
          >
            Update
          </button>
          <button
            type="button"
            onClick={() => void deleteSavedSearch()}
            disabled={!selectedSavedSearchId || submitting}
            className="rounded-md border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-700 disabled:opacity-60"
          >
            Delete
          </button>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <label className="text-sm">
            <span className="mb-1 block text-black/70">Name</span>
            <input
              value={savedForm.name}
              onChange={(event) => setSavedForm((prev) => ({ ...prev, name: event.target.value }))}
              className="w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
              placeholder="Hensall Corn Nearby"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-black/70">Commodity</span>
            <select
              value={savedForm.commodity_name}
              onChange={(event) => setSavedForm((prev) => ({ ...prev, commodity_name: event.target.value }))}
              className="w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
            >
              <option value="">Any commodity</option>
              {facets.commodities.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-black/70">Location</span>
            <select
              value={savedForm.location}
              onChange={(event) => setSavedForm((prev) => ({ ...prev, location: event.target.value }))}
              className="w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
            >
              <option value="">Any location</option>
              {facets.locations.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-black/70">Company</span>
            <select
              value={savedForm.source_name}
              onChange={(event) => setSavedForm((prev) => ({ ...prev, source_name: event.target.value }))}
              className="w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
            >
              <option value="">Any company</option>
              {facets.company_names.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-black/70">Delivery month scope (comma-separated)</span>
            <input
              value={savedForm.delivery_months}
              onChange={(event) => setSavedForm((prev) => ({ ...prev, delivery_months: event.target.value }))}
              className="w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
              placeholder="May 2026, Jul 2026"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-black/70">Target Cash/Bu (optional)</span>
            <input
              type="number"
              step="0.01"
              value={savedForm.target_cash_price_bu}
              onChange={(event) => setSavedForm((prev) => ({ ...prev, target_cash_price_bu: event.target.value }))}
              className="w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-black/70">Target Basis (optional)</span>
            <input
              type="number"
              step="0.01"
              value={savedForm.target_basis}
              onChange={(event) => setSavedForm((prev) => ({ ...prev, target_basis: event.target.value }))}
              className="w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
            />
          </label>
          <label className="flex items-center gap-2 pt-6 text-sm text-black/70">
            <input
              type="checkbox"
              checked={savedForm.is_active}
              onChange={(event) => setSavedForm((prev) => ({ ...prev, is_active: event.target.checked }))}
            />
            Active
          </label>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void createSavedSearch()}
            disabled={submitting}
            className="rounded-md border border-black bg-black px-3 py-2 text-sm text-white disabled:opacity-60"
          >
            Create saved search
          </button>
          <button
            type="button"
            onClick={clearSavedSearchForm}
            className="rounded-md border border-black/20 bg-white px-3 py-2 text-sm"
          >
            Clear form
          </button>
        </div>
        {savedAction ? <p className="mt-3 text-sm text-emerald-700">{savedAction}</p> : null}
        {savedError ? <p className="mt-3 text-sm text-rose-700">{savedError}</p> : null}

        <PreviewTable
          rows={savedPreviewRows}
          emptyMessage={savedPreviewLabel ? `No rows matched "${savedPreviewLabel}".` : "Run saved search preview to see rows."}
        />
      </section>
    </main>
  );
}

function PreviewTable({ rows, emptyMessage }: { rows: PreviewRow[]; emptyMessage: string }) {
  return (
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
          {rows.length === 0 ? (
            <tr>
              <td className="px-2 py-4 text-black/55" colSpan={8}>
                {emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
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
  );
}

function AutomationStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-black/10 bg-white px-3 py-2">
      <div className="text-xs uppercase tracking-wide text-black/45">{label}</div>
      <div className="mt-1 text-sm font-medium">{value}</div>
    </div>
  );
}

function AutomationDetail({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-black/10 bg-white px-3 py-2">
      <div className="text-xs uppercase tracking-wide text-black/45">{label}</div>
      <div className="mt-1 text-sm text-black/80">{value}</div>
    </div>
  );
}

function booleanLabel(value: boolean | undefined) {
  return value ? "Enabled" : "Disabled";
}

function normalizeFacetValues(values: unknown): string[] {
  if (!Array.isArray(values)) return [];
  const map = new Map<string, string>();
  for (const raw of values) {
    if (typeof raw !== "string") continue;
    const value = raw.trim().replace(/\s+/g, " ");
    if (!value || value.toLowerCase() === "nan") continue;
    const key = value.toLowerCase();
    if (!map.has(key)) map.set(key, value);
  }
  return Array.from(map.values()).sort((a, b) => a.localeCompare(b));
}

function setOptionalFilterParams(params: URLSearchParams, form: SavedSearchForm) {
  if (form.commodity_name.trim()) params.set("commodity_name", form.commodity_name.trim());
  if (form.location.trim()) params.set("location", form.location.trim());
  if (form.source_name.trim()) params.set("source_name", form.source_name.trim());
  if (form.delivery_months.trim()) params.set("delivery_months", form.delivery_months.trim());
  if (form.target_cash_price_bu.trim()) params.set("target_cash_price_bu", form.target_cash_price_bu.trim());
  if (form.target_basis.trim()) params.set("target_basis", form.target_basis.trim());
}
