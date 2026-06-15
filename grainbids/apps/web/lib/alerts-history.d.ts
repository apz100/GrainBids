declare module "@/lib/alerts-history.mjs" {
  export function formatNotificationValue(value: unknown): string;
  export function formatNotificationTimestamp(value: string | null | undefined): string;
  export function notificationStatusClass(status: string | null | undefined): string;
}
