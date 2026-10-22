"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { ClinicFilterField } from "@/components/features/clinic-chip";
import { ExternalRecordReviews } from "@/components/features/external-record-reviews";
import { NotificationList } from "@/components/features/notification-centre";
import { useNotificationCentre } from "@/components/features/notification-provider";
import { clinicScopeLabel } from "@/hooks/clinic-scope";
import { useClinicFilter } from "@/hooks/use-clinic-filter";

function AlertsContent() {
  const clinicFilter = useClinicFilter();
  const [view, setView] = useState<"actions" | "history">("actions");
  const { summary } = useNotificationCentre();
  return <div className="ma-page space-y-5">
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-[-0.02em] text-ink">Alerts</h1>
        <p className="mt-1 max-w-[80ch] text-sm text-muted">Your clinical action inbox. Open each item in its review workspace. Reading or acknowledging an alert does not approve care or resolve a clinical concern.{clinicScopeLabel(clinicFilter) ? ` · ${clinicScopeLabel(clinicFilter)}` : ""}</p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <ClinicFilterField filter={clinicFilter} />
        <Link href={clinicFilter.clinicId ? `/review-queue?clinic=${encodeURIComponent(clinicFilter.clinicId)}` : "/review-queue"} className="inline-flex min-h-9 items-center rounded-lg border border-line-strong bg-surface px-3 text-sm font-medium text-ink-2 hover:bg-surface-2">Patient upload reviews</Link>
        <Link href={clinicFilter.clinicId ? `/care-plan-reviews?clinic=${encodeURIComponent(clinicFilter.clinicId)}` : "/care-plan-reviews"} className="inline-flex min-h-9 items-center rounded-lg border border-line-strong bg-surface px-3 text-sm font-medium text-ink-2 hover:bg-surface-2">Care plan reviews</Link>
        <p className="text-sm text-muted" role="status">{summary.error || !summary.data ? "Counts unavailable" : `${clinicFilter.multi && clinicFilter.clinicId ? "All clinics: " : ""}${summary.data.action_item_count} need attention · ${summary.data.unread_count} unread`}</p>
      </div>
    </div>
    <div role="group" aria-label="Alerts views" className="inline-flex flex-wrap gap-1 rounded-lg border border-line bg-surface-2 p-1">
      {(["actions", "history"] as const).map((value) => <button key={value} type="button" aria-pressed={view === value} onClick={() => setView(value)} className={`min-h-9 rounded-md px-4 text-sm ${view === value ? "bg-surface font-medium text-ink shadow-sm" : "text-muted"}`}>{value === "actions" ? "Needs attention" : "History"}</button>)}
    </div>
    <NotificationList key={view} actions={view === "actions"} clinicFilter={clinicFilter} />
    {view === "actions" && <ExternalRecordReviews clinicId={clinicFilter.clinicId} ready={clinicFilter.ready} />}

  </div>;
}

export default function AlertsPage() {
  return <Suspense fallback={<p role="status">Loading alerts…</p>}><AlertsContent /></Suspense>;
}
