"use client";

import { useParams } from "next/navigation";
import { SharedHandoffView } from "@/components/features/shared-handoff-view";

export default function SharedHandoffPage() {
    return (
        <div className="ma-page">
            <SharedHandoffView shareId={useParams()["shareId"] as string} />
        </div>
    );
}
