"use client";

import { useState } from "react";
import { CareConversations } from "@/components/features/care-conversations";
import { OperationalAlerts } from "@/components/features/operational-alerts";

export default function MessagesPage() {
  const [view, setView] = useState<"conversations" | "alerts">("conversations");
  return <div className="mx-auto max-w-5xl space-y-6">
    <h1 className="text-2xl font-bold text-ink">Messages</h1>
    <p className="text-sm text-muted">Contact assigned patients in Conversations. Operational alerts are separate notification history.</p>
    <div role="group" aria-label="Message views" className="flex flex-wrap gap-3">
      <button type="button" aria-pressed={view === "conversations"} onClick={() => setView("conversations")}
        className={`rounded-lg border px-4 py-2 text-sm font-medium ${view === "conversations" ? "border-primary bg-primary-tint text-primary" : "border-line-strong bg-surface text-ink-2"}`}>Conversations</button>
      <button type="button" aria-pressed={view === "alerts"} onClick={() => setView("alerts")}
        className={`rounded-lg border px-4 py-2 text-sm font-medium ${view === "alerts" ? "border-primary bg-primary-tint text-primary" : "border-line-strong bg-surface text-ink-2"}`}>Operational alerts</button>
    </div>
    <div hidden={view !== "conversations"}><CareConversations audience="clinician" visible={view === "conversations"} /></div>
    {view === "alerts" && <OperationalAlerts />}
  </div>;
}
