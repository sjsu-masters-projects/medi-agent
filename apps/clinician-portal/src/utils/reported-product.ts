import type { SymptomReport } from "@/types";

function record(value: unknown): Record<string, unknown> | null {
    return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

/** Read confirmed patient testimony only; never infer a canonical medication link. */
export function reportedProduct(raw: Record<string, unknown>): SymptomReport["reportedProduct"] {
    if (raw.confirmation_state !== "patient_confirmed") return undefined;
    const answers = record(record(raw.confirmed_content)?.answers);
    const product = record(answers?.product);
    const value = record(product?.value);
    if (product?.state !== "answered" || typeof value?.name !== "string" || !value.name.trim()) return undefined;
    return { name: value.name.trim(), concern: typeof value.concern === "boolean" ? value.concern : null };
}
