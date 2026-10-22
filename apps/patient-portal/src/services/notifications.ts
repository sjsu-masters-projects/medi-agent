import { api } from "@/services/api";
import type { Locale } from "@/types";
import type { NotificationPage, NotificationSummary } from "@/types/notifications";

const root = "/api/v1/notification-centre";
export const notifications = {
  list(token: string, locale: Locale, unread = false, cursor?: string, signal?: AbortSignal) {
    const query = new URLSearchParams({ locale, unread: String(unread), limit: "50" });
    if (cursor) query.set("cursor", cursor);
    return api.get<NotificationPage>(`${root}?${query}`, { token, signal });
  },
  summary(token: string, signal?: AbortSignal) {
    return api.get<NotificationSummary>(`${root}/summary`, { token, signal });
  },
  read(token: string, id: string) {
    return api.put<void>(`${root}/${encodeURIComponent(id)}/read`, undefined, { token });
  },
  /** Marks a displayed page read; items no longer available are skipped, not fatal. */
  async readThrough(token: string, readThrough: string): Promise<{ skipped: number }> {
    const result = await api.post<{ skipped_count?: number } | null>(`${root}/read-through`, { read_through: readThrough }, { token });
    return { skipped: Math.max(0, Number(result?.skipped_count ?? 0) || 0) };
  },
};

/** Destinations must stay within the authenticated patient app. */
export function notificationDestination(value: string | null): string | null {
  if (!value || !value.startsWith("/") || value.startsWith("//") || /[\\\s]/.test(value)) return null;
  const url = new URL(value, "https://patient.invalid");
  return url.origin === "https://patient.invalid" && (["/chat", "/today", "/visits", "/records", "/reminders"].includes(url.pathname) || /^\/symptoms\/[0-9a-f-]{36}$/i.test(url.pathname)) ? value : null;
}
