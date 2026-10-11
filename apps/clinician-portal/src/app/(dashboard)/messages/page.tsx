"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { CareConversations } from "@/components/features/care-conversations";
import { EarlierMessages } from "@/components/features/operational-alerts";

function MessagesInbox() {
  const searchParams = useSearchParams();
  return <CareConversations audience="clinician" conversationId={searchParams.get("conversation")} />;
}

export default function MessagesPage() {
  return <div className="ma-page space-y-5">
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-[-0.02em] text-ink">Messages</h1>
        <p className="mt-1 max-w-[80ch] text-sm text-muted">Conversations with assigned patients.</p>
      </div>
    </div>
    <Suspense fallback={<p role="status">Loading conversations…</p>}><MessagesInbox /></Suspense>
    <EarlierMessages />
  </div>;
}
