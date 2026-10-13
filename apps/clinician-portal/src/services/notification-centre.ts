import { api } from "@/services/api";
import type { CentrePage, CentreSummary, NotificationCategory } from "@/types/notification-centre";

const root = "/api/v1/notification-centre";
export const notificationCentre = {
  list(token: string, actions = false, cursor?: string, signal?: AbortSignal, category?: NotificationCategory) {
    const query = new URLSearchParams({ locale: "en-US", limit: "50" });
    if (!actions) query.set("unread", "false");
    if (cursor) query.set("cursor", cursor);
    if (actions && category) query.set("category", category);
    return api.get<CentrePage>(`${root}${actions ? "/action-items" : ""}?${query}`, { token, signal });
  },
  summary: (token: string, signal?: AbortSignal) => api.get<CentreSummary>(`${root}/summary`, { token, signal }),
  read: (token: string, id: string) => api.put(`${root}/${encodeURIComponent(id)}/read`, undefined, { token }),
  /** Marks a loaded page read; items no longer available are skipped, not fatal. */
  readThrough: async (token: string, read_through: string): Promise<{ skipped: number }> => {
    const result = await api.post<{ skipped_count?: number } | null>(`${root}/read-through`, { read_through }, { token });
    return { skipped: Math.max(0, Number(result?.skipped_count ?? 0) || 0) };
  },
  acknowledge: (token: string, id: string, note?: string) => api.post(`${root}/action-items/${encodeURIComponent(id)}/acknowledge`, note ? { note } : {}, { token }),
};

// Keep target identity supplied by the server; never synthesize a clinical destination.
export function notificationTarget(url: string | null): string | null {
  if (!url || !url.startsWith("/") || url.startsWith("//") || /[\\\u0000-\u0020]/.test(url)) return null;
  return url;
}
