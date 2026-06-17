"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { useAuthSession } from "../_components/auth-session-provider";
import { API_BASE, buildApiRequestInit, getApiConfigError, isAdminRole } from "@/lib/api";

type OrgData = {
  id: string;
  name: string;
  plan: string;
  created_at: string | null;
};

type UserRow = {
  id: string;
  email: string;
  role: string;
  is_active: boolean;
  company_name: string | null;
  auth_user_id: string | null;
  created_at: string | null;
};

export default function SettingsPage() {
  const { session, status } = useAuthSession();
  const admin = isAdminRole(session?.user_role);

  const [org, setOrg] = useState<OrgData | null>(null);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const configError = getApiConfigError({ requireOrg: false });

  const fetchOrg = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/settings/org`, buildApiRequestInit());
      if (res.ok) {
        const data: OrgData = await res.json();
        setOrg(data);
        setNameDraft(data.name);
      }
    } catch {
      /* ignore */
    }
  }, []);

  const fetchUsers = useCallback(async () => {
    if (!admin) return;
    try {
      const res = await fetch(`${API_BASE}/api/settings/users`, buildApiRequestInit());
      if (res.ok) {
        const data = await res.json();
        setUsers(data.rows ?? []);
      }
    } catch {
      /* ignore */
    }
  }, [admin]);

  useEffect(() => {
    if (status !== "loading") {
      fetchOrg();
      if (admin) fetchUsers();
    }
  }, [status, admin, fetchOrg, fetchUsers]);

  if (status === "loading") {
    return (
      <main className="mx-auto max-w-4xl px-6 py-12">
        <div className="rounded-xl border border-black/10 bg-white/80 p-6 shadow-sm">
          <p className="text-sm text-black/70">Loading session...</p>
        </div>
      </main>
    );
  }

  if (!session) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-12">
        <div className="rounded-xl border border-black/10 bg-white/80 p-6 shadow-sm">
          <p className="text-xs uppercase tracking-[0.16em] text-black/50">Settings</p>
          <h1 className="mt-2 font-[family-name:var(--font-serif)] text-3xl">Sign in required</h1>
          <p className="mt-3 text-sm text-black/70">Please sign in to access settings.</p>
        </div>
      </main>
    );
  }

  async function handleSaveName() {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch(`${API_BASE}/api/settings/org`, {
        ...buildApiRequestInit({ method: "PATCH" }),
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: nameDraft }),
      });
      if (res.ok) {
        const data: OrgData = await res.json();
        setOrg(data);
        setEditingName(false);
        setSuccess("Organization name updated");
      } else {
        setError("Failed to update organization name");
      }
    } catch {
      setError("Network error updating organization name");
    } finally {
      setSaving(false);
    }
  }

  async function handleRoleChange(userId: string, newRole: string) {
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch(`${API_BASE}/api/settings/users/${userId}`, {
        ...buildApiRequestInit({ method: "PATCH" }),
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: newRole }),
      });
      if (res.ok) {
        setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, role: newRole } : u)));
        setSuccess("User role updated");
      } else {
        setError("Failed to update user role");
      }
    } catch {
      setError("Network error updating user role");
    }
  }

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <p className="text-xs uppercase tracking-[0.16em] text-black/50">GrainBids / Settings</p>
      <h1 className="mt-1 font-[family-name:var(--font-serif)] text-4xl leading-tight">Settings</h1>

      {error && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>
      )}
      {success && (
        <div className="mt-4 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-700">{success}</div>
      )}

      {/* Organization */}
      <section className="mt-8 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Organization</h2>
        {org ? (
          <div className="mt-4 space-y-3">
            <div>
              <span className="text-xs uppercase tracking-[0.12em] text-black/50">Name</span>
              {editingName && admin ? (
                <div className="mt-1 flex gap-2">
                  <input
                    type="text"
                    value={nameDraft}
                    onChange={(e) => setNameDraft(e.target.value)}
                    className="flex-1 rounded-md border border-black/20 bg-white px-3 py-1.5 text-sm"
                  />
                  <button
                    onClick={handleSaveName}
                    disabled={saving}
                    className="rounded-md bg-black/90 px-3 py-1.5 text-sm text-white hover:bg-black/70 disabled:opacity-50"
                  >
                    {saving ? "Saving..." : "Save"}
                  </button>
                  <button
                    onClick={() => { setEditingName(false); setNameDraft(org.name); }}
                    className="rounded-md border border-black/20 bg-white px-3 py-1.5 text-sm hover:bg-black/5"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <p className="text-sm font-medium">{org.name}</p>
                  {admin && (
                    <button
                      onClick={() => setEditingName(true)}
                      className="text-xs text-black/50 hover:text-black/80"
                    >
                      Edit
                    </button>
                  )}
                </div>
              )}
            </div>
            <div>
              <span className="text-xs uppercase tracking-[0.12em] text-black/50">Plan</span>
              <p className="text-sm font-medium capitalize">{org.plan}</p>
            </div>
            <div>
              <span className="text-xs uppercase tracking-[0.12em] text-black/50">Created</span>
              <p className="text-sm">{org.created_at ? new Date(org.created_at).toLocaleDateString() : "—"}</p>
            </div>
          </div>
        ) : (
          <p className="mt-2 text-sm text-black/50">Loading organization info...</p>
        )}
      </section>

      {/* Users */}
      {admin && (
        <section className="mt-6 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
          <h2 className="text-lg font-semibold">Users</h2>
          {users.length === 0 ? (
            <p className="mt-2 text-sm text-black/50">No users found.</p>
          ) : (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-black/10 text-left text-xs uppercase tracking-[0.12em] text-black/50">
                    <th className="pb-2 pr-4 font-normal">Email</th>
                    <th className="pb-2 pr-4 font-normal">Role</th>
                    <th className="pb-2 pr-4 font-normal">Status</th>
                    <th className="pb-2 font-normal">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id} className="border-b border-black/5">
                      <td className="py-2 pr-4">{u.email}</td>
                      <td className="py-2 pr-4 capitalize">{u.role}</td>
                      <td className="py-2 pr-4">
                        <span className={`inline-block rounded-full px-2 py-0.5 text-xs ${u.is_active ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                          {u.is_active ? "Active" : "Inactive"}
                        </span>
                      </td>
                      <td className="py-2">
                        {u.id !== session?.user_id && (
                          <select
                            value={u.role}
                            onChange={(e) => handleRoleChange(u.id, e.target.value)}
                            className="rounded-md border border-black/20 bg-white px-2 py-1 text-xs"
                          >
                            <option value="member">Member</option>
                            <option value="admin">Admin</option>
                            <option value="owner">Owner</option>
                          </select>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* Sources shortcut */}
      <section className="mt-6 rounded-lg border border-black/10 bg-white/65 p-5 backdrop-blur">
        <h2 className="text-lg font-semibold">Source Management</h2>
        <p className="mt-2 text-sm text-black/65">Manage source mappings, priority controls, and canonical coverage.</p>
        <Link href="/sources" className="mt-4 inline-flex rounded-md border border-black/20 bg-white/80 px-3 py-2 text-sm hover:border-black/40">
          Manage sources
        </Link>
      </section>
    </main>
  );
}
