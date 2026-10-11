"use client";

import { useState } from "react";
import { NotificationList } from "@/components/features/notification-centre";
import { useNotificationCentre } from "@/components/features/notification-provider";

export default function AlertsPage() {
  const [view, setView] = useState<"actions" | "history">("actions");
  const { summary } = useNotificationCentre();
  return <div className="ma-page space-y-5">
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-[-0.02em] text-ink">Alerts</h1>
        <p className="mt-1 max-w-[80ch] text-sm text-muted">Reading or acknowledging an alert does not approve care or resolve a clinical concern.</p>
      </div>
      <p className="text-sm text-muted" role="status">{summary.error || !summary.data ? "Counts unavailable" : `${summary.data.action_item_count} need attention · ${summary.data.unread_count} unread`}</p>
    </div>
    <div role="group" aria-label="Alerts views" className="inline-flex flex-wrap gap-1 rounded-lg border border-line bg-surface-2 p-1">
      {(["actions", "history"] as const).map((value) => <button key={value} type="button" aria-pressed={view === value} onClick={() => setView(value)} className={`min-h-9 rounded-md px-4 text-sm ${view === value ? "bg-surface font-medium text-ink shadow-sm" : "text-muted"}`}>{value === "actions" ? "Needs attention" : "History"}</button>)}
    </div>
    <NotificationList key={view} actions={view === "actions"} />

  </div>;
}
