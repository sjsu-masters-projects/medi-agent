"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { CareConversations } from "@/components/features/care-conversations";
import { ClinicFilterEmpty, ClinicFilterField } from "@/components/features/clinic-chip";
import { EarlierMessages } from "@/components/features/operational-alerts";
import { clinicScopeLabel } from "@/hooks/clinic-scope";
import { useClinicFilter } from "@/hooks/use-clinic-filter";

function MessagesInbox() {
  const searchParams = useSearchParams();
  const clinicFilter = useClinicFilter();
  const scope = clinicScopeLabel(clinicFilter);
  return <>
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-[-0.02em] text-ink">Messages</h1>
        <p className="mt-1 max-w-[80ch] text-sm text-muted">Conversations with assigned patients.{scope ? ` · ${scope}` : ""}</p>
      </div>
      <ClinicFilterField filter={clinicFilter} />
    </div>
    {clinicFilter.ready ? <CareConversations
      audience="clinician"
      clinicEmpty={clinicFilter.clinicId ? <ClinicFilterEmpty filter={clinicFilter} noun="conversations" /> : null}
      clinicId={clinicFilter.clinicId}
      conversationId={searchParams.get("conversation")}
    /> : null}
    <EarlierMessages clinicId={clinicFilter.clinicId} showClinic={clinicFilter.multi} />
  </>;
}

export default function MessagesPage() {
  return <div className="ma-page space-y-5">
    <Suspense fallback={<p role="status">Loading conversations…</p>}><MessagesInbox /></Suspense>
  </div>;
}
