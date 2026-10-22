"use client";

import { useParams } from "next/navigation";
import { HandoffSummaryReview } from "@/components/features/handoff-summary-review";

export default function HandoffSummaryPage() {
    const params = useParams();
    return (
        <div className="ma-page">
            <HandoffSummaryReview patientId={params["id"] as string} summaryId={params["summaryId"] as string} />
        </div>
    );
}
