"use client";

import { FormEvent, useEffect, useState } from "react";

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
  trigger_type: string;
  attempt_number: number;
  max_attempts: number;
  duration_ms: number | null;
  parse_success_rate: number | null;
  schema_drift_count: number | null;
  error_message: string | null;
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
};

type SlaSummary = {
  active_sources: number;
  fresh_sources: number;
  stale_sources: number;
  failing_sources: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

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

  async function loadData() {
    const [runsRes, sourcesRes, slaRes, alertsRes] = await Promise.all([
      fetch(`${API_BASE}/api/ingestion/runs?limit=25`, { cache: "no-store" }),
      fetch(`${API_BASE}/api/sources`, { cache: "no-store" }),
      fetch(`${API_BASE}/api/ingestion/sla`, { cache: "no-store" }),
      fetch(`${API_BASE}/api/alerts/recent?limit=10`, { cache: "no-store" }),
    ]);
    const runsJson = runsRes.ok ? await runsRes.json() : { rows: [] };
    const sourcesJson = sourcesRes.ok ? await sourcesRes.json() : { rows: [] };
    const slaJson = slaRes.ok ? await slaRes.json() : null;
    const alertsJson = alertsRes.ok ? await alertsRes.json() : { rows: [] };

    setRuns(runsJson.rows || []);
    setSources(sourcesJson.rows || []);
    setSla(slaJson);
    setAlerts(alertsJson.rows || []);
  }

  useEffect(() => {
    loadData().catch((err) => setError(String(err)));
  }, []);

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
      const res = await fetch(`${API_BASE}/api/ingestion/source-file/run?${params.toString()}`, { method: "POST" });
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
      const res = await fetch(`${API_BASE}/api/sources/${sourceId}/refresh`, { method: "POST" });
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
      const res = await fetch(`${API_BASE}/api/sources/seed`, { method: "POST" });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(typeof json.detail === "string" ? json.detail : "Seed failed");
      }
      setMessage(`Seeded ${json.created ?? 0} sources from registry.`);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function updateAlertStatus(alertId: string, status: "acknowledged" | "resolved") {
    setUpdatingAlertId(alertId);
    setMessage("");
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/alerts/${alertId}/status?status=${status}`, { method: "PATCH" });
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
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-lg font-semibold">Source adapters</h2>
          <button
            disabled={loading}
            onClick={seedSources}
            className="rounded-md border border-black/20 bg-white px-4 py-2 text-sm disabled:opacity-50"
          >
            Seed registry sources
          </button>
        </div>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-black/10 text-xs uppercase tracking-wide text-black/50">
                <th className="px-2 py-2">Source</th>
                <th className="px-2 py-2">Freshness</th>
                <th className="px-2 py-2">Confidence</th>
                <th className="px-2 py-2">Failures</th>
                <th className="px-2 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sources.length === 0 ? (
                <tr>
                  <td className="px-2 py-4 text-black/55" colSpan={5}>
                    No sources configured yet.
                  </td>
                </tr>
              ) : (
                sources.map((source) => (
                  <tr key={source.id} className="border-b border-black/5">
                    <td className="px-2 py-2">
                      <div className="font-medium">{source.name}</div>
                      <div className="text-xs text-black/55">{source.adapter_key || "-"}</div>
                    </td>
                    <td className="px-2 py-2">
                      {source.is_stale ? "stale" : "fresh"} ({source.stale_age_minutes ?? "-"}m)
                    </td>
                    <td className="px-2 py-2">{source.confidence_score ?? "-"}</td>
                    <td className="px-2 py-2">{source.consecutive_failures}</td>
                    <td className="px-2 py-2">
                      <button
                        disabled={refreshingSourceId === source.id}
                        onClick={() => runSourceRefresh(source.id)}
                        className="rounded-md border border-black/20 bg-black px-3 py-1 text-xs text-white disabled:opacity-50"
                      >
                        {refreshingSourceId === source.id ? "Running..." : "Refresh"}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
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
                <th className="px-2 py-2">Duration</th>
                <th className="px-2 py-2">Started</th>
                <th className="px-2 py-2">File</th>
              </tr>
            </thead>
            <tbody>
              {runs.length === 0 ? (
                <tr>
                  <td className="px-2 py-4 text-black/55" colSpan={9}>
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
