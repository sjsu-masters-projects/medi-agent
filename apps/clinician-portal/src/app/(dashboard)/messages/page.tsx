"use client";

import { useState } from "react";
import { CareConversations } from "@/components/features/care-conversations";
import { OperationalAlerts } from "@/components/features/operational-alerts";

const viewButton = "ma-press h-8 rounded-[7px] px-3.5 text-[13px] font-medium transition-colors";

export default function MessagesPage() {
  const [view, setView] = useState<"conversations" | "alerts">("conversations");
  return <div className="ma-page space-y-5">
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-[-0.02em] text-ink">Messages</h1>
        <p className="mt-1 max-w-[80ch] text-sm text-muted">Contact assigned patients in Conversations. Operational alerts are separate notification history.</p>
      </div>
      <div role="group" aria-label="Message views" className="inline-flex gap-0.5 rounded-[10px] border border-line bg-sunken p-[3px]">
        <button type="button" aria-pressed={view === "conversations"} onClick={() => setView("conversations")}
          className={`${viewButton} ${view === "conversations" ? "bg-surface text-ink shadow-[var(--shadow-card)]" : "text-muted hover:text-ink"}`}>Conversations</button>
        <button type="button" aria-pressed={view === "alerts"} onClick={() => setView("alerts")}
          className={`${viewButton} ${view === "alerts" ? "bg-surface text-ink shadow-[var(--shadow-card)]" : "text-muted hover:text-ink"}`}>Operational alerts</button>
      </div>
    </div>
    <div hidden={view !== "conversations"}><CareConversations audience="clinician" visible={view === "conversations"} /></div>
    {view === "alerts" && <OperationalAlerts />}
  </div>;
}
