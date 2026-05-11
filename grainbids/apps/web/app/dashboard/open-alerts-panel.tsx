"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "../lib/api";

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

export default function OpenAlertsPanel() {
  const [alerts, setAlerts] = useState<RecentAlert[]>([]);
  const [openOnly, setOpenOnly] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [activeAlertId, setActiveAlertId] = useState("");

  async function loadAlerts() {
    setLoading(true);
    setError("");
    try {
      const openOnlyQuery = openOnly ? "&open_only=true" : "";
      const res = await apiFetch(`/api/alerts/recent?limit=8${openOnlyQuery}`);
      const json = await res.json();
      if (!res.ok) {
        throw new Error(typeof json.detail === "string" ? json.detail : "Failed to load alerts");
      }
      setAlerts(json.rows || []);
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
      const res = await apiFetch(`/api/alerts/${alertId}/status?status=${status}`, { method: "PATCH" });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(typeof json.detail === "string" ? json.detail : "Failed to update alert");
      }
      setMessage(`Alert updated to ${json.status}.`);
      await loadAlerts();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setActiveAlertId("");
    }
  }

  useEffect(() => {
    loadAlerts().catch((err) => setError(String(err)));
  }, [openOnly]);

  return (
    <section className="mt-8 rounded-2xl border border-black/10 bg-white/65 p-5 backdrop-blur">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Open Alerts</h2>
          <p className="mt-1 text-xs text-black/55">Acknowledge or resolve alerts directly from the dashboard.</p>
        </div>
        <button
          disabled={loading}
          onClick={() => loadAlerts()}
          className="rounded-md border border-black/20 bg-white px-3 py-2 text-xs disabled:opacity-50"
        >
          Refresh
        </button>
      </div>
      <label className="mt-3 inline-flex items-center gap-2 text-xs text-black/70">
        <input
          type="checkbox"
          checked={openOnly}
          onChange={(event) => setOpenOnly(event.target.checked)}
          className="h-4 w-4 rounded border border-black/20"
        />
        Show open alerts only
      </label>

      {message ? <p className="mt-3 text-sm text-emerald-700">{message}</p> : null}
      {error ? <p className="mt-3 text-sm text-red-700">{error}</p> : null}

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
                  No alerts.
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
    </section>
  );
}
