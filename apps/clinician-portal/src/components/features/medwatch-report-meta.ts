import type { MedWatchDraft } from "@/services/clinicians";

export type ReportTab = "drafts" | "approved" | "submitted" | "discarded";

export function reportTabOf(draft: MedWatchDraft): ReportTab {
    if (draft.discardedAt) return "discarded";
    if (draft.status === "submitted") return "submitted";
    return draft.status === "reviewed" ? "approved" : "drafts";
}

export function patientCode(draft: MedWatchDraft): string {
    return draft.formData.section_a.identifier.trim() || "No identifier";
}

export function productName(draft: MedWatchDraft): string {
    return draft.formData.section_d.product_1.name.trim() || "—";
}

/** A one-line event label: the first sentence of the B5 narrative. */
export function eventSummary(draft: MedWatchDraft): string {
    const narrative = draft.formData.section_b.narrative.replace(/\s+/g, " ").trim();
    if (!narrative) return "—";
    const sentence = narrative.split(/(?<=[.!?])\s/)[0];
    return sentence.length > 90 ? `${sentence.slice(0, 87)}…` : sentence;
}
