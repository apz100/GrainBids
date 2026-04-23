"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type AlertRuleRow = {
  id: string;
  rule_type: string;
  comparison_operator: string;
  threshold_value: number;
  location: string | null;
  is_active: boolean;
  last_triggered_at: string | null;
  open_alert_count: number;
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

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export default function AlertsPage() {
  const [rules, setRules] = useState<AlertRuleRow[]>([]);
  const [alerts, setAlerts] = useState<RecentAlert[]>([]);
  const [openOnly, setOpenOnly] = useState(true);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [activeAlertId, setActiveAlertId] = useState("");

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const openOnlyQuery = openOnly ? "&open_only=true" : "";
      const [rulesRes, alertsRes] = await Promise.all([
        fetch(`${API_BASE}/api/alerts/rules`, { cache: "no-store" }),
        fetch(`${API_BASE}/api/alerts/recent?limit=25${openOnlyQuery}`, { cache: "no-store" }),
      ]);
      const rulesJson = rulesRes.ok ? await rulesRes.json() : { rows: [] };
      const alertsJson = alertsRes.ok ? await alertsRes.json() : { rows: [] };
      setRules(rulesJson.rows || []);
      setAlerts(alertsJson.rows || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function updateAlertStatus(alertId: string, status: "acknowledged" | "resolved") {
    setActiveAlertId(alertId);
    setMessage("");
    setError("");
    try {
      const res = await fetch(`${API_BASE}/api/alerts/${alertId}/status?status=${status}`, { method: "PATCH" });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(typeof json.detail === "string" ? json.detail : "Failed to update alert");
      }
      setMessage(`Alert updated to ${json.status}.`);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setActiveAlertId("");
    }
  }

  useEffect(() => {
    loadData().catch((err) => setError(String(err)));
  }, [openOnly]);

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <p className="text-xs uppercase tracking-[0.16em] text-black/50">GrainBids / Alerts</p>
      <h1 className="mt-1 font-[family-name:var(--font-serif)] text-4xl leading-tight">Alerts</h1>

      {message ? <p className="mt-4 text-sm text-emerald-700">{message}</p> : null}
      {error ? <p className="mt-4 text-sm text-red-700">{error}</p> : null}

      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Alert rules</h2>
            <p className="mt-2 text-sm text-black/65">Configured thresholds and their current open-alert counts.</p>
          </div>
          <button
            disabled={loading}
            onClick={() => loadData()}
            className="rounded-md border border-black/20 bg-white px-3 py-2 text-xs disabled:opacity-50"
          >
            Refresh
          </button>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-black/10 text-xs uppercase tracking-wide text-black/50">
                <th className="px-2 py-2">Type</th>
                <th className="px-2 py-2">Operator</th>
                <th className="px-2 py-2">Threshold</th>
                <th className="px-2 py-2">Location</th>
                <th className="px-2 py-2">Open Alerts</th>
                <th className="px-2 py-2">Last Trigger</th>
              </tr>
            </thead>
            <tbody>
              {rules.length === 0 ? (
                <tr>
                  <td className="px-2 py-4 text-black/55" colSpan={6}>
                    No alert rules yet.
                  </td>
                </tr>
              ) : (
                rules.map((row) => (
                  <tr key={row.id} className="border-b border-black/5">
                    <td className="px-2 py-2">{row.rule_type}</td>
                    <td className="px-2 py-2">{row.comparison_operator}</td>
                    <td className="px-2 py-2">{row.threshold_value}</td>
                    <td className="px-2 py-2">{row.location || "All"}</td>
                    <td className="px-2 py-2">{row.open_alert_count}</td>
                    <td className="px-2 py-2">{row.last_triggered_at ? new Date(row.last_triggered_at).toLocaleString() : "-"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Alert events</h2>
        <label className="mt-3 inline-flex items-center gap-2 text-xs text-black/70">
          <input
            type="checkbox"
            checked={openOnly}
            onChange={(event) => setOpenOnly(event.target.checked)}
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
                    No alerts found.
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
                          disabled={activeAlertId === alert.id || alert.status === "acknowledged" || alert.status === "resolved"}
                          onClick={() => updateAlertStatus(alert.id, "acknowledged")}
                          className="rounded-md border border-black/20 bg-white px-2 py-1 text-xs disabled:opacity-50"
                        >
                          Acknowledge
                        </button>
                        <button
                          disabled={activeAlertId === alert.id || alert.status === "resolved"}
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
        <Link href="/dashboard" className="mt-4 inline-flex rounded-md border border-black/20 bg-white/80 px-3 py-2 text-sm hover:border-black/40">
          Back to dashboard
        </Link>
      </section>
    </main>
  );
}
