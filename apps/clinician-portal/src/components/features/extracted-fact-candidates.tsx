"use client";

import type { ReactNode } from "react";
import { Icon } from "@/components/ui/icons";
import { OriginalText, TranslationBadge, UntranslatedBadge } from "@/components/ui/translation-note";
import { EvidenceGlossLine, glossFor, useEvidenceGlosses, type GlossMap } from "@/components/features/evidence-gloss";
import type { ExtractedDocumentFact } from "@/services/clinicians";

/**
 * Candidate facts extracted from one document, shown for clinician review.
 *
 * Printed values are displayed as printed. Derived keys (flag meaning, range
 * status, consistency, medication action) are never listed as raw fields; they
 * only drive the badges and warnings below so a stopped medication or a
 * critical result cannot be mistaken for a routine one.
 */

const FACT_TYPE_HEADINGS: Record<string, string> = {
    allergy: "Allergy",
    appointment: "Appointment",
    condition: "Condition",
    immunization: "Immunization",
    lab_result: "Lab result",
    medication: "Medication",
    obligation: "Instruction",
    procedure: "Procedure",
    vital_sign: "Vital sign",
};

const FACT_FIELD_LABELS: Record<string, Record<string, string>> = {
    allergy: { allergen: "Allergen", reaction: "Reaction", severity: "Severity" },
    appointment: {
        description: "Appointment",
        location: "Location",
        provider: "Provider",
        scheduled_for: "Scheduled for",
    },
    condition: { name: "Condition", notes: "Notes", status: "Status" },
    immunization: { administered_at: "Administered", dose_number: "Dose number", vaccine: "Vaccine" },
    lab_result: {
        collected_at: "Collected",
        flag: "Flag",
        panel: "Panel",
        reference_range: "Reference range",
        specimen: "Specimen",
        test_name: "Test",
        unit: "Unit",
        value: "Result",
    },
    medication: {
        dosage: "Dose",
        frequency: "Frequency",
        instructions: "Instructions",
        name: "Medication",
        route: "Route",
        status: "Printed status",
    },
    obligation: { description: "Instruction", frequency: "Frequency", obligation_type: "Type" },
    procedure: { name: "Procedure", performed_at: "Performed", result: "Result" },
    vital_sign: { measured_at: "Measured", name: "Measurement", unit: "Unit", value: "Value" },
};

/** Keys computed by the backend rather than printed in the source. */
const DERIVED_KEYS = new Set(["consistency", "flag_meaning", "range_status", "medication_action"]);

/** Lab fields rendered in the compact result row rather than the generic list. */
const LAB_ROW_KEYS = new Set([
    "collected_at",
    "flag",
    "panel",
    "reference_range",
    "specimen",
    "test_name",
    "unit",
    "value",
]);

const BADGE = "inline-flex items-center gap-1 whitespace-nowrap rounded-[7px] px-2 py-0.5 text-xs font-semibold";

function humanize(key: string): string {
    const text = key.replaceAll("_", " ");
    return text.charAt(0).toUpperCase() + text.slice(1);
}

export function factTypeHeading(factType: string): string {
    return FACT_TYPE_HEADINGS[factType] ?? humanize(factType);
}

export function factFieldLabel(factType: string, key: string): string {
    return FACT_FIELD_LABELS[factType]?.[key] ?? humanize(key);
}

function isPresent(value: unknown): boolean {
    return value !== null && value !== undefined && !(typeof value === "string" && value.trim() === "");
}

function formatFactField(value: unknown): string {
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
        return String(value);
    }
    return JSON.stringify(value) ?? "Not supplied";
}

function textValue(value: unknown): string {
    return isPresent(value) ? formatFactField(value).trim() : "";
}

/** One printed field as the clinician reads it, plus the original when English replaced it. */
export interface FactField {
    key: string;
    label: string;
    value: string;
    /** The source text this English replaced, when the two differ. */
    original?: string;
}

