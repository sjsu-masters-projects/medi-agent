"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Badge, Button, ErrorState, Modal, Skeleton } from "@/components/ui";
import { AiChip } from "@/components/ui/ai-chip";
import { Icon } from "@/components/ui/icons";
import {
    fetchForm3500Preview,
    type Form3500Preview,
    type Form3500PreviewItem,
    type Form3500ProvenanceKind,
} from "@/services/clinicians";
import { gateIssueLabel, legacyKeyLabel, type MedWatchGateIssue } from "@/services/medwatch-form-3500";
import { TemplateSupersededNote } from "@/components/features/form-3500-download-dialog";

const wrapClass = "break-words [overflow-wrap:anywhere]";

export const NOT_SUBMITTED_FOOTER = "Not submitted to FDA by MediAgent";

const PROVENANCE_ORDER: Form3500ProvenanceKind[] = [
    "record",
    "ai_extracted",
    "patient_confirmed",
    "clinician_edited",
];

function ProvenanceChips({ item }: { item: Form3500PreviewItem }) {
    const kinds = PROVENANCE_ORDER.filter((kind) =>
        item.provenance.some((entry) => entry.kind === kind),
    );
    if (kinds.length === 0) return null;
    return (
        <span className="flex flex-wrap gap-1.5" aria-label="Source">
            {kinds.map((kind) => {
                if (kind === "ai_extracted") return <AiChip key={kind}>AI-extracted</AiChip>;
                if (kind === "patient_confirmed") {
                    return (
                        <Badge key={kind} variant="info">
                            Patient-confirmed
                        </Badge>
                    );
                }
                if (kind === "clinician_edited") {
                    return (
                        <Badge key={kind} variant="neutral">
                            <Icon className="h-3 w-3" name="edit" />
                            Clinician edited
                        </Badge>
                    );
                }
                return (
                    <Badge key={kind} variant="neutral">
                        Record
                    </Badge>
                );
            })}
        </span>
    );
}

function MissingBadge() {
    return (
        <Badge variant="warning">
            <Icon className="h-3 w-3" name="alert" />
            Missing for approval
        </Badge>
    );
}

/**
 * Read-only Form FDA 3500 layout of a draft, in form order. It has no input controls; the
 * clinician edits in the draft card and downloads the fillable PDF to submit it themselves.
 */
