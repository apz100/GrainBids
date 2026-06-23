import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const providerSource = readFileSync(join(__dirname, "../app/_components/auth-session-provider.tsx"), "utf8");
const apiSource = readFileSync(join(__dirname, "../lib/api.ts"), "utf8");
const routeSource = readFileSync(join(__dirname, "../app/api/auth/session/route.ts"), "utf8");

assert.match(providerSource, /fetch\("\/api\/auth\/session"/);
assert.doesNotMatch(providerSource, /NEXT_PUBLIC_AUTH_USER_ID/);
assert.doesNotMatch(providerSource, /buildApiRequestInit/);

assert.match(apiSource, /NEXT_PUBLIC_ENABLE_LOCAL_HEADER_AUTH/);
assert.match(apiSource, /if \(!LOCAL_HEADER_AUTH_ENABLED\) \{\s+return headers;\s+\}/);

assert.match(routeSource, /AUTH_SESSION_COOKIE_NAME/);
assert.match(routeSource, /AUTH_TRUST_PROXY_HEADERS/);
assert.match(routeSource, /LOCAL_HEADER_AUTH_ENABLED/);
