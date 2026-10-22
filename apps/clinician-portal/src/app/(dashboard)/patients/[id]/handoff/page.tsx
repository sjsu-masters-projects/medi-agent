"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { HandoffSummaryList } from "@/components/features/handoff-summary-list";

export default function HandoffSummariesPage() {
    const patientId = useParams()["id"] as string;
    return (
        <div className="ma-page space-y-5">
            <div>
                <Link className="text-[13px] font-medium text-primary" href={`/patients/${encodeURIComponent(patientId)}`}>Back to patient</Link>
                <h1 className="mt-1 text-2xl font-semibold tracking-[-0.02em] text-ink">Handoff summaries</h1>
            </div>
            <HandoffSummaryList patientId={patientId} />
        </div>
    );
}