export function Form3500PreviewView({ preview }: { preview: Form3500Preview }) {
    const showMissing = preview.status === "draft";
    const missingPaths = new Set(preview.missingForApproval.map((issue) => issue.path));
    const itemPaths = new Set(
        preview.sections.flatMap((section) => section.items.map((item) => item.path)),
    );
    const rationaleMissing = missingPaths.has("mediagent_review.reportability_rationale");
    const legacyEntries = Object.entries(preview.legacy).filter(([, value]) => value.trim());

    return (
        <article aria-label="Form FDA 3500 preview" className="space-y-5 text-sm text-ink-2">
            <header className="space-y-1.5">
                <p className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">
                    Form FDA 3500 · revision {preview.template.revision}
                </p>
                <p className="leading-relaxed">
                    Voluntary report by a health professional. Sections C and E are left for you to
                    complete in the PDF if they apply.
                </p>
            </header>

            <TemplateSupersededNote template={preview.template} />

            {showMissing && preview.missingForApproval.length > 0 ? (
                <MissingList issues={preview.missingForApproval} />
            ) : null}

            {preview.sections.map((section) => {
                const headingId = `form-3500-section-${section.id}`;
                return (
                    <section
                        aria-labelledby={headingId}
                        className="ma-print-section min-w-0 rounded-xl border border-line"
                        key={section.id}
                    >
                        <h3
                            className="border-b border-line bg-surface-2 px-4 py-2.5 text-[13px] font-semibold text-ink"
                            id={headingId}
                        >
                            <span className="font-mono">{section.id}.</span> {section.title}
                        </h3>
                        {section.notCompletedByMediAgent ? (
                            <p className="px-4 py-3 text-muted">Not completed by MediAgent</p>
                        ) : (
                            <dl className="divide-y divide-line">
                                {section.items.map((item) => {
                                    const missing =
                                        showMissing &&
                                        (item.missingForApproval.length > 0 ||
                                            missingPaths.has(item.path));
                                    return (
                                        <div
                                            className="grid gap-x-4 gap-y-1.5 px-4 py-2.5 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]"
                                            key={`${item.item}-${item.path}`}
                                        >
                                            <dt className={`flex gap-2 text-ink-2 ${wrapClass}`}>
                                                <span className="w-8 shrink-0 font-mono text-xs leading-5 text-muted">
                                                    {item.item}
                                                </span>
                                                <span>{item.label}</span>
                                            </dt>
                                            <dd className="flex min-w-0 flex-col items-start gap-1.5">
                                                {item.value ? (
                                                    <span className={`text-ink ${wrapClass} whitespace-pre-line`}>
                                                        {item.value}
                                                    </span>
                                                ) : (
                                                    <span className="text-muted">Not provided</span>
                                                )}
                                                <span className="flex flex-wrap gap-1.5">
                                                    {missing ? <MissingBadge /> : null}
                                                    <ProvenanceChips item={item} />
                                                </span>
                                            </dd>
                                        </div>
                                    );
                                })}
                            </dl>
                        )}
                    </section>
                );
            })}

            <section
                aria-labelledby="form-3500-mediagent-review"
                className="ma-print-section rounded-xl border border-line bg-surface-2"
            >
                <h3
                    className="border-b border-line px-4 py-2.5 text-[13px] font-semibold text-ink"
                    id="form-3500-mediagent-review"
                >
                    MediAgent review (not part of Form 3500)
                </h3>
                <dl className="divide-y divide-line">
                    <div className="grid gap-x-4 gap-y-1 px-4 py-2.5 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
                        <dt>Calculated Naranjo score</dt>
                        <dd className="font-mono text-ink">
                            {preview.mediagentReview.naranjoScore ?? "Not provided"}
                        </dd>
                    </div>
                    <div className="grid gap-x-4 gap-y-1 px-4 py-2.5 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
                        <dt>Causality</dt>
                        <dd className="text-ink">
                            {preview.mediagentReview.causality ?? (
                                <span className="text-muted">Not provided</span>
                            )}
                        </dd>
                    </div>
                    <div className="grid gap-x-4 gap-y-1 px-4 py-2.5 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
                        <dt>Reportability rationale</dt>
                        <dd className="flex min-w-0 flex-col items-start gap-1.5">
                            {preview.mediagentReview.reportabilityRationale.trim() ? (
                                <span className={`text-ink ${wrapClass}`}>
                                    {preview.mediagentReview.reportabilityRationale}
                                </span>
                            ) : (
                                <span className="text-muted">Not provided</span>
                            )}
                            {showMissing && rationaleMissing ? <MissingBadge /> : null}
                        </dd>
                    </div>
                </dl>
            </section>

            {legacyEntries.length > 0 ? (
                <section
                    aria-labelledby="form-3500-legacy"
                    className="ma-print-section rounded-xl border border-line"
                >
                    <h3
                        className="border-b border-line px-4 py-2.5 text-[13px] font-semibold text-ink"
                        id="form-3500-legacy"
                    >
                        Earlier draft text with no Form 3500 item
                    </h3>
                    <dl className="divide-y divide-line">
                        {legacyEntries.map(([key, value]) => (
                            <div className="px-4 py-2.5" key={key}>
                                <dt className={`text-xs font-medium text-muted ${wrapClass}`}>{legacyKeyLabel(key)}</dt>
                                <dd className={`mt-1 text-ink ${wrapClass}`}>{value}</dd>
                            </div>
                        ))}
                    </dl>
                </section>
            ) : null}

            {showMissing ? (
                <UnplacedIssues issues={preview.missingForApproval} placed={itemPaths} />
            ) : null}

            <footer className="ma-print-footer flex items-center gap-2 border-t border-line pt-3 text-[13px] font-medium text-warn-ink">
                <Icon className="h-4 w-4 shrink-0" name="info" />
                {NOT_SUBMITTED_FOOTER}
            </footer>
        </article>
    );
}

