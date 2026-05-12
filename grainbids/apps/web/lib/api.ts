export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
export const ORG_ID = (process.env.NEXT_PUBLIC_ORG_ID || "").trim();
export const USER_ROLE = (process.env.NEXT_PUBLIC_USER_ROLE || "member").trim().toLowerCase();
export const USER_EMAIL = (process.env.NEXT_PUBLIC_USER_EMAIL || "").trim();

export function getApiConfigError(options?: { requireOrg?: boolean }): string | null {
  const requireOrg = options?.requireOrg ?? true;
  if (!API_BASE.trim()) {
    return "Missing NEXT_PUBLIC_API_URL in web environment.";
  }
  if (requireOrg && !ORG_ID) {
    return "Missing NEXT_PUBLIC_ORG_ID in web environment.";
  }
  return null;
}

export function buildApiHeaders(): HeadersInit {
  const headers: Record<string, string> = {};
  if (ORG_ID) headers["X-Org-Id"] = ORG_ID;
  if (USER_ROLE) headers["X-User-Role"] = USER_ROLE;
  if (USER_EMAIL) headers["X-User-Email"] = USER_EMAIL;
  return headers;
}

export function isAdminRole(role = USER_ROLE): boolean {
  return role === "admin" || role === "owner";
}
