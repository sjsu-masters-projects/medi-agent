"use client";

import { useState } from "react";
import { Accordion, AccordionItem } from "@/components/ui/accordion";
import { AiChip } from "@/components/ui/ai-chip";
import { Icon } from "@/components/ui/icons";
import { annotateDocument } from "@/services/clinicians";

interface DocumentSummaryProps {
    documentId: string;
    patientId: string;
    summaryText: string;
    existingAnnotation?: string;
}

interface ParsedSection {
    type: "general";
    title: string;
    items: string[];
}

// ── Parser ─────────────────────────────────────────────────────────────────

function cleanSummaryLine(line: string): string {
    return line
        .replace(/^#+\s*/, "")
        .replace(/[\*_`]/g, "")
        .replace(/\s{2,}/g, " ")
        .trim();
}

function parseSummary(text: string): ParsedSection[] {
    // A model-generated summary is display text, not a coded clinical record. Do not
    // infer medication, risk, or appointment semantics from familiar words: that can
    // turn an incomplete sentence into a misleading clinical category or action.
    const lines = text
        .split("\n")
        .map(cleanSummaryLine)
        .filter(Boolean);

    return lines.length > 0 ? [{ type: "general", title: "Summary", items: lines }] : [];
}

// ── Section badge ───────────────────────────────────────────────────────────

function SectionBadge({ type, count }: { type: ParsedSection["type"]; count: number }) {
    const styles: Record<ParsedSection["type"], string> = {
        general: "bg-sunken text-ink-2",
    };

    return (
        <span
            className={`inline-flex items-center rounded-[7px] px-2 py-0.5 font-mono text-xs font-medium ${styles[type]}`}
        >
            {count}
        </span>
    );
}

// ── Main component ──────────────────────────────────────────────────────────

export function DocumentSummary({
    documentId,
    patientId,
    summaryText,
    existingAnnotation = "",
}: DocumentSummaryProps) {
    const sections = parseSummary(summaryText);
    const [annotation, setAnnotation] = useState(existingAnnotation);
    const [editing, setEditing] = useState(false);
    const [saving, setSaving] = useState(false);
    const [saveError, setSaveError] = useState<string | null>(null);

    async function handleSaveAnnotation() {
        if (!annotation.trim()) return;
        setSaving(true);
        setSaveError(null);

        try {
            await annotateDocument(patientId, documentId, annotation);
            setEditing(false);
        } catch (err) {
            setSaveError(err instanceof Error ? err.message : "Failed to save annotation");
        } finally {
            setSaving(false);
        }
    }

    return (
        <div className="space-y-3">
            {/* Model-generated explanation: always labelled as AI output, never sealed */}
            <section className="rounded-xl border border-line bg-surface-2 p-3">
                <div className="mb-3 flex flex-wrap items-center gap-2 px-1">
                    <AiChip>AI-generated patient explanation</AiChip>
                </div>
                <Accordion>
                    {sections.map((section, idx) => (
                        <AccordionItem
                            badge={<SectionBadge count={section.items.length} type={section.type} />}
                            defaultOpen={idx === 0}
                            key={`${section.type}-${idx}`}
                            title={section.title}
                        >
                            <ul className="max-w-[80ch] space-y-2" aria-label={section.title}>
                                {section.items.map((item, itemIdx) => (
                                    <li
                                        className="flex items-start gap-2.5 text-sm leading-relaxed text-ink-2"
                                        key={itemIdx}
                                    >
                                        <span
                                            aria-hidden="true"
                                            className="mt-[9px] h-1.5 w-1.5 shrink-0 rounded-full bg-[#94A3B8]"
                                        />
                                        {item}
                                    </li>
                                ))}
                            </ul>
                        </AccordionItem>
                    ))}
                </Accordion>
            </section>

            {/* Clinician annotation */}
            <div className="rounded-xl border border-line bg-surface p-4">
                <div className="mb-2 flex items-center justify-between gap-3">
                    <p className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">
                        Clinician Annotation
                    </p>
                    {!editing && (
                        <button
                            aria-label="Edit annotation"
                            className="ma-press inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-muted hover:bg-sunken hover:text-ink"
                            id="edit-annotation-btn"
                            onClick={() => setEditing(true)}
                            type="button"
                        >
                            <Icon name="edit" aria-hidden="true" className="h-3.5 w-3.5" />
                            Edit
                        </button>
                    )}
                </div>

                {editing ? (
                    <div className="space-y-2.5">
                        <textarea
                            aria-label="Clinician annotation text"
                            className="w-full rounded-[10px] border border-line-strong bg-surface px-3.5 py-2.5 text-sm text-ink outline-none transition placeholder:text-[#94A3B8] focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)]"
                            id={`annotation-textarea-${documentId}`}
                            onChange={(e) => setAnnotation(e.target.value)}
                            placeholder="Add your clinical notes visible to the patient alongside the AI summary…"
                            rows={4}
                            value={annotation}
                        />
                        {saveError && (
                            <p className="flex items-start gap-2 text-xs text-risk-ink" role="alert">
                                <Icon name="alert" aria-hidden="true" className="mt-px h-3.5 w-3.5 shrink-0" />
                                {saveError}
                            </p>
                        )}
                        <div className="flex gap-2">
                            <button
                                className="ma-press inline-flex h-8 items-center gap-1.5 rounded-lg bg-primary px-3 text-xs font-semibold text-white hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-track disabled:text-[#94A3B8]"
                                disabled={saving || !annotation.trim()}
                                id={`save-annotation-btn-${documentId}`}
                                onClick={handleSaveAnnotation}
                                type="button"
                            >
                                <Icon name="check" aria-hidden="true" className="h-3.5 w-3.5" />
                                {saving ? "Saving…" : "Save"}
                            </button>
                            <button
                                className="ma-press inline-flex h-8 items-center rounded-lg border border-line-strong bg-surface px-3 text-xs font-medium text-ink-2 hover:bg-surface-2 hover:text-ink"
                                onClick={() => {
                                    setEditing(false);
                                    setAnnotation(existingAnnotation);
                                }}
                                type="button"
                            >
                                Cancel
                            </button>
                        </div>
                    </div>
                ) : (
                    <p className="max-w-[80ch] text-sm leading-relaxed text-ink-2">
                        {annotation || (
                            <span className="text-muted">
                                No annotation yet. Click Edit to add one.
                            </span>
                        )}
                    </p>
                )}
            </div>
        </div>
    );
}