function MissingList({ issues }: { issues: MedWatchGateIssue[] }) {
    return (
        <section
            aria-label="Missing for approval"
            className="rounded-xl border border-warn-line bg-warn-soft px-4 py-3 text-warn-ink"
        >
            <p className="flex items-center gap-2 font-semibold">
                <Icon className="h-4 w-4 shrink-0" name="alert" />
                Missing for approval (<span className="font-mono">{issues.length}</span>)
            </p>
            <ul className="mt-2 list-disc space-y-1 pl-6">
                {issues.map((issue) => (
                    <li className={wrapClass} key={`${issue.path}-${issue.code}`}>
                        {gateIssueLabel(issue)}
                    </li>
                ))}
            </ul>
        </section>
    );
}

/** Missing items with no previewed row (other than the review rationale) stay visible. */
function UnplacedIssues({ issues, placed }: { issues: MedWatchGateIssue[]; placed: Set<string> }) {
    const unplaced = issues.filter(
        (issue) =>
            !placed.has(issue.path) && issue.path !== "mediagent_review.reportability_rationale",
    );
    if (unplaced.length === 0) return null;
    return (
        <p className="text-[13px] text-ink-2">
            Also missing: {unplaced.map((issue) => gateIssueLabel(issue)).join("; ")}.
        </p>
    );
}

/** Opens the preview for a draft in the shared Modal, with loading, error and print. */
export function Form3500PreviewDialog({
    draftId,
    open,
    onClose,
}: {
    draftId: string;
    open: boolean;
    onClose: () => void;
}) {
    const [preview, setPreview] = useState<Form3500Preview | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);
    const request = useRef(0);

    const load = useCallback(async () => {
        const id = ++request.current;
        setLoading(true);
        setError(null);
        try {
            const result = await fetchForm3500Preview(draftId);
            if (id === request.current) setPreview(result);
        } catch (failure) {
            if (id === request.current) {
                setPreview(null);
                setError(
                    failure instanceof Error
                        ? failure.message
                        : "Unable to load the Form 3500 preview.",
                );
            }
        } finally {
            if (id === request.current) setLoading(false);
        }
    }, [draftId]);

    useEffect(() => {
        if (!open) return;
        // Load on open; the preview always reflects the stored revision.
        void load();
    }, [open, load]);

    return (
        <Modal contentClassName="max-w-4xl" onClose={onClose} open={open} title="Form FDA 3500 preview">
            <div className="ma-print-root space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3" data-print-hide>
                    <p className="text-[13px] text-ink-2">
                        Read-only. This shows the version you last saved.
                    </p>
                    <Button
                        disabled={!preview || loading}
                        onClick={() => window.print()}
                        size="sm"
                        variant="secondary"
                    >
                        <Icon className="h-4 w-4" name="file" />
                        Print preview
                    </Button>
                </div>
                {loading && !preview ? (
                    <div aria-label="Loading Form 3500 preview" className="space-y-3" role="status">
                        <Skeleton className="h-5 w-48" variant="text" />
                        <Skeleton className="h-24 w-full" />
                        <Skeleton className="h-24 w-full" />
                    </div>
                ) : null}
                {error ? (
                    <ErrorState
                        description={error}
                        onRetry={() => void load()}
                        title="Unable to load the Form 3500 preview"
                    />
                ) : null}
                {preview ? <Form3500PreviewView preview={preview} /> : null}
            </div>
        </Modal>
    );
}
