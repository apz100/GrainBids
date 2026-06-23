import { cookies, headers } from "next/headers";
import { NextResponse } from "next/server";

import { API_BASE, LOCAL_HEADER_AUTH_ENABLED } from "@/lib/api";

export const dynamic = "force-dynamic";

const DEFAULT_AUTH_USER_COOKIE = "gb_auth_user_id";
const DEFAULT_ORG_COOKIE = "gb_org_id";
const DEFAULT_AUTH_USER_HEADER = "x-auth-user-id";
const DEFAULT_ORG_HEADER = "x-org-id";

export async function GET() {
  const bridgeHeaders = buildSessionBridgeHeaders();
  if (!bridgeHeaders["X-Auth-User-Id"]) {
    return NextResponse.json({ detail: "Authenticated session was not found" }, { status: 401 });
  }
  if (!bridgeHeaders["X-Org-Id"]) {
    return NextResponse.json({ detail: "Organization session was not found" }, { status: 401 });
  }

  const response = await fetch(`${API_BASE}/api/settings/session`, {
    cache: "no-store",
    headers: bridgeHeaders,
  });
  const body = await response.text();

  return new NextResponse(body, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("content-type") || "application/json",
    },
  });
}

function buildSessionBridgeHeaders(): Record<string, string> {
  if (LOCAL_HEADER_AUTH_ENABLED) {
    return compactHeaders({
      "X-Org-Id": process.env.NEXT_PUBLIC_ORG_ID,
      "X-Auth-User-Id": process.env.NEXT_PUBLIC_AUTH_USER_ID,
      "X-User-Role": process.env.NEXT_PUBLIC_USER_ROLE,
      "X-User-Email": process.env.NEXT_PUBLIC_USER_EMAIL,
    });
  }

  const cookieStore = cookies();
  const requestHeaders = headers();
  const trustProxyHeaders = process.env.AUTH_TRUST_PROXY_HEADERS === "true";
  const authUserHeader = (process.env.AUTH_TRUSTED_USER_HEADER || DEFAULT_AUTH_USER_HEADER).toLowerCase();
  const orgHeader = (process.env.AUTH_TRUSTED_ORG_HEADER || DEFAULT_ORG_HEADER).toLowerCase();

  return compactHeaders({
    "X-Org-Id":
      process.env.AUTH_ORG_ID ||
      cookieStore.get(process.env.AUTH_ORG_COOKIE_NAME || DEFAULT_ORG_COOKIE)?.value ||
      (trustProxyHeaders ? requestHeaders.get(orgHeader) : null),
    "X-Auth-User-Id":
      cookieStore.get(process.env.AUTH_SESSION_COOKIE_NAME || DEFAULT_AUTH_USER_COOKIE)?.value ||
      (trustProxyHeaders ? requestHeaders.get(authUserHeader) : null),
  });
}

function compactHeaders(headersToCompact: Record<string, string | null | undefined>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(headersToCompact)
      .map(([key, value]) => [key, (value || "").trim()])
      .filter((entry): entry is [string, string] => Boolean(entry[1])),
  );
}
