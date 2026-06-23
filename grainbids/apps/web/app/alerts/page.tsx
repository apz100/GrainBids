"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { API_BASE, buildApiHeaders, isAdminRole } from "@/lib/api";
import {
  formatNotificationTimestamp,
  formatNotificationValue,
  notificationStatusClass,
} from "@/lib/alerts-history.mjs";
import { useAuthSession } from "../_components/auth-session-provider";

type AlertRuleRow = {
  id: string;
  rule_type: string;
  comparison_operator: string;
  threshold_value: number;
  location: string | null;
  saved_search_id: string | null;
  delivery_months: string[];
  notification_channels: { channel: string; recipient: string }[];
  is_active: boolean;
  last_triggered_at: string | null;
  open_alert_count: number;
};

type SavedSearchRow = {
  id: string;
  name: string;
  delivery_months: string[];
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

type NotificationLogRow = {
  id: string;
  alert_id: string | null;
  channel: string;
  recipient: string | null;
  status: string;
  provider_message_id: string | null;
  error_message: string | null;
  created_at: string | null;
};

export default function AlertsPage() {
  const { session } = useAuthSession();
  const headers = buildApiHeaders();
  const canManageAlerts = isAdminRole(session?.user_role);
  const [rules, setRules] = useState<AlertRuleRow[]>([]);
  const [savedSearches, setSavedSearches] = useState<SavedSearchRow[]>([]);
  const [alerts, setAlerts] = useState<RecentAlert[]>([]);
  const [notificationLogs, setNotificationLogs] = useState<NotificationLogRow[]>([]);
  const [openOnly, setOpenOnly] = useState(true);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [activeAlertId, setActiveAlertId] = useState("");
  const [activeRuleId, setActiveRuleId] = useState("");
  const [editingChannels, setEditingChannels] = useState<Record<string, { channel: string; recipient: string }[]>>({});
  const [statusFilter, setStatusFilter] = useState<"all" | "new" | "open" | "pending" | "acknowledged" | "resolved">("all");
  const [ruleFilter, setRuleFilter] = useState<string>("all");
  const [searchText, setSearchText] = useState("");
  const [newRuleType, setNewRuleType] = useState("cash_price_bu");
  const [newRuleOperator, setNewRuleOperator] = useState(">=");
  const [newRuleThreshold, setNewRuleThreshold] = useState("6.5");
  const [newRuleLocation, setNewRuleLocation] = useState("");
  const [newRuleSavedSearchId, setNewRuleSavedSearchId] = useState("");
  const [newRuleDeliveryMonths, setNewRuleDeliveryMonths] = useState("");

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const openOnlyQuery = openOnly ? "&open_only=true" : "";
      const [rulesRes, alertsRes, logsRes] = await Promise.all([
        fetch(`${API_BASE}/api/alerts/rules`, { cache: "no-store", headers }),
        fetch(`${API_BASE}/api/alerts/recent?limit=25${openOnlyQuery}`, { cache: "no-store", headers }),
        fetch(`${API_BASE}/api/alerts/notification-logs?limit=25`, { cache: "no-store", headers }),
      ]);
      const savedSearchesRes = await fetch(`${API_BASE}/api/saved-searches`, { cache: "no-store", headers });
      const rulesJson = rulesRes.ok ? await rulesRes.json() : { rows: [] };
      const alertsJson = alertsRes.ok ? await alertsRes.json() : { rows: [] };
      const logsJson = logsRes.ok ? await logsRes.json() : { rows: [] };
      const savedSearchesJson = savedSearchesRes.ok ? await savedSearchesRes.json() : { rows: [] };
      setRules(rulesJson.rows || []);
      setAlerts(alertsJson.rows || []);
      setNotificationLogs(logsJson.rows || []);
      setSavedSearches(savedSearchesJson.rows || []);
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
      const res = await fetch(`${API_BASE}/api/alerts/${alertId}/status?status=${status}`, { method: "PATCH", headers });
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

  async function createAlertRule() {
    setError("");
    setMessage("");
    const threshold = Number(newRuleThreshold);
    if (!Number.isFinite(threshold)) {
      setError("Threshold must be a number.");
      return;
    }
    const params = new URLSearchParams({
      rule_type: newRuleType,
      threshold_value: String(threshold),
      comparison_operator: newRuleOperator,
    });
    if (newRuleLocation.trim()) {
      params.set("location", newRuleLocation.trim());
    }
    if (newRuleSavedSearchId) {
      params.set("saved_search_id", newRuleSavedSearchId);
    }
    if (newRuleDeliveryMonths.trim()) {
      params.set("delivery_months", newRuleDeliveryMonths.trim());
    }

    try {
      const res = await fetch(`${API_BASE}/api/alerts/rules?${params.toString()}`, { method: "POST", headers });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(typeof json.detail === "string" ? json.detail : "Failed to create alert rule");
      }
      setMessage("Alert rule created.");
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function updateNotificationChannels(ruleId: string) {
    const channels = editingChannels[ruleId] || [];
    setError("");
    setMessage("");
    try {
      const res = await fetch(`${API_BASE}/api/alerts/rules/${ruleId}/channels`, {
        method: "PATCH",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ notification_channels: channels }),
      });
      if (res.ok) {
        setMessage("Notification channels updated.");
        setEditingChannels((prev) => { const next = { ...prev }; delete next[ruleId]; return next; });
        await loadData();
      } else {
        setError("Failed to update notification channels");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  function addChannel(ruleId: string) {
    setEditingChannels((prev) => ({
      ...prev,
      [ruleId]: [...(prev[ruleId] || []), { channel: "email", recipient: "" }],
    }));
  }

  function updateChannel(ruleId: string, index: number, field: string, value: string) {
    setEditingChannels((prev) => {
      const channels = [...(prev[ruleId] || [])];
      channels[index] = { ...channels[index], [field]: value };
      return { ...prev, [ruleId]: channels };
    });
  }

  function removeChannel(ruleId: string, index: number) {
    setEditingChannels((prev) => {
      const channels = (prev[ruleId] || []).filter((_, i) => i !== index);
      return { ...prev, [ruleId]: channels };
    });
  }

  async function deleteAlertRule(ruleId: string) {
    setActiveRuleId(ruleId);
    setError("");
    setMessage("");
    try {
      const res = await fetch(`${API_BASE}/api/alerts/rules/${ruleId}`, { method: "DELETE", headers });
      const json = await res.json();
      if (!res.ok) {
        throw new Error(typeof json.detail === "string" ? json.detail : "Failed to delete alert rule");
      }
      setMessage(`Deleted rule ${json.deleted}.`);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setActiveRuleId("");
    }
  }

  useEffect(() => {
    loadData().catch((err) => setError(String(err)));
  }, [openOnly]);

  useEffect(() => {
    if (!newRuleSavedSearchId) {
      return;
    }
    const selected = savedSearches.find((row) => row.id === newRuleSavedSearchId);
    if (selected && selected.delivery_months.length > 0) {
      setNewRuleDeliveryMonths(selected.delivery_months.join(", "));
    }
  }, [newRuleSavedSearchId, savedSearches]);

  const visibleAlerts = alerts.filter((alert) => {
    if (statusFilter !== "all" && alert.status !== statusFilter) return false;
    if (ruleFilter !== "all" && alert.rule_type !== ruleFilter) return false;
    const text = searchText.trim().toLowerCase();
    if (!text) return true;
    return (
      (alert.location || "").toLowerCase().includes(text)
      || (alert.message || "").toLowerCase().includes(text)
      || (alert.rule_type || "").toLowerCase().includes(text)
    );
  });

  const uniqueRuleTypes = Array.from(new Set(alerts.map((a) => a.rule_type).filter(Boolean))).sort((a, b) =>
    a.localeCompare(b),
  );
  const savedSearchById = new Map(savedSearches.map((row) => [row.id, row.name]));

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <p className="text-xs uppercase tracking-[0.16em] text-black/50">GrainBids / Alerts</p>
      <h1 className="mt-1 font-[family-name:var(--font-serif)] text-4xl leading-tight">Alerts</h1>

      {message ? <p className="mt-4 text-sm text-emerald-700">{message}</p> : null}
      {error ? <p className="mt-4 text-sm text-red-700">{error}</p> : null}

      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Create alert rule</h2>
        <p className="mt-2 text-sm text-black/65">Create threshold rules and optionally scope them to a saved search and delivery months.</p>
        <div className="mt-4 grid gap-2 md:grid-cols-3">
          <select value={newRuleType} onChange={(event) => setNewRuleType(event.target.value)} className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm">
            <option value="cash_price_bu">Cash/Bu</option>
            <option value="basis">Basis</option>
            <option value="basis_change">Basis Change</option>
            <option value="cash_price_bu_change">Cash/Bu Change</option>
          </select>
          <select value={newRuleOperator} onChange={(event) => setNewRuleOperator(event.target.value)} className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm">
            <option value=">=">{">="}</option>
            <option value="<=">{"<="}</option>
            <option value=">">{">"}</option>
            <option value="<">{"<"}</option>
            <option value="=">{"="}</option>
          </select>
          <input
            value={newRuleThreshold}
            onChange={(event) => setNewRuleThreshold(event.target.value)}
            placeholder="Threshold"
            className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
          />
          <input
            value={newRuleLocation}
            onChange={(event) => setNewRuleLocation(event.target.value)}
            placeholder="Optional location"
            className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
          />
          <select
            value={newRuleSavedSearchId}
            onChange={(event) => setNewRuleSavedSearchId(event.target.value)}
            className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
          >
            <option value="">All bids (no saved search)</option>
            {savedSearches.map((row) => (
              <option key={row.id} value={row.id}>{row.name}</option>
            ))}
          </select>
          <input
            value={newRuleDeliveryMonths}
            onChange={(event) => setNewRuleDeliveryMonths(event.target.value)}
            placeholder="Delivery months (comma separated)"
            className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
          />
        </div>
        <div className="mt-3">
          <button onClick={() => createAlertRule()} className="rounded-md border border-black/20 bg-black px-3 py-2 text-sm text-white">
            Create rule
          </button>
        </div>
      </section>

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
                <th className="px-2 py-2">Saved Search</th>
                <th className="px-2 py-2">Months</th>
                <th className="px-2 py-2">Channels</th>
                <th className="px-2 py-2">Open Alerts</th>
                <th className="px-2 py-2">Last Trigger</th>
                <th className="px-2 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rules.length === 0 ? (
                <tr>
                  <td className="px-2 py-4 text-black/55" colSpan={9}>
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
                    <td className="px-2 py-2">{row.saved_search_id ? (savedSearchById.get(row.saved_search_id) || "Unknown") : "All bids"}</td>
                    <td className="px-2 py-2">{row.delivery_months?.length ? row.delivery_months.join(", ") : "-"}</td>
                    <td className="px-2 py-2">
                      {editingChannels[row.id] ? (
                        <div className="space-y-1">
                          {editingChannels[row.id].map((ch, ci) => (
                            <div key={ci} className="flex items-center gap-1 text-xs">
                              <select
                                value={ch.channel}
                                onChange={(e) => updateChannel(row.id, ci, "channel", e.target.value)}
                                className="rounded border border-black/15 bg-white px-1 py-0.5 text-xs"
                              >
                                <option value="email">Email</option>
                                <option value="webhook">Webhook</option>
                              </select>
                              <input
                                type="text"
                                value={ch.recipient}
                                onChange={(e) => updateChannel(row.id, ci, "recipient", e.target.value)}
                                placeholder={ch.channel === "webhook" ? "https://..." : "email@..."}
                                className="flex-1 rounded border border-black/15 bg-white px-1 py-0.5 text-xs"
                              />
                              <button onClick={() => removeChannel(row.id, ci)} className="text-red-600 hover:text-red-800">&times;</button>
                            </div>
                          ))}
                          <div className="flex gap-1">
                            <button onClick={() => addChannel(row.id)} className="rounded border border-black/15 bg-white px-1.5 py-0.5 text-xs hover:bg-black/5">+ Add</button>
                            <button onClick={() => updateNotificationChannels(row.id)} className="rounded bg-black/80 px-1.5 py-0.5 text-xs text-white hover:bg-black/60">Save</button>
                            <button onClick={() => setEditingChannels((prev) => { const next = { ...prev }; delete next[row.id]; return next; })} className="rounded border border-black/15 bg-white px-1.5 py-0.5 text-xs hover:bg-black/5">Cancel</button>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1">
                          <span className="text-xs">{row.notification_channels?.length ? row.notification_channels.map((c) => `${c.channel}:${c.recipient}`).join(", ") : "Default"}</span>
                          {canManageAlerts && (
                            <button
                              onClick={() => setEditingChannels((prev) => ({ ...prev, [row.id]: row.notification_channels?.length ? [...row.notification_channels] : [{ channel: "email", recipient: "" }] }))}
                              className="text-xs text-black/50 hover:text-black/80"
                            >
                              Edit
                            </button>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="px-2 py-2">{row.open_alert_count}</td>
                    <td className="px-2 py-2">{row.last_triggered_at ? new Date(row.last_triggered_at).toLocaleString() : "-"}</td>
                    <td className="px-2 py-2">
                      <button
                        disabled={activeRuleId === row.id}
                        onClick={() => deleteAlertRule(row.id)}
                        className="rounded-md border border-black/20 bg-white px-2 py-1 text-xs disabled:opacity-50"
                      >
                        Delete
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
        <h2 className="text-lg font-semibold">Alert events</h2>
        <div className="mt-3 grid gap-2 md:grid-cols-4">
          <label className="inline-flex items-center gap-2 text-xs text-black/70">
            <input
              type="checkbox"
              checked={openOnly}
              onChange={(event) => setOpenOnly(event.target.checked)}
              className="h-4 w-4 rounded border border-black/20"
            />
            Show open alerts only
          </label>
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}
            className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
          >
            <option value="all">All statuses</option>
            <option value="new">new</option>
            <option value="open">open</option>
            <option value="pending">pending</option>
            <option value="acknowledged">acknowledged</option>
            <option value="resolved">resolved</option>
          </select>
          <select
            value={ruleFilter}
            onChange={(event) => setRuleFilter(event.target.value)}
            className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
          >
            <option value="all">All rule types</option>
            {uniqueRuleTypes.map((ruleType) => (
              <option key={ruleType} value={ruleType}>
                {ruleType}
              </option>
            ))}
          </select>
          <input
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
            placeholder="Search location/message"
            className="rounded-md border border-black/15 bg-white px-3 py-2 text-sm"
          />
        </div>
        <p className="mt-2 text-xs text-black/55">Showing {visibleAlerts.length} of {alerts.length} alerts.</p>
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
              {visibleAlerts.length === 0 ? (
                <tr>
                  <td className="px-2 py-4 text-black/55" colSpan={5}>
                    No alerts found.
                  </td>
                </tr>
              ) : (
                visibleAlerts.map((alert) => (
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

      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Notification history</h2>
            <p className="mt-2 text-sm text-black/65">
              Delivery attempts from the notifier, including sent, skipped, and failed records.
            </p>
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
                <th className="px-2 py-2">Timestamp</th>
                <th className="px-2 py-2">Status</th>
                <th className="px-2 py-2">Channel</th>
                <th className="px-2 py-2">Recipient</th>
                <th className="px-2 py-2">Provider Message ID</th>
                <th className="px-2 py-2">Error</th>
              </tr>
            </thead>
            <tbody>
              {notificationLogs.length === 0 ? (
                <tr>
                  <td className="px-2 py-4 text-black/55" colSpan={6}>
                    No notification history yet.
                  </td>
                </tr>
              ) : (
                notificationLogs.map((row) => (
                  <tr key={row.id} className="border-b border-black/5">
                    <td className="px-2 py-2">{formatNotificationTimestamp(row.created_at)}</td>
                    <td className="px-2 py-2">
                      <span className={`inline-flex rounded-full border px-2 py-1 text-xs ${notificationStatusClass(row.status)}`}>
                        {formatNotificationValue(row.status)}
                      </span>
                    </td>
                    <td className="px-2 py-2">{formatNotificationValue(row.channel)}</td>
                    <td className="px-2 py-2">{formatNotificationValue(row.recipient)}</td>
                    <td className="px-2 py-2 text-xs">{formatNotificationValue(row.provider_message_id)}</td>
                    <td className="px-2 py-2 text-xs text-black/70">{formatNotificationValue(row.error_message)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <Link href="/bids" className="mt-4 inline-flex rounded-md border border-black/20 bg-white/80 px-3 py-2 text-sm hover:border-black/40">
        Back to market
      </Link>
    </main>
  );
}