/** Printed fields in source order, excluding derived and (optionally) other keys. */
export function factFields(
    fact: ExtractedDocumentFact,
    exclude: ReadonlySet<string> = new Set(),
): FactField[] {
    /* LOC-003: prefer English display_value fields when available (Spanish source). */
    const displayValue = fact.display_value ?? {};
    return Object.entries(fact.value)
        .filter(([key, value]) => !DERIVED_KEYS.has(key) && !exclude.has(key) && isPresent(value))
        .map(([key, value]) => {
            const englishOverride = displayValue[key];
            const printed = formatFactField(value);
            const translated = typeof englishOverride === "string" && englishOverride.trim()
                ? englishOverride.trim()
                : "";
            /* LOC-003 item 4: the original stays one tap away, never replaced in storage. */
            return {
                key,
                label: factFieldLabel(fact.fact_type, key),
                value: translated || printed,
                original: translated && translated !== printed.trim() ? printed : undefined,
            };
        });
}

/** LOC-003: True when this fact was extracted from a Spanish document and has English display fields. */
export function isFactTranslatedFromSpanish(fact: ExtractedDocumentFact): boolean {
    return fact.display_locale === "es-MX" && fact.display_value != null && Object.keys(fact.display_value).length > 0;
}

/**
 * LOC-003 item 6: a Spanish fact the translation guard rejected, or the model never
 * translated. Ingestion records `es-MX` either way, so the absence of English display
 * fields is exactly the untranslated state — and it must be said, not left to look like
 * English that happens to be in Spanish.
 */
export function isFactUntranslated(fact: ExtractedDocumentFact): boolean {
    return fact.display_locale === "es-MX" && !isFactTranslatedFromSpanish(fact);
}

/** The Spanish text of an untranslated fact, for the card's "show original" disclosure. */
export function untranslatedFactText(fact: ExtractedDocumentFact): string {
    return factFields(fact)
        .map((field) => `${field.label}: ${field.value}`)
        .join(" · ");
}

export type FactReviewEntry =
    | { kind: "fact"; fact: ExtractedDocumentFact }
    | { kind: "panel"; panel: string; facts: ExtractedDocumentFact[] };

/**
 * Lab results that share a printed panel are gathered under that panel at the
 * position of its first result; everything else keeps source order.
 */
export function groupFactsForReview(facts: ExtractedDocumentFact[]): FactReviewEntry[] {
    const entries: FactReviewEntry[] = [];
    const panels = new Map<string, { kind: "panel"; panel: string; facts: ExtractedDocumentFact[] }>();
    for (const fact of facts) {
        const panel = fact.fact_type === "lab_result" ? textValue(fact.value.panel) : "";
        if (!panel) {
            entries.push({ kind: "fact", fact });
            continue;
        }
        const key = panel.toLowerCase();
        let group = panels.get(key);
        if (!group) {
            group = { kind: "panel", panel, facts: [] };
            panels.set(key, group);
            entries.push(group);
        }
        group.facts.push(fact);
    }
    return entries;
}

function candidateState(fact: ExtractedDocumentFact): string {
    return fact.review_state === "pending_review"
        ? "Pending clinician review"
        : fact.review_state.replaceAll("_", " ");
}

function MedicationActionBadge({ action }: { action: string }) {
    if (action === "stopped") {
        return (
            <span className={`${BADGE} bg-risk-strong text-white`}>
                <Icon name="stop" aria-hidden="true" className="h-3 w-3" />
                Stop
                <span className="sr-only"> — source says to stop this medication</span>
            </span>
        );
    }
    if (action === "held") {
        return (
            <span className={`${BADGE} bg-warn-strong text-white`}>
                <Icon name="stop" aria-hidden="true" className="h-3 w-3" />
                Hold
                <span className="sr-only"> — source says to hold this medication</span>
            </span>
        );
    }
    if (action === "new" || action === "changed") {
        return (
            <span className={`${BADGE} border border-line-strong bg-sunken text-ink-2`}>
                {action === "new" ? "New" : "Changed"}
            </span>
        );
    }
    return null;
}

const FLAG_MEANING_LABELS: Record<string, string> = {
    abnormal: "abnormal",
    critical: "critical",
    high: "high",
    low: "low",
};

