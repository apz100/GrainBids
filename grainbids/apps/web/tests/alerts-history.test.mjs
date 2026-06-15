import assert from "node:assert/strict";

import {
  formatNotificationTimestamp,
  formatNotificationValue,
  notificationStatusClass,
} from "../lib/alerts-history.mjs";

assert.equal(formatNotificationValue(null), "-");
assert.equal(formatNotificationValue("   "), "-");
assert.equal(formatNotificationTimestamp(""), "-");
assert.match(notificationStatusClass("sent"), /emerald/);
assert.match(notificationStatusClass("skipped"), /amber/);
assert.match(notificationStatusClass("failed"), /rose/);
assert.equal(
  formatNotificationTimestamp("2026-06-15T15:30:00Z"),
  new Date("2026-06-15T15:30:00Z").toLocaleString(),
);
