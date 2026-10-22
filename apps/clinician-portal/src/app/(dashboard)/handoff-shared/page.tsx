"use client";

import { SharedWithMeList } from "@/components/features/shared-handoff-list";

export default function SharedHandoffsPage() {
    return (
        <div className="ma-page space-y-5">
            <h1 className="text-2xl font-semibold tracking-[-0.02em] text-ink">Handoff summaries shared with me</h1>
            <SharedWithMeList />
        </div>
    );
}