function LabFlagBadges({ flag, meaning }: { flag: string; meaning: string }) {
    const flagged = meaning === "high" || meaning === "low" || meaning === "abnormal" || meaning === "critical";
    return (
        <span className="inline-flex flex-wrap items-center gap-1">
            {meaning === "critical" ? (
                <span className={`${BADGE} bg-risk-strong text-white`}>
                    <Icon name="alert" aria-hidden="true" className="h-3 w-3" />
                    Critical
                </span>
            ) : null}
            {flag ? (
                <span
                    className={`${BADGE} ${flagged ? "border border-risk-line bg-risk-soft text-risk-ink" : "border border-line-strong bg-sunken text-ink-2"}`}
                    title={FLAG_MEANING_LABELS[meaning] ? `Printed flag: ${FLAG_MEANING_LABELS[meaning]}` : "Printed flag"}
                >
                    {flag}
                    {FLAG_MEANING_LABELS[meaning] && meaning !== "critical" ? (
                        <span className="sr-only"> ({FLAG_MEANING_LABELS[meaning]})</span>
                    ) : null}
                </span>
            ) : null}
        </span>
    );
}

function CompactField({ label, children }: { label: string; children: ReactNode }) {
    return (
        <div className="min-w-0">
            <dt className="text-[11px] font-medium text-muted">{label}</dt>
            <dd className="break-words text-sm text-ink-2">{children}</dd>
        </div>
    );
}

function LabResultRow({ fact }: { fact: ExtractedDocumentFact }) {
    const value = fact.value;
    const testName = textValue(value.test_name);
    const result = textValue(value.value);
    const unit = textValue(value.unit);
    const range = textValue(value.reference_range);
    const flag = textValue(value.flag);
    const meaning = textValue(value.flag_meaning).toLowerCase();
    const collected = textValue(value.collected_at);
    const specimen = textValue(value.specimen);
    const label = (key: string) => factFieldLabel("lab_result", key);
    return (
        <dl className="mt-3 flex flex-wrap items-start gap-x-5 gap-y-2">
            <CompactField label={label("test_name")}>
                <span className="font-semibold text-ink">{testName || "Not supplied"}</span>
            </CompactField>
            {result || unit ? (
                <CompactField label={label("value")}>
                    <span className="font-mono text-ink">{result}</span>
                    {unit ? <span className="text-ink-2"> {unit}</span> : null}
                </CompactField>
            ) : null}
            {range ? <CompactField label={label("reference_range")}>{range}</CompactField> : null}
            {flag || meaning === "critical" ? (
                <CompactField label={label("flag")}>
                    <LabFlagBadges flag={flag} meaning={meaning} />
                </CompactField>
            ) : null}
            {collected ? <CompactField label={label("collected_at")}><span className="font-mono text-xs">{collected}</span></CompactField> : null}
            {specimen ? <CompactField label={label("specimen")}>{specimen}</CompactField> : null}
        </dl>
    );
}

function FactFieldList({ fields }: { fields: FactField[] }) {
    if (fields.length === 0) {
        return null;
    }
    return (
        <dl className="mt-3 space-y-1 text-sm text-ink-2">
            {fields.map(({ key, label, value, original }) => (
                <div className="grid grid-cols-[minmax(0,7rem)_minmax(0,1fr)] gap-2" key={key}>
                    <dt className="text-[13px] font-medium text-muted">{label}</dt>
                    <dd className="min-w-0 whitespace-pre-line break-words">
                        {value}
                        {/* LOC-003: the printed Spanish this English replaced, one tap away. */}
                        {original ? <OriginalText className="mt-0.5">{original}</OriginalText> : null}
                    </dd>
                </div>
            ))}
        </dl>
    );
}

interface FactCandidateProps {
    fact: ExtractedDocumentFact;
    selected: boolean;
    onSelect: (factId: string) => void;
    /** LOC-003 item 2: English glosses for the Spanish excerpts on this screen. */
    glosses?: GlossMap;
}

