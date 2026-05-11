"use client";

import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "../lib/api";

type IngestionRun = {
  id: string;
  source_name: string;
  source_identifier: string;
  started_at: string | null;
  completed_at: string | null;
  status: string;
  raw_row_count: number | null;
  normalized_row_count: number | null;
  created_alert_count: number | null;
  deduped_alert_count: number | null;
  duplicate_key_count: number | null;
  rejected_row_count: number | null;
  missing_required_count: number | null;
  row_reject_reasons: Record<string, number> | null;
  trigger_type: string;
  attempt_number: number;
  max_attempts: number;
  duration_ms: number | null;
  parse_success_rate: number | null;
  schema_drift_count: number | null;
  error_message: string | null;
  quality_summary?: {
    parse_success_rate: number;
    rejection_rate: number;
    row_reject_reasons: Record<string, number>;
  } | null;
};

type RecentAlert = {
  id: string;
  triggered_at: string | null;
  status: "new" | "open" | "pending" | "acknowledged" | "resolved" | string;
  message: string;
  rule_type: string;
  comparison_operator: string;
  threshold_value: number;
  location: string | null;
};

type SourceRow = {
  id: string;
  name: string;
  adapter_key: string | null;
  source_type: string;
  region: string | null;
  is_active: boolean;
  polling_interval_minutes: number;
  timeout_seconds: number;
  max_retries: number;
  last_success_at: string | null;
  stale_age_minutes: number | null;
  is_stale: boolean;
  confidence_score: number | null;
  consecutive_failures: number;
  latest_error_message: string | null;
  latest_parse_success_rate: number | null;
  latest_schema_drift_count: number | null;
  latest_duplicate_key_count: number | null;
  latest_rejected_row_count: number | null;
  latest_missing_required_count: number | null;
  latest_row_reject_reasons: Record<string, number> | null;
  successful_run_count: number;
  promotion_status: string;
  can_refresh?: boolean;
  logical_parent_source_name?: string;
  logical_row_count?: number;
};

type SlaSummary = {
  generated_at: string;
  active_sources: number;
  fresh_sources: number;
  stale_sources: number;
  failing_sources: number;
  last_successful_ingestion_run?: {
    id: string;
    status: string;
    started_at: string | null;
    completed_at: string | null;
  } | null;
  failing_source_rows?: {
    id: string;
    name: string;
    consecutive_failures: number;
    latest_error_message: string | null;
  }[];
  latest_quality?: {
    parse_success_rate: number;
    rejected_row_count: number;
    missing_required_count: number;
  } | null;
};

type QualityBreakdown = {
  run: {
    id: string;
    status: string;
    raw_row_count: number | null;
    normalized_row_count: number | null;
    rejected_row_count: number | null;
    totals: Record<string, number>;
    by_source: Record<string, Record<string, number>>;
    by_field: Record<string, number>;
  } | null;
};

