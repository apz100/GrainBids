export function formatNotificationValue(value) {
  if (typeof value !== "string") {
    return "-";
  }
  const trimmed = value.trim();
  return trimmed || "-";
}

export function formatNotificationTimestamp(value) {
  if (!value) {
    return "-";
  }
  return new Date(value).toLocaleString();
}

export function notificationStatusClass(status) {
  switch ((status || "").trim().toLowerCase()) {
    case "sent":
      return "border-emerald-700/20 bg-emerald-100 text-emerald-900";
    case "skipped":
      return "border-amber-700/20 bg-amber-100 text-amber-900";
    case "failed":
      return "border-rose-700/20 bg-rose-100 text-rose-900";
    default:
      return "border-black/15 bg-white text-black/75";
  }
}