function FactCandidate({ fact, selected, onSelect, glosses }: FactCandidateProps) {
    const isLab = fact.fact_type === "lab_result";
    const action = fact.fact_type === "medication" ? textValue(fact.value.medication_action).toLowerCase() : "";
    const consistency = textValue(fact.value.consistency);
    const citation = fact.citations?.[0];
    const translated = isFactTranslatedFromSpanish(fact);
    const untranslated = isFactUntranslated(fact);
    return (
        <article
            className={`ma-press w-full rounded-xl border p-3.5 text-left ${selected ? "border-primary bg-primary-tint" : "border-line bg-surface hover:bg-surface-2"}`}
        >
            <button aria-pressed={selected} className="ma-press mb-2 min-h-10 w-full rounded-lg px-2 text-left text-sm font-semibold text-primary hover:bg-primary-tint" onClick={() => onSelect(fact.id)} type="button">Select {factTypeHeading(fact.fact_type)} evidence</button>
            <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
                <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                        <p className="text-sm font-semibold text-ink">{factTypeHeading(fact.fact_type)}</p>
                        {action ? <MedicationActionBadge action={action} /> : null}
                        {/* LOC-003 items 5 and 6: translated text carries the model and its
                            caveat; a guard-rejected fact says so instead of looking English. */}
                        {translated ? <TranslationBadge modelId={fact.display_model_id} /> : null}
                        {untranslated ? <UntranslatedBadge /> : null}
                    </div>
                    <p className="mt-1 text-xs font-medium text-warn-ink">{candidateState(fact)}</p>
                </div>
                <span className="whitespace-nowrap rounded-[7px] bg-warn-soft px-2 py-1 text-xs font-medium text-warn-ink">
                    {fact.confidence_score === null || fact.confidence_score === undefined ? "Confidence unavailable" : <><span className="font-mono">{Math.round(fact.confidence_score * 100)}%</span> confidence</>}
                </span>
            </div>
            {isLab ? <LabResultRow fact={fact} /> : null}
            <FactFieldList fields={factFields(fact, isLab ? LAB_ROW_KEYS : undefined)} />
            {consistency ? (
                <p className="mt-3 flex items-start gap-2 rounded-lg border border-warn-line bg-warn-soft px-3 py-2 text-xs font-medium text-warn-ink">
                    <Icon name="alert" aria-hidden="true" className="mt-px h-3.5 w-3.5 shrink-0" />
                    <span>{consistency}</span>
                </p>
            ) : null}
            {/* LOC-003 item 2: the excerpt stays the exact printed text; English sits under it. */}
            {citation?.excerpt ? <span className="mt-3 block border-l-2 border-line-strong pl-3 text-xs text-ink-2">
                <span className="block" lang={fact.display_locale === "es-MX" ? "es-MX" : undefined}>“{citation.excerpt}”{citation.location?.page ? ` · page ${citation.location.page}` : ""}</span>
                {glosses ? <EvidenceGlossLine gloss={glossFor(glosses, citation.excerpt)} /> : null}
            </span> : null}
        </article>
    );
}

interface ExtractedFactCandidatesProps {
    facts: ExtractedDocumentFact[];
    selectedFactId: string | null;
    onSelect: (factId: string) => void;
    /** Needed to ask for glosses; without it the Spanish excerpts simply stand alone. */
    patientId?: string;
}

export function ExtractedFactCandidates({ facts, selectedFactId, onSelect, patientId }: ExtractedFactCandidatesProps) {
    /* LOC-003 item 2: one request covers every Spanish excerpt on screen. */
    const glosses = useEvidenceGlosses(patientId, facts.map((fact) => fact.citations?.[0]?.excerpt));
    return (
        <div className="space-y-2.5" role="list" aria-label="Extracted fact candidates">
            {groupFactsForReview(facts).map((entry, index) =>
                entry.kind === "fact" ? (
                    <div key={entry.fact.id} role="listitem">
                        <FactCandidate fact={entry.fact} glosses={glosses} onSelect={onSelect} selected={selectedFactId === entry.fact.id} />
                    </div>
                ) : (
                    <div key={`panel-${index}-${entry.panel}`} role="listitem">
                        <section aria-labelledby={`fact-panel-${index}`} className="space-y-2 rounded-xl border border-line bg-surface-2 p-2.5">
                            <h3 className="flex flex-wrap items-baseline gap-x-2 px-1" id={`fact-panel-${index}`}>
                                <span className="font-mono text-[11px] font-medium uppercase tracking-[.06em] text-muted">Lab panel</span>
                                <span className="break-words text-sm font-semibold text-ink">{entry.panel}</span>
                            </h3>
                            <div className="space-y-2" role="list" aria-label={`${entry.panel} results`}>
                                {entry.facts.map((fact) => (
                                    <div key={fact.id} role="listitem">
                                        <FactCandidate fact={fact} glosses={glosses} onSelect={onSelect} selected={selectedFactId === fact.id} />
                                    </div>
                                ))}
                            </div>
                        </section>
                    </div>
                ),
            )}
        </div>
    );
}