export default function SourcesPage() {
  const [runs, setRuns] = useState<IngestionRun[]>([]);
  const [alerts, setAlerts] = useState<RecentAlert[]>([]);
  const [sources, setSources] = useState<SourceRow[]>([]);
  const [sla, setSla] = useState<SlaSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshingSourceId, setRefreshingSourceId] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [updatingAlertId, setUpdatingAlertId] = useState("");
  const [openAlertsOnly, setOpenAlertsOnly] = useState(true);
  const [runningScheduledCycle, setRunningScheduledCycle] = useState(false);
  const [qualityBreakdown, setQualityBreakdown] = useState<QualityBreakdown["run"]>(null);

  async function loadData() {
    const openOnlyQuery = openAlertsOnly ? "&open_only=true" : "";
    const [runsRes, sourcesRes, slaRes, alertsRes, qualityRes] = await Promise.all([
      apiFetch(`/api/ingestion/runs?limit=25`),
      apiFetch(`/api/sources`),
      apiFetch(`/api/ingestion/sla`),
      apiFetch(`/api/alerts/recent?limit=10${openOnlyQuery}`),
      apiFetch(`/api/ingestion/quality/latest`),
    ]);
    const runsJson = runsRes.ok ? await runsRes.json() : { rows: [] };
    const sourcesJson = sourcesRes.ok ? await sourcesRes.json() : { rows: [] };
    const slaJson = slaRes.ok ? await slaRes.json() : null;
    const alertsJson = alertsRes.ok ? await alertsRes.json() : { rows: [] };
    const qualityJson = qualityRes.ok ? ((await qualityRes.json()) as QualityBreakdown) : { run: null };

    setRuns(runsJson.rows || []);
    setSources(sourcesJson.rows || []);
    setSla(slaJson);
    setAlerts(alertsJson.rows || []);
    setQualityBreakdown(qualityJson.run || null);
  }

  useEffect(() => {
    loadData().catch((err) => setError(String(err)));
  }, [openAlertsOnly]);

  async function triggerIngestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setMessage("");
    setError("");

    const form = new FormData(event.currentTarget);
    const params = new URLSearchParams();
    for (const key of ["source_file_path", "source_name", "source_id", "commodity_id"]) {
      const value = String(form.get(key) || "").trim();
      if (value) params.set(key, value);
    }

    try {
      const res = await apiFetch(`/api/ingestion/source-file/run?${params.toString()}`, { method: "POST" });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(typeof json.detail === "string" ? json.detail : "Ingestion failed");
      }
      setMessage(`Ingestion ${json.result.status}. Normalized ${json.result.normalized_row_count ?? 0} rows.`);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function runSourceRefresh(sourceId: string) {
    setRefreshingSourceId(sourceId);
    setMessage("");
    setError("");
    try {
      const res = await apiFetch(`/api/sources/${sourceId}/refresh`, { method: "POST" });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(typeof json.detail === "string" ? json.detail : "Source refresh failed");
      }
      setMessage(
        `Source refresh completed in ${json.result.duration_ms ?? 0} ms. ` +
          `Alerts: +${json.result.alerts_created ?? 0}, deduped ${json.result.alerts_deduped ?? 0}.`
      );
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRefreshingSourceId("");
    }
  }

  async function seedSources() {
    setLoading(true);
    setMessage("");
    setError("");
    try {
      const res = await apiFetch(`/api/sources/seed?scope=pilot`, { method: "POST" });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(typeof json.detail === "string" ? json.detail : "Seed failed");
      }
      setMessage(`Seeded ${json.created ?? 0} ${json.scope} sources from registry.`);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function runScheduledCycle() {
    setRunningScheduledCycle(true);
    setMessage("");
    setError("");
    try {
      const res = await apiFetch(`/api/ingestion/source-files/run?max_attempts=2`, { method: "POST" });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(typeof json.detail === "string" ? json.detail : "Scheduled cycle failed");
      }
      setMessage(
        `Scheduled cycle complete. ${json.summary.completed_sources}/${json.summary.total_sources} sources succeeded.`
      );
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunningScheduledCycle(false);
    }
  }

  async function updateAlertStatus(alertId: string, status: "acknowledged" | "resolved") {
    setUpdatingAlertId(alertId);
    setMessage("");
    setError("");
    try {
      const res = await apiFetch(`/api/alerts/${alertId}/status?status=${status}`, { method: "PATCH" });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(typeof json.detail === "string" ? json.detail : "Alert update failed");
      }
      setMessage(`Alert updated to ${json.status}.`);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setUpdatingAlertId("");
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-6 py-10">
      <header>
        <p className="text-xs uppercase tracking-[0.16em] text-black/50">GrainBids / Sources</p>
        <h1 className="mt-1 font-[family-name:var(--font-serif)] text-4xl leading-tight">Source Ingestion</h1>
        <p className="mt-2 text-sm text-black/65">Run and monitor source adapters, ingestion SLA, and configured file ingestion.</p>
      </header>

      <section className="mt-6 grid gap-4 md:grid-cols-4">
        <MetricCard label="Active Sources" value={sla?.active_sources ?? 0} />
        <MetricCard label="Fresh Sources" value={sla?.fresh_sources ?? 0} />
        <MetricCard label="Stale Sources" value={sla?.stale_sources ?? 0} />
        <MetricCard label="Failing Sources" value={sla?.failing_sources ?? 0} />
      </section>

      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Latest rejection diagnostics</h2>
        {qualityBreakdown ? (
          <div className="mt-4 grid gap-5 md:grid-cols-2">
            <div>
              <h3 className="text-sm font-medium text-black/80">By field</h3>
              <ul className="mt-2 space-y-1 text-sm text-black/70">
                {Object.entries(qualityBreakdown.by_field || {}).length === 0 ? (
                  <li>No field-level rejects.</li>
                ) : (
                  Object.entries(qualityBreakdown.by_field)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 8)
                    .map(([field, count]) => <li key={field}>{field}: {count}</li>)
                )}
              </ul>
            </div>
            <div>
              <h3 className="text-sm font-medium text-black/80">Top source sheets by rejects</h3>
              <ul className="mt-2 space-y-1 text-sm text-black/70">
                {Object.entries(qualityBreakdown.by_source || {}).length === 0 ? (
                  <li>No source-level rejects.</li>
                ) : (
                  Object.entries(qualityBreakdown.by_source)
                    .map(([source, reasons]) => [
                      source,
                      Object.values(reasons).reduce((sum, value) => sum + Number(value || 0), 0),
                    ] as const)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 8)
                    .map(([source, total]) => <li key={source}>{source}: {total}</li>)
                )}
              </ul>
            </div>
          </div>
        ) : (
          <p className="mt-2 text-sm text-black/60">No run data available yet.</p>
        )}
      </section>
      <p className="mt-3 text-xs text-black/55">
        Last successful ingestion:{" "}
        {sla?.last_successful_ingestion_run?.started_at
          ? new Date(sla.last_successful_ingestion_run.started_at).toLocaleString()
          : "-"}
      </p>
      <p className="mt-1 text-xs text-black/55">
        Latest quality: parse {sla?.latest_quality ? `${(sla.latest_quality.parse_success_rate * 100).toFixed(1)}%` : "-"} | rejected{" "}
        {sla?.latest_quality?.rejected_row_count ?? "-"} | missing required {sla?.latest_quality?.missing_required_count ?? "-"}
      </p>

      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-lg font-semibold">Source adapters</h2>
          <div className="flex items-center gap-2">
            <button
              disabled={runningScheduledCycle}
              onClick={runScheduledCycle}
              className="rounded-md border border-black/20 bg-black px-4 py-2 text-sm text-white disabled:opacity-50"
            >
              {runningScheduledCycle ? "Running cycle..." : "Run scheduled file cycle"}
            </button>
            <button
              disabled={loading}
              onClick={seedSources}
              className="rounded-md border border-black/20 bg-white px-4 py-2 text-sm disabled:opacity-50"
            >
              Seed pilot adapters
            </button>
          </div>
        </div>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-black/10 text-xs uppercase tracking-wide text-black/50">
                <th className="px-2 py-2">Source</th>
                <th className="px-2 py-2">Interval</th>
                <th className="px-2 py-2">Freshness</th>
                <th className="px-2 py-2">Confidence</th>
                <th className="px-2 py-2">Parse %</th>
                <th className="px-2 py-2">Failures</th>
                <th className="px-2 py-2">Last Success</th>
                <th className="px-2 py-2">Last Error</th>
                <th className="px-2 py-2">Promotion</th>
                <th className="px-2 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sources.length === 0 ? (
                <tr>
                  <td className="px-2 py-4 text-black/55" colSpan={10}>
                    No sources configured yet.
                  </td>
                </tr>
              ) : (
                sources.map((source) => (
                  <tr key={source.id} className="border-b border-black/5">
                    <td className="px-2 py-2">
                      <div className="font-medium">{source.name}</div>
                      <div className="text-xs text-black/55">
                        {source.logical_parent_source_name
                          ? `${source.logical_parent_source_name} (${source.logical_row_count ?? 0} rows)`
                          : source.adapter_key || "-"}
                      </div>
                    </td>
                    <td className="px-2 py-2">{source.polling_interval_minutes}m</td>
                    <td className="px-2 py-2">
                      {source.is_stale ? "stale" : "fresh"} ({source.stale_age_minutes ?? "-"}m)
                    </td>
                    <td className="px-2 py-2">{source.confidence_score ?? "-"}</td>
                    <td className="px-2 py-2">
                      {source.latest_parse_success_rate != null ? `${(source.latest_parse_success_rate * 100).toFixed(1)}%` : "-"}
                    </td>
                    <td className="px-2 py-2">{source.consecutive_failures}</td>
                    <td className="px-2 py-2">{source.last_success_at ? new Date(source.last_success_at).toLocaleString() : "-"}</td>
                    <td className="px-2 py-2 max-w-64 truncate" title={source.latest_error_message || ""}>
                      {source.latest_error_message || "-"}
                    </td>
                    <td className="px-2 py-2">
                      {source.promotion_status}
                      <div className="text-xs text-black/50">runs: {source.successful_run_count}</div>
                    </td>
                    <td className="px-2 py-2">
                      {source.can_refresh === false ? (
                        <span className="text-xs text-black/55">n/a</span>
                      ) : (
                        <button
                          disabled={refreshingSourceId === source.id}
                          onClick={() => runSourceRefresh(source.id)}
                          className="rounded-md border border-black/20 bg-black px-3 py-1 text-xs text-white disabled:opacity-50"
                        >
                          {refreshingSourceId === source.id ? "Running..." : "Refresh"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {sla?.failing_source_rows && sla.failing_source_rows.length > 0 ? (
          <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm">
            <p className="font-medium text-red-900">Failing sources</p>
            <ul className="mt-2 space-y-1 text-red-800">
              {sla.failing_source_rows.map((item) => (
                <li key={item.id}>
                  {item.name}: {item.consecutive_failures} failures {item.latest_error_message ? `(${item.latest_error_message})` : ""}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Manual admin trigger</h2>
        <form className="mt-4 grid gap-3 md:grid-cols-2" onSubmit={triggerIngestion}>
          <Field name="source_file_path" label="Source file path" placeholder="P:\Adam\DailyBids\latest.xlsx" />
          <Field name="source_name" label="Source name" placeholder="Daily bid file" />
          <Field name="source_id" label="Source ID" placeholder="UUID from sources table" />
          <Field name="commodity_id" label="Commodity ID" placeholder="UUID from commodities table" />
          <div className="md:col-span-2 flex items-center gap-3">
            <button disabled={loading} className="rounded-md border border-black/20 bg-black px-4 py-2 text-sm text-white disabled:opacity-50">
              {loading ? "Running..." : "Run ingestion"}
            </button>
            {message ? <span className="text-sm text-emerald-700">{message}</span> : null}
            {error ? <span className="text-sm text-red-700">{error}</span> : null}
          </div>
        </form>
      </section>

      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Recent ingestion runs</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-black/10 text-xs uppercase tracking-wide text-black/50">
                <th className="px-2 py-2">Source</th>
                <th className="px-2 py-2">Status</th>
                <th className="px-2 py-2">Raw</th>
                <th className="px-2 py-2">Normalized</th>
                <th className="px-2 py-2">Alerts +</th>
                <th className="px-2 py-2">Alerts deduped</th>
                <th className="px-2 py-2">Duplicates</th>
                <th className="px-2 py-2">Rejected</th>
                <th className="px-2 py-2">Missing req</th>
                <th className="px-2 py-2">Reject reasons</th>
                <th className="px-2 py-2">Parse %</th>
                <th className="px-2 py-2">Duration</th>
                <th className="px-2 py-2">Started</th>
                <th className="px-2 py-2">File</th>
              </tr>
            </thead>
            <tbody>
              {runs.length === 0 ? (
                <tr>
                  <td className="px-2 py-4 text-black/55" colSpan={14}>
                    No ingestion runs yet.
                  </td>
                </tr>
              ) : (
                runs.map((run) => (
                  <tr key={run.id} className="border-b border-black/5">
                    <td className="px-2 py-2">{run.source_name}</td>
                    <td className="px-2 py-2">{run.status}</td>
                    <td className="px-2 py-2">{run.raw_row_count ?? "-"}</td>
                    <td className="px-2 py-2">{run.normalized_row_count ?? "-"}</td>
                    <td className="px-2 py-2">{run.created_alert_count ?? 0}</td>
                    <td className="px-2 py-2">{run.deduped_alert_count ?? 0}</td>
                    <td className="px-2 py-2">{run.duplicate_key_count ?? 0}</td>
                    <td className="px-2 py-2">{run.rejected_row_count ?? 0}</td>
                    <td className="px-2 py-2">{run.missing_required_count ?? 0}</td>
                    <td className="px-2 py-2 max-w-56 truncate" title={formatRejectReasons(run.row_reject_reasons)}>
                      {formatRejectReasons(run.row_reject_reasons)}
                    </td>
                    <td className="px-2 py-2">
                      {run.parse_success_rate != null ? `${(run.parse_success_rate * 100).toFixed(1)}%` : "-"}
                    </td>
                    <td className="px-2 py-2">{run.duration_ms ?? "-"}</td>
                    <td className="px-2 py-2">{run.started_at ? new Date(run.started_at).toLocaleString() : "-"}</td>
                    <td className="px-2 py-2">{run.source_identifier}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Latest triggered alerts</h2>
        <label className="mt-3 inline-flex items-center gap-2 text-xs text-black/70">
          <input
            type="checkbox"
            checked={openAlertsOnly}
            onChange={(event) => setOpenAlertsOnly(event.target.checked)}
            className="h-4 w-4 rounded border border-black/20"
          />
          Show open alerts only
        </label>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-black/10 text-xs uppercase tracking-wide text-black/50">
                <th className="px-2 py-2">When</th>
                <th className="px-2 py-2">Rule</th>
                <th className="px-2 py-2">Status</th>
                <th className="px-2 py-2">Message</th>
                <th className="px-2 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {alerts.length === 0 ? (
                <tr>
                  <td className="px-2 py-4 text-black/55" colSpan={5}>
                    No alerts triggered yet.
                  </td>
                </tr>
              ) : (
                alerts.map((alert) => (
                  <tr key={alert.id} className="border-b border-black/5">
                    <td className="px-2 py-2">{alert.triggered_at ? new Date(alert.triggered_at).toLocaleString() : "-"}</td>
                    <td className="px-2 py-2">
                      {alert.rule_type} {alert.comparison_operator} {alert.threshold_value}
                      {alert.location ? ` @ ${alert.location}` : ""}
                    </td>
                    <td className="px-2 py-2">{alert.status}</td>
                    <td className="px-2 py-2">{alert.message}</td>
                    <td className="px-2 py-2">
                      <div className="flex gap-2">
                        <button
                          disabled={updatingAlertId === alert.id || alert.status === "acknowledged" || alert.status === "resolved"}
                          onClick={() => updateAlertStatus(alert.id, "acknowledged")}
                          className="rounded-md border border-black/20 bg-white px-2 py-1 text-xs disabled:opacity-50"
                        >
                          Acknowledge
                        </button>
                        <button
                          disabled={updatingAlertId === alert.id || alert.status === "resolved"}
                          onClick={() => updateAlertStatus(alert.id, "resolved")}
                          className="rounded-md border border-black/20 bg-black px-2 py-1 text-xs text-white disabled:opacity-50"
                        >
                          Resolve
                        </button>
                      </div>
                    </td>
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

function MetricCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl border border-black/10 bg-white/65 p-4 backdrop-blur">
      <div className="text-xs uppercase tracking-wide text-black/50">{label}</div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
    </div>
  );
}

function Field({ name, label, placeholder }: { name: string; label: string; placeholder: string }) {
  return (
    <label className="text-sm">
      <span className="text-xs uppercase tracking-wide text-black/50">{label}</span>
      <input name={name} placeholder={placeholder} className="mt-1 w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm" />
    </label>
  );
}

function formatRejectReasons(reasons: Record<string, number> | null | undefined): string {
  if (!reasons || Object.keys(reasons).length === 0) {
    return "-";
  }
  return Object.entries(reasons)
    .map(([key, count]) => `${key}:${count}`)
    .join(", ");
}
