export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export function apiHeaders(): HeadersInit {
  const headers: Record<string, string> = {};
  const orgId = process.env.NEXT_PUBLIC_ORG_ID;
  const userRole = process.env.NEXT_PUBLIC_USER_ROLE || "admin";
  const userEmail = process.env.NEXT_PUBLIC_USER_EMAIL || "";

  if (orgId) {
    headers["X-Org-Id"] = orgId;
  }
  if (userRole) {
    headers["X-User-Role"] = userRole;
  }
  if (userEmail) {
    headers["X-User-Email"] = userEmail;
  }
  return headers;
}

export async function fetchApiJsonServer<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      cache: "no-store",
      headers: apiHeaders(),
    });
    if (!res.ok) {
      return null;
    }
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export async function apiFetch(path: string, init: RequestInit = {}) {
  const headers = { ...apiHeaders(), ...(init.headers || {}) };
  return fetch(`${API_BASE}${path}`, { ...init, headers, cache: "no-store" });
}

