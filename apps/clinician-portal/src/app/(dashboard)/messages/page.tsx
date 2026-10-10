"use client";

import { useState } from "react";
import { CareConversations } from "@/components/features/care-conversations";
import { OperationalAlerts } from "@/components/features/operational-alerts";

export default function MessagesPage() {
  const [view, setView] = useState<"conversations" | "alerts">("conversations");
  return <div className="mx-auto max-w-5xl space-y-6">
    <h1 className="text-2xl font-bold text-gray-900">Messages</h1>
    <p className="text-sm text-gray-500">Contact assigned patients in Conversations. Operational alerts are separate notification history.</p>
    <div role="group" aria-label="Message views" className="flex flex-wrap gap-3">
      <button type="button" aria-pressed={view === "conversations"} onClick={() => setView("conversations")}
        className={`rounded-lg border px-4 py-2 text-sm font-medium ${view === "conversations" ? "border-blue-600 bg-blue-50 text-blue-700" : "border-gray-300 bg-white text-gray-700"}`}>Conversations</button>
      <button type="button" aria-pressed={view === "alerts"} onClick={() => setView("alerts")}
        className={`rounded-lg border px-4 py-2 text-sm font-medium ${view === "alerts" ? "border-blue-600 bg-blue-50 text-blue-700" : "border-gray-300 bg-white text-gray-700"}`}>Operational alerts</button>
    </div>
    <div hidden={view !== "conversations"}><CareConversations audience="clinician" visible={view === "conversations"} /></div>
    {view === "alerts" && <OperationalAlerts />}
  </div>;
}
