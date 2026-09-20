"use client";

import { useState } from "react";
import { HiOutlinePencilSquare, HiOutlineCheck } from "react-icons/hi2";
import { Accordion, AccordionItem } from "@/components/ui/accordion";
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
        general: "bg-gray-100 text-gray-600",
    };

    return (
        <span
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${styles[type]}`}
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
        <div className="space-y-4">
            {/* Accordion sections */}
            <Accordion>
                {sections.map((section, idx) => (
                    <AccordionItem
                        badge={<SectionBadge count={section.items.length} type={section.type} />}
                        defaultOpen={idx === 0}
                        key={`${section.type}-${idx}`}
                        title={section.title}
                    >
                        <ul className="space-y-2" aria-label={section.title}>
                            {section.items.map((item, itemIdx) => (
                                <li
                                    className="flex items-start gap-2 text-sm text-gray-700"
                                    key={itemIdx}
                                >
                                    <span
                                        aria-hidden="true"
                                        className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-gray-400"
                                    />
                                    {item}
                                </li>
                            ))}
                        </ul>
                    </AccordionItem>
                ))}
            </Accordion>

            {/* Clinician annotation */}
            <div className="rounded-xl border border-dashed border-gray-300 bg-amber-50/40 p-4">
                <div className="mb-2 flex items-center justify-between">
                    <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">
                        Clinician Annotation
                    </p>
                    {!editing && (
                        <button
                            aria-label="Edit annotation"
                            className="flex items-center gap-1 rounded px-2 py-1 text-xs text-gray-500 hover:bg-amber-100"
                            id="edit-annotation-btn"
                            onClick={() => setEditing(true)}
                            type="button"
                        >
                            <HiOutlinePencilSquare aria-hidden="true" className="h-3 w-3" />
                            Edit
                        </button>
                    )}
                </div>

                {editing ? (
                    <div className="space-y-2">
                        <textarea
                            aria-label="Clinician annotation text"
                            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                            id={`annotation-textarea-${documentId}`}
                            onChange={(e) => setAnnotation(e.target.value)}
                            placeholder="Add your clinical notes visible to the patient alongside the AI summary…"
                            rows={4}
                            value={annotation}
                        />
                        {saveError && (
                            <p className="text-xs text-red-600" role="alert">{saveError}</p>
                        )}
                        <div className="flex gap-2">
                            <button
                                className="flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-60"
                                disabled={saving || !annotation.trim()}
                                id={`save-annotation-btn-${documentId}`}
                                onClick={handleSaveAnnotation}
                                type="button"
                            >
                                <HiOutlineCheck aria-hidden="true" className="h-3.5 w-3.5" />
                                {saving ? "Saving…" : "Save"}
                            </button>
                            <button
                                className="rounded-lg border border-gray-300 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
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
                    <p className="text-sm text-gray-600">
                        {annotation || (
                            <span className="italic text-gray-400">
                                No annotation yet. Click Edit to add one.
                            </span>
                        )}
                    </p>
                )}
            </div>
        </div>
    );
}
