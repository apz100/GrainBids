"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { API_BASE, buildApiHeaders, getApiConfigError, isAdminRole } from "@/lib/api";

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
  country_code: string | null;
  currency_code: string | null;
  timezone_name: string | null;
  collection_status: string;
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

type ProbeCoverage = {
  matched_columns: string[];
  present_rows: number;
  total_rows: number;
  ratio: number;
};

type ProbeResult = {
  passed: boolean;
  attempts: number;
  timeout_seconds: number;
  raw_row_count: number;
  column_count: number;
  columns: string[];
  required_field_coverage: Record<string, ProbeCoverage>;
  commodities: string[];
  locations: string[];
  pass_reasons: string[];
  fail_reasons: string[];
  preview: Record<string, string | number | boolean | null>[];
  preview_limit: number;
  preview_truncated: boolean;
  persisted: boolean;
};

type ProbeResponse = {
  source: Pick<SourceRow, "id" | "name" | "adapter_key" | "collection_status" | "is_active">;
  result: ProbeResult;
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

type FacetsResponse = {
  company_rows?: { id: string; name: string }[];
};

type CanonicalCoverageRow = {
  source_name: string | null;
  source_key: string | null;
  row_count: number;
  canonical_count: number;
  winner_rate: number;
};

type CompanyPriorityCandidateRow = {
  source_key: string;
  display_name: string;
  row_count: number;
  canonical_count: number;
  winner_rate: number;
  policy_rank: number;
};

export default function SourcesPage() {
  const headers = buildApiHeaders();
  const adminAllowed = isAdminRole();
  const configError = getApiConfigError({ requireOrg: true });
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
  const [companyRows, setCompanyRows] = useState<{ id: string; name: string }[]>([]);
  const [selectedCompanyId, setSelectedCompanyId] = useState("");
  const [priorityKeysInput, setPriorityKeysInput] = useState("");
  const [loadingPriority, setLoadingPriority] = useState(false);
  const [savingPriority, setSavingPriority] = useState(false);
  const [seedingDefaults, setSeedingDefaults] = useState(false);
  const [coverageRows, setCoverageRows] = useState<CanonicalCoverageRow[]>([]);
  const [priorityCandidates, setPriorityCandidates] = useState<CompanyPriorityCandidateRow[]>([]);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [importingCandidates, setImportingCandidates] = useState(false);
  const [probingSourceId, setProbingSourceId] = useState("");
  const [updatingSourceId, setUpdatingSourceId] = useState("");
  const [probeResponse, setProbeResponse] = useState<ProbeResponse | null>(null);

  async function loadData() {
    const openOnlyQuery = openAlertsOnly ? "&open_only=true" : "";
    const [runsRes, sourcesRes, slaRes, alertsRes, facetsRes, coverageRes] = await Promise.all([
      fetch(`${API_BASE}/api/ingestion/runs?limit=25`, { cache: "no-store", headers }),
      fetch(`${API_BASE}/api/sources`, { cache: "no-store", headers }),
      fetch(`${API_BASE}/api/ingestion/sla`, { cache: "no-store", headers }),
      fetch(`${API_BASE}/api/alerts/recent?limit=10${openOnlyQuery}`, { cache: "no-store", headers }),
      fetch(`${API_BASE}/api/normalized-prices/facets`, { cache: "no-store", headers }),
      fetch(`${API_BASE}/api/sources/canonical-coverage?days=7`, { cache: "no-store", headers }),
    ]);
    const runsJson = runsRes.ok ? await runsRes.json() : { rows: [] };
    const sourcesJson = sourcesRes.ok ? await sourcesRes.json() : { rows: [] };
    const slaJson = slaRes.ok ? await slaRes.json() : null;
    const alertsJson = alertsRes.ok ? await alertsRes.json() : { rows: [] };
    const facetsJson: FacetsResponse = facetsRes.ok ? await facetsRes.json() : { company_rows: [] };
    const coverageJson = coverageRes.ok ? await coverageRes.json() : { rows: [] };
    setRuns(runsJson.rows || []);
    setSources(sourcesJson.rows || []);
    setSla(slaJson);
    setAlerts(alertsJson.rows || []);
    setCompanyRows(Array.isArray(facetsJson.company_rows) ? facetsJson.company_rows : []);
    setCoverageRows(Array.isArray(coverageJson.rows) ? coverageJson.rows : []);
  }

  useEffect(() => {
    if (!adminAllowed) {
      return;
    }
    if (configError) {
      setError(configError);
      return;
    }
    loadData().catch((err) => setError(String(err)));
  }, [adminAllowed, openAlertsOnly, configError]);

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
      const res = await fetch(`${API_BASE}/api/ingestion/source-file/run?${params.toString()}`, { method: "POST", headers });
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
      const res = await fetch(`${API_BASE}/api/sources/${sourceId}/refresh`, { method: "POST", headers });
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
      const res = await fetch(`${API_BASE}/api/sources/seed?scope=pilot`, { method: "POST", headers });
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

  async function importUsCandidates() {
    setImportingCandidates(true);
    setMessage("");
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/sources/seed-us-candidates`, { method: "POST", headers });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(typeof json.detail === "string" ? json.detail : "Candidate import failed");
      }
      setMessage(`Imported ${json.created ?? 0} inactive US candidates; skipped ${json.skipped ?? 0}.`);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setImportingCandidates(false);
    }
  }

  async function probeCandidate(sourceId: string) {
    setProbingSourceId(sourceId);
    setProbeResponse(null);
    setMessage("");
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/sources/${sourceId}/probe`, { method: "POST", headers });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(typeof json.detail === "string" ? json.detail : "Candidate probe failed");
      }
      setProbeResponse(json as ProbeResponse);
      setMessage(`Probe completed for ${json.source.name}: ${json.result.passed ? "passed" : "needs review"}. No rows were saved.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setProbingSourceId("");
    }
  }

  async function updateCandidateStatus(source: SourceRow, action: "promote-to-pilot" | "quarantine") {
    const verb = action === "promote-to-pilot" ? "promote to pilot and activate" : "quarantine";
    if (!window.confirm(`Confirm: ${verb} ${source.name}?`)) return;

    setUpdatingSourceId(source.id);
    setMessage("");
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/sources/${source.id}/${action}`, { method: "POST", headers });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(typeof json.detail === "string" ? json.detail : `Failed to ${verb}`);
      }
      setMessage(`${source.name} is now ${json.collection_status}.`);
      setProbeResponse(null);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setUpdatingSourceId("");
    }
  }

  async function runScheduledCycle() {
    setRunningScheduledCycle(true);
    setMessage("");
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/ingestion/source-files/run?max_attempts=2`, { method: "POST", headers });
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

  async function loadPriority(companyId: string) {
    if (!companyId) {
      setPriorityKeysInput("");
      setPriorityCandidates([]);
      return;
    }
    setLoadingPriority(true);
    setLoadingCandidates(true);
    setError("");
    try {
      const [priorityRes, candidatesRes] = await Promise.all([
        fetch(`${API_BASE}/api/sources/priority?company_id=${companyId}`, { cache: "no-store", headers }),
        fetch(`${API_BASE}/api/sources/priority/candidates?company_id=${companyId}`, { cache: "no-store", headers }),
      ]);

      const priorityJson = await priorityRes.json();
      if (!priorityRes.ok) {
        throw new Error(typeof priorityJson.detail === "string" ? priorityJson.detail : "Failed to load priority");
      }
      const keys = (priorityJson.rows || []).map((row: { source_key: string }) => row.source_key);
      setPriorityKeysInput(keys.join("\n"));

      const candidatesJson = await candidatesRes.json();
      if (!candidatesRes.ok) {
        throw new Error(typeof candidatesJson.detail === "string" ? candidatesJson.detail : "Failed to load candidates");
      }
      setPriorityCandidates(Array.isArray(candidatesJson.rows) ? candidatesJson.rows : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoadingPriority(false);
      setLoadingCandidates(false);
    }
  }

  async function savePriority() {
    if (!selectedCompanyId) return;
    setSavingPriority(true);
    setMessage("");
    setError("");
    try {
      const sourceKeys = priorityKeysInput
        .split(/\r?\n|,/)
        .map((item) => item.trim())
        .filter(Boolean)
        .join(",");
      const res = await fetch(
        `${API_BASE}/api/sources/priority?company_id=${selectedCompanyId}&source_keys=${encodeURIComponent(sourceKeys)}`,
        { method: "PUT", headers }
      );
      const json = await res.json();
      if (!res.ok) {
        throw new Error(typeof json.detail === "string" ? json.detail : "Failed to save priority");
      }
      setMessage(`Updated source priority for ${json.company_name}.`);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingPriority(false);
    }
  }

  async function seedDefaultPriority() {
    setSeedingDefaults(true);
    setMessage("");
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/sources/priority/seed-defaults`, {
        method: "POST",
        headers,
      });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(typeof json.detail === "string" ? json.detail : "Failed to seed defaults");
      }
      setMessage(`Seeded defaults for ${json.seeded_companies} companies (${json.touched_rows} rows).`);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSeedingDefaults(false);
    }
  }

  function applyCoverageOrder() {
    if (priorityCandidates.length === 0) return;
    const ordered = [...priorityCandidates]
      .sort((a, b) => {
        if (a.policy_rank !== b.policy_rank) return a.policy_rank - b.policy_rank;
        if (a.winner_rate !== b.winner_rate) return b.winner_rate - a.winner_rate;
        if (a.row_count !== b.row_count) return b.row_count - a.row_count;
        return a.source_key.localeCompare(b.source_key);
      })
      .map((row) => row.source_key);
    setPriorityKeysInput(ordered.join("\n"));
  }

  async function updateAlertStatus(alertId: string, status: "acknowledged" | "resolved") {
    setUpdatingAlertId(alertId);
    setMessage("");
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/alerts/${alertId}/status?status=${status}`, { method: "PATCH", headers });
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

  if (!adminAllowed) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-12">
        <div className="rounded-xl border border-black/10 bg-white/80 p-6 shadow-sm">
          <p className="text-xs uppercase tracking-[0.16em] text-black/50">Admin route</p>
          <h1 className="mt-2 font-[family-name:var(--font-serif)] text-3xl">Access restricted</h1>
          <p className="mt-3 text-sm text-black/70">Sources and ingestion controls are admin-only in this phase.</p>
          <div className="mt-5">
            <Link href="/bids" className="rounded-md border border-black/20 bg-white px-4 py-2 text-sm">
              Return to Market
            </Link>
          </div>
        </div>
      </main>
    );
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
        <h2 className="text-lg font-semibold">Canonical winner coverage (7d)</h2>
        <p className="mt-2 text-sm text-black/70">
          Shows how often each source appears in canonical winner rows versus total candidate rows.
        </p>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-black/10 text-xs uppercase tracking-wide text-black/50">
                <th className="px-2 py-2">Source</th>
                <th className="px-2 py-2">Source key</th>
                <th className="px-2 py-2 text-right">Candidates</th>
                <th className="px-2 py-2 text-right">Winners</th>
                <th className="px-2 py-2 text-right">Winner rate</th>
              </tr>
            </thead>
            <tbody>
              {coverageRows.length === 0 ? (
                <tr>
                  <td className="px-2 py-4 text-black/55" colSpan={5}>
                    No coverage data yet.
                  </td>
                </tr>
              ) : (
                coverageRows.map((row) => (
                  <tr key={`${row.source_key}-${row.source_name}`} className="border-b border-black/5">
                    <td className="px-2 py-2">{row.source_name || "-"}</td>
                    <td className="px-2 py-2 font-mono text-xs text-black/65">{row.source_key || "-"}</td>
                    <td className="px-2 py-2 text-right">{row.row_count}</td>
                    <td className="px-2 py-2 text-right">{row.canonical_count}</td>
                    <td className="px-2 py-2 text-right">{(row.winner_rate * 100).toFixed(1)}%</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Source priority by company</h2>
        <p className="mt-2 text-sm text-black/70">
          Canonical resolver picks one winner per market key. Set ordered source keys for each company (top line wins).
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-[320px_1fr]">
          <div>
            <label className="text-xs uppercase tracking-wide text-black/55">Company</label>
            <select
              value={selectedCompanyId}
              onChange={(event) => {
                const nextCompanyId = event.target.value;
                setSelectedCompanyId(nextCompanyId);
                void loadPriority(nextCompanyId);
              }}
              className="mt-1 w-full rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
            >
              <option value="">Select company</option>
              {companyRows.map((company) => (
                <option key={company.id} value={company.id}>
                  {company.name}
                </option>
              ))}
            </select>
            <p className="mt-2 text-xs text-black/55">Available source keys from adapter names and canonical source labels.</p>
          </div>
          <div>
            <label className="text-xs uppercase tracking-wide text-black/55">Ordered source keys (one per line)</label>
            <textarea
              value={priorityKeysInput}
              onChange={(event) => setPriorityKeysInput(event.target.value)}
              placeholder="agricharts&#10;glg&#10;andersons"
              className="mt-1 min-h-28 w-full rounded-md border border-black/15 bg-white px-3 py-2 font-mono text-sm"
            />
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={!selectedCompanyId || loadingPriority || savingPriority}
                onClick={() => void loadPriority(selectedCompanyId)}
                className="rounded-md border border-black/20 bg-white px-3 py-2 text-sm disabled:opacity-50"
              >
                {loadingPriority ? "Loading..." : "Reload"}
              </button>
              <button
                type="button"
                disabled={!selectedCompanyId || savingPriority}
                onClick={savePriority}
                className="rounded-md border border-black/20 bg-black px-3 py-2 text-sm text-white disabled:opacity-50"
              >
                {savingPriority ? "Saving..." : "Save priority"}
              </button>
              <button
                type="button"
                disabled={!selectedCompanyId || loadingCandidates || priorityCandidates.length === 0}
                onClick={applyCoverageOrder}
                className="rounded-md border border-black/20 bg-white px-3 py-2 text-sm disabled:opacity-50"
              >
                Apply recommended order
              </button>
            </div>
          </div>
        </div>
        <div className="mt-4 overflow-x-auto rounded-md border border-black/10 bg-white">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-black/10 text-xs uppercase tracking-wide text-black/50">
                <th className="px-2 py-2">Source key</th>
                <th className="px-2 py-2">Display</th>
                <th className="px-2 py-2 text-right">Rows</th>
                <th className="px-2 py-2 text-right">Winners</th>
                <th className="px-2 py-2 text-right">Winner rate</th>
                <th className="px-2 py-2 text-right">Policy rank</th>
              </tr>
            </thead>
            <tbody>
              {priorityCandidates.length === 0 ? (
                <tr>
                  <td className="px-2 py-4 text-black/55" colSpan={6}>
                    {selectedCompanyId ? "No source candidates found." : "Select a company to see source candidates."}
                  </td>
                </tr>
              ) : (
                priorityCandidates.map((row) => (
                  <tr key={row.source_key} className="border-b border-black/5">
                    <td className="px-2 py-2 font-mono text-xs">{row.source_key}</td>
                    <td className="px-2 py-2">{row.display_name}</td>
                    <td className="px-2 py-2 text-right">{row.row_count}</td>
                    <td className="px-2 py-2 text-right">{row.canonical_count}</td>
                    <td className="px-2 py-2 text-right">{(row.winner_rate * 100).toFixed(1)}%</td>
                    <td className="px-2 py-2 text-right">{row.policy_rank}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Latest rejection diagnostics</h2>
        <div className="mt-3 text-sm text-black/70">
          <p>Use the latest ingestion run table below for reject counts and reason breakdown.</p>
        </div>
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
            <button
              disabled={importingCandidates}
              onClick={importUsCandidates}
              className="rounded-md border border-black/20 bg-white px-4 py-2 text-sm disabled:opacity-50"
            >
              {importingCandidates ? "Importing..." : "Import US candidates"}
            </button>
            <button
              disabled={seedingDefaults}
              onClick={seedDefaultPriority}
              className="rounded-md border border-black/20 bg-white px-4 py-2 text-sm disabled:opacity-50"
            >
              {seedingDefaults ? "Seeding defaults..." : "Seed company source priority"}
            </button>
          </div>
        </div>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-black/10 text-xs uppercase tracking-wide text-black/50">
                <th className="px-2 py-2">Source</th>
                <th className="px-2 py-2">Geography</th>
                <th className="px-2 py-2">Collection</th>
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
                  <td className="px-2 py-4 text-black/55" colSpan={12}>
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
                    <td className="px-2 py-2">
                      <div>{source.region || "-"}</div>
                      <div className="text-xs text-black/50">
                        {[source.country_code, source.currency_code, source.timezone_name].filter(Boolean).join(" · ") || "-"}
                      </div>
                    </td>
                    <td className="px-2 py-2">
                      <div>{source.collection_status}</div>
                      <div className="text-xs text-black/50">{source.is_active ? "active" : "inactive"}</div>
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
                      {source.collection_status === "candidate" && !source.is_active ? (
                        <div className="flex flex-wrap gap-1">
                          <button
                            disabled={probingSourceId === source.id || updatingSourceId === source.id}
                            onClick={() => probeCandidate(source.id)}
                            className="rounded-md border border-black/20 bg-black px-3 py-1 text-xs text-white disabled:opacity-50"
                          >
                            {probingSourceId === source.id ? "Probing..." : "Probe"}
                          </button>
                          <button
                            disabled={
                              updatingSourceId === source.id ||
                              probeResponse?.source.id !== source.id ||
                              !probeResponse.result.passed
                            }
                            onClick={() => updateCandidateStatus(source, "promote-to-pilot")}
                            className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-1 text-xs text-emerald-900 disabled:opacity-40"
                            title="A passing probe is required in this browser session"
                          >
                            Promote
                          </button>
                          <button
                            disabled={updatingSourceId === source.id}
                            onClick={() => updateCandidateStatus(source, "quarantine")}
                            className="rounded-md border border-amber-300 bg-amber-50 px-3 py-1 text-xs text-amber-900 disabled:opacity-50"
                          >
                            Quarantine
                          </button>
                        </div>
                      ) : source.can_refresh === false ? (
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
        {probeResponse ? <ProbeResultPanel response={probeResponse} /> : null}
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

function ProbeResultPanel({ response }: { response: ProbeResponse }) {
  const result = response.result;
  const previewColumns = result.preview.length > 0 ? Object.keys(result.preview[0]) : [];
  return (
    <div className="mt-5 rounded-lg border border-black/10 bg-white p-4 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-semibold">Probe result: {response.source.name}</p>
          <p className="mt-1 text-xs text-black/55">
            One attempt · {result.raw_row_count} raw rows · {result.column_count} columns · nothing persisted
          </p>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-medium ${
            result.passed ? "bg-emerald-100 text-emerald-900" : "bg-amber-100 text-amber-900"
          }`}
        >
          {result.passed ? "Passed" : "Needs review"}
        </span>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-black/50">Required-field coverage</p>
          <ul className="mt-2 space-y-1">
            {Object.entries(result.required_field_coverage).map(([field, coverage]) => (
              <li key={field}>
                {field}: {(coverage.ratio * 100).toFixed(1)}% ({coverage.present_rows}/{coverage.total_rows})
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-black/50">Coverage found</p>
          <p className="mt-2">Commodities: {result.commodities.join(", ") || "none"}</p>
          <p className="mt-1">Locations: {result.locations.join(", ") || "none"}</p>
          <p className="mt-1">Columns: {result.columns.join(", ") || "none"}</p>
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div className="rounded-md bg-emerald-50 p-3 text-emerald-900">
          <p className="font-medium">Passed checks</p>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {result.pass_reasons.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
        </div>
        <div className="rounded-md bg-amber-50 p-3 text-amber-900">
          <p className="font-medium">Failed checks</p>
          {result.fail_reasons.length > 0 ? (
            <ul className="mt-1 list-disc space-y-1 pl-5">
              {result.fail_reasons.map((reason) => <li key={reason}>{reason}</li>)}
            </ul>
          ) : (
            <p className="mt-1">None.</p>
          )}
        </div>
      </div>

      <div className="mt-4 overflow-x-auto">
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-black/50">
          Sanitized preview (maximum {result.preview_limit} rows)
        </p>
        {result.preview.length === 0 ? (
          <p className="text-black/55">No preview rows returned.</p>
        ) : (
          <table className="min-w-full text-left text-xs">
            <thead>
              <tr className="border-b border-black/10 text-black/55">
                {previewColumns.map((column) => <th key={column} className="whitespace-nowrap px-2 py-2">{column}</th>)}
              </tr>
            </thead>
            <tbody>
              {result.preview.map((row, index) => (
                <tr key={index} className="border-b border-black/5">
                  {previewColumns.map((column) => (
                    <td key={column} className="max-w-64 truncate px-2 py-2" title={String(row[column] ?? "")}>
                      {String(row[column] ?? "-")}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
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
