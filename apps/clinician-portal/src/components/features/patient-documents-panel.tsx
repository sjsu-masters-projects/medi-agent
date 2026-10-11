"use client";

import { SourceFileIcon } from "@/components/features/source-file";
import { useEffect, useState, useSyncExternalStore } from "react";
import { Modal } from "@/components/ui";
import { AiChip } from "@/components/ui/ai-chip";
import { Icon } from "@/components/ui/icons";
import { ProcessingDots } from "@/components/ui/motion";
import { DocumentSummary } from "@/components/features/document-summary";
import { DocumentSourceViewer } from "@/components/features/document-source-viewer";
import {
    DocumentTypeTile,
    ParseStatusBadge,
    ReviewStatusBadge,
} from "@/components/features/document-review-badges";
import {
    approveDocumentReview,
    fetchClinicianDocumentSource,
    rejectDocumentReview,
    retryClinicianDocumentIngestion,
    retryClinicianDocumentSummary,
    fetchExtractedDocumentFacts,
} from "@/services/clinicians";
import {
    type ClinicianPatientDocument,
    DocumentReviewStatus,
    UploaderRole,
    getDocumentTypeLabel,
} from "@/types";
import type { ClinicianDocumentSource, ExtractedDocumentFact } from "@/services/clinicians";

const compactSecondary =
    "ma-press inline-flex h-8 items-center justify-center gap-1.5 rounded-lg border border-line-strong bg-surface px-3 text-[13px] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink disabled:cursor-not-allowed disabled:text-[#94A3B8]";

function subscribeDocumentTarget(change: () => void) {
    window.addEventListener("hashchange", change);
    window.addEventListener("popstate", change);
    return () => { window.removeEventListener("hashchange", change); window.removeEventListener("popstate", change); };
}

interface PatientDocumentsPanelProps {
    documents: ClinicianPatientDocument[];
    patientId: string;
    onRefresh: () => void;
}

const FACT_FIELD_LABELS: Record<string, string> = {
    dosage: "Dose",
    frequency: "Frequency",
    instructions: "Instructions",
    name: "Medication",
    route: "Route",
};

function formatFactField(value: unknown): string {
    if (typeof value === "string" || typeof value === "number") {
        return String(value);
    }
    return JSON.stringify(value) ?? "Not supplied";
}

function factFields(fact: ExtractedDocumentFact): Array<[string, string]> {
    return Object.entries(fact.value).map(([key, value]) => [
        FACT_FIELD_LABELS[key] ?? key.replaceAll("_", " "),
        formatFactField(value),
    ]);
}

function candidateState(fact: ExtractedDocumentFact): string {
    return fact.review_state === "pending_review"
        ? "Pending clinician review"
        : fact.review_state.replaceAll("_", " ");
}

function formatReviewerName(
    reviewer?: { firstName?: string; lastName?: string } | null,
): string | null {
    if (!reviewer) {
        return null;
    }

    const fullName = [reviewer.firstName, reviewer.lastName]
        .filter(Boolean)
        .join(" ")
        .trim();
    return fullName || null;
}

export function PatientDocumentsPanel({
    documents,
    patientId,
    onRefresh,
}: PatientDocumentsPanelProps) {
    const target = useSyncExternalStore(subscribeDocumentTarget, () => window.location.hash.slice(1), () => "");
    const hasTarget = documents.some((doc) => target === `document-${doc.id}`);
    useEffect(() => {
        if (hasTarget) {
            const row = document.getElementById(target);
            row?.scrollIntoView?.({ block: "center" });
            row?.focus({ preventScroll: true });
        }
    }, [target, hasTarget]);
    const [reviewError, setReviewError] = useState<string | null>(null);
    const [reviewingDocumentId, setReviewingDocumentId] = useState<string | null>(null);
    const [retryingDocumentId, setRetryingDocumentId] = useState<string | null>(null);
    const [retryingSummaryId, setRetryingSummaryId] = useState<string | null>(null);
    const [rejectingDocumentId, setRejectingDocumentId] = useState<string | null>(null);
    const [rejectNote, setRejectNote] = useState("");
    const [sourceDocument, setSourceDocument] = useState<ClinicianPatientDocument | null>(null);
    const [source, setSource] = useState<ClinicianDocumentSource | null>(null);
    const [sourceError, setSourceError] = useState<string | null>(null);
    const [sourceLoading, setSourceLoading] = useState(false);
    const [factsDocument, setFactsDocument] = useState<ClinicianPatientDocument | null>(null);
    const [facts, setFacts] = useState<ExtractedDocumentFact[]>([]);
    const [factsLoading, setFactsLoading] = useState(false);
    const [factsError, setFactsError] = useState<string | null>(null);
    const [factsSource, setFactsSource] = useState<ClinicianDocumentSource | null>(null);
    const [factsSourceError, setFactsSourceError] = useState<string | null>(null);
    const [factsSourceLoading, setFactsSourceLoading] = useState(false);
    const [selectedFactId, setSelectedFactId] = useState<string | null>(null);

    async function handleReviewFacts(document: ClinicianPatientDocument) {
        setFactsDocument(document);
        setFacts([]);
        setFactsError(null);
        setFactsSource(null);
        setFactsSourceError(null);
        setSelectedFactId(null);
        setFactsLoading(true);
        setFactsSourceLoading(true);
        try {
            const [factsResult, sourceResult] = await Promise.allSettled([
                fetchExtractedDocumentFacts(patientId, document.id),
                fetchClinicianDocumentSource(patientId, document.id),
            ]);
            if (factsResult.status === "fulfilled") {
                setFacts(factsResult.value);
                setSelectedFactId(factsResult.value[0]?.id ?? null);
            } else {
                setFactsError("Unable to load extracted facts.");
            }
            if (sourceResult.status === "fulfilled") {
                setFactsSource(sourceResult.value);
            } else {
                setFactsSourceError("Unable to open the protected source preview.");
            }
        } finally {
            setFactsLoading(false);
            setFactsSourceLoading(false);
        }
    }

    async function handleOpenSource(document: ClinicianPatientDocument) {
        setSourceDocument(document);
        setSource(null);
        setSourceError(null);
        setSourceLoading(true);
        try {
            setSource(await fetchClinicianDocumentSource(patientId, document.id));
        } catch (error) {
            setSourceError(
                error instanceof Error ? error.message : "Unable to open this source document.",
            );
        } finally {
            setSourceLoading(false);
        }
    }

    async function handleApproveDocument(documentId: string) {
        setReviewError(null);
        setReviewingDocumentId(documentId);
        try {
            await approveDocumentReview(patientId, documentId);
            onRefresh();
        } catch (error) {
            setReviewError(
                error instanceof Error ? error.message : "Unable to approve document review.",
            );
        } finally {
            setReviewingDocumentId(null);
        }
    }

    async function handleRejectDocument() {
        if (!rejectingDocumentId) {
            return;
        }

        setReviewError(null);
        setReviewingDocumentId(rejectingDocumentId);
        try {
            await rejectDocumentReview(patientId, rejectingDocumentId, rejectNote);
            onRefresh();
            setRejectingDocumentId(null);
            setRejectNote("");
        } catch (error) {
            setReviewError(
                error instanceof Error ? error.message : "Unable to reject document review.",
            );
        } finally {
            setReviewingDocumentId(null);
        }
    }

    async function handleRetryDocument(documentId: string) {
        setReviewError(null);
        setRetryingDocumentId(documentId);
        try {
            await retryClinicianDocumentIngestion(patientId, documentId);
            onRefresh();
        } catch (error) {
            setReviewError(
                error instanceof Error ? error.message : "Unable to retry document processing.",
            );
        } finally {
            setRetryingDocumentId(null);
        }
    }

    async function handleRetrySummary(documentId: string) {
        setReviewError(null);
        setRetryingSummaryId(documentId);
        try {
            await retryClinicianDocumentSummary(patientId, documentId);
            onRefresh();
        } catch (error) {
            setReviewError(
                error instanceof Error
                    ? error.message
                    : "Unable to retry the patient explanation.",
            );
        } finally {
            setRetryingSummaryId(null);
        }
    }

    /**
     * Why the patient explanation is missing on a document that parsed successfully.
     *
     * The explanation has its own lifecycle: it never changes the source, the parse
     * result, or any candidate awaiting review. Saying so explicitly matters here,
     * because a clinician seeing an empty summary needs to know the clinical record is
     * intact and that retrying costs nothing but another generation attempt.
     */
    function summaryMessage(document: ClinicianPatientDocument): string | null {
        if (document.aiSummary || document.parseStatus !== "completed") {
            return null;
        }
        if (document.summaryStatus === "failed") {
            return document.summaryFailureCode === "summary_empty"
                ? "The patient explanation came back empty. Extraction and review candidates are unaffected; you can request it again."
                : "The patient explanation is unavailable after repeated attempts. Extraction and review candidates are unaffected; you can request it again.";
        }
        if (document.summaryStatus === "not_required") {
            return "No extracted information in this document needs a patient explanation.";
        }
        if (document.summaryStatus === "processing") {
            return "The patient explanation is being generated. The clinical extraction and review candidates are unaffected.";
        }
        if (document.summaryFailureCode === "provider_unavailable") {
            const attempt = document.summaryAttempts ?? 0;
            const attemptLabel = attempt > 0 ? ` (attempt ${attempt} of 3)` : "";
            if (document.summaryNextAttemptAt) {
                return `The patient explanation will retry automatically${attemptLabel}. The clinical extraction and review candidates are unaffected.`;
            }
            return `The patient explanation is being prepared${attemptLabel}. The clinical extraction and review candidates are unaffected.`;
        }
        return "The patient explanation has not been generated yet. It is queued and does not block review.";
    }

    function parseMessage(document: ClinicianPatientDocument): string | null {
        if (document.parseStatus === "duplicate") {
            return "These exact file contents were already processed for this patient. This copy is stored, but it created no new extracted facts or care-plan proposals. Its upload review is separate; approval does not copy another document's evidence.";
        }
        if (document.parseStatus === "needs_ocr") {
            return "This document has no usable embedded text. It is stored safely; OCR review is required and no candidate was generated.";
        }
        if (document.parseStatus === "needs_evidence_review") {
            return "Extraction did not provide verifiable source evidence. No unverified candidate was generated.";
        }
        if (document.parseStatus === "failed") {
            return "Processing could not be completed. You can retry while attempts remain.";
        }
        return null;
    }

    return (
        <div aria-labelledby="tab-btn-documents" id="tab-panel-documents" role="tabpanel">
            {target.startsWith("document-") && !hasTarget && <p role="status" className="mb-4 text-sm text-muted">The linked document is unavailable in the returned records.</p>}
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-[15px] font-semibold text-ink">Documents</h2>
                <a
                    className="ma-press inline-flex h-[34px] items-center rounded-[9px] bg-primary px-4 text-[13px] font-semibold text-white hover:bg-primary-hover"
                    href={`/patients/${patientId}/upload`}
                    id="clinician-upload-link"
                >
                    + Upload Document
                </a>
            </div>

            {reviewError && (
                <div
                    className="mb-4 flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink"
                    role="alert"
                >
                    <Icon name="alert" aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{reviewError}</span>
                </div>
            )}

            {documents.length === 0 ? (
                <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-line bg-surface px-6 py-12 text-center">
                    <span aria-hidden="true" className="flex h-12 w-12 items-center justify-center rounded-2xl bg-sunken text-muted">
                        <Icon name="folder" className="h-6 w-6" />
                    </span>
                    <p className="text-[15px] font-semibold text-ink">No documents on file</p>
                </div>
            ) : (
                <div className="overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]">
                    {documents.map((doc) => (
                        <div tabIndex={target === `document-${doc.id}` ? -1 : undefined} className="scroll-mt-24 border-b border-line px-5 py-4 last:border-b-0 target:bg-primary-tint/40 target:ring-2 target:ring-inset target:ring-primary" id={`document-${doc.id}`} key={doc.id}>
                            <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
                                <div className="flex min-w-0 flex-1 basis-[18rem] items-start gap-3">
                                    <DocumentTypeTile documentType={doc.documentType} />
                                    <div className="min-w-0">
                                        <div className="flex min-w-0 items-start gap-1.5"><SourceFileIcon className="mt-0.5" name={doc.fileName} /><div className="min-w-0">{doc.displayTitle?.["en-US"] ? <p className="break-words text-sm font-semibold text-ink">{doc.displayTitle["en-US"]}</p> : null}<p className={doc.displayTitle?.["en-US"] ? "break-all font-mono text-[11px] text-muted" : "break-words text-sm font-semibold text-ink"}>{doc.fileName}</p></div></div>
                                        <p className="mt-0.5 text-xs text-muted">
                                            <span className="capitalize">{getDocumentTypeLabel(doc.documentType)}</span> ·{" "}
                                            <time className="font-mono" dateTime={doc.createdAt}>{new Date(doc.createdAt).toLocaleDateString()}</time> ·
                                            uploaded by {doc.uploadedByRole}
                                        </p>
                                        {doc.uploadedByRole === UploaderRole.PATIENT &&
                                            doc.reviewStatus &&
                                            doc.reviewStatus !==
                                                DocumentReviewStatus.PENDING && (
                                                <p className="mt-1 text-xs text-muted">
                                                    {doc.reviewStatus ===
                                                    DocumentReviewStatus.APPROVED
                                                        ? "Approved"
                                                        : "Rejected"}
                                                    {doc.reviewedAt
                                                        ? ` on ${new Date(doc.reviewedAt).toLocaleString()}`
                                                        : ""}
                                                    {formatReviewerName(doc.reviewer)
                                                        ? ` by ${formatReviewerName(doc.reviewer)}`
                                                        : ""}
                                                </p>
                                            )}
                                        {doc.reviewStatus ===
                                            DocumentReviewStatus.REJECTED &&
                                            doc.reviewNote && (
                                                <p className="mt-1.5 max-w-[80ch] border-l-2 border-risk-line pl-2.5 text-xs text-risk-ink">
                                                    Review note: {doc.reviewNote}
                                                </p>
                                            )}
                                    </div>
                                </div>
                                <div className="flex flex-wrap items-center gap-1.5 sm:justify-end">
                                    {doc.uploadedByRole === UploaderRole.PATIENT &&
                                        doc.reviewStatus && (
                                            <ReviewStatusBadge
                                                reviewStatus={doc.reviewStatus}
                                            />
                                        )}
                                    <ParseStatusBadge parseStatus={doc.parseStatus} />
                                </div>
                            </div>

                            <div className="mt-3 space-y-3 sm:pl-12">
                                {parseMessage(doc) && (
                                    <div className={`flex items-start gap-2.5 rounded-xl border px-4 py-3 text-sm ${doc.parseStatus === "failed" ? "border-risk-line bg-risk-soft text-risk-ink" : "border-line bg-surface-2 text-ink-2"}`}>
                                        <Icon name={doc.parseStatus === "failed" ? "alert" : "info"} aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
                                        <div className="min-w-0 flex-1">
                                            <p className="max-w-[80ch]">{parseMessage(doc)}</p>
                                            {doc.parseStatus === "failed" && (
                                                <div className="mt-2 flex flex-wrap items-center gap-3">
                                                    <span className="font-mono text-xs text-muted">
                                                        Attempt {doc.parseAttempts ?? 0} of 3
                                                    </span>
                                                    {(doc.parseAttempts ?? 0) < 3 && (
                                                        <button
                                                            className={compactSecondary}
                                                            disabled={retryingDocumentId === doc.id}
                                                            onClick={() => void handleRetryDocument(doc.id)}
                                                            type="button"
                                                        >
                                                            <Icon name="refresh" aria-hidden="true" className="h-3.5 w-3.5" />
                                                            {retryingDocumentId === doc.id
                                                                ? "Retrying..."
                                                                : "Retry processing"}
                                                        </button>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}

                                <div className="flex flex-wrap items-center gap-2">
                                    <button
                                        className={compactSecondary}
                                        onClick={() => void handleOpenSource(doc)}
                                        type="button"
                                    >
                                        <Icon name="eye" aria-hidden="true" className="h-3.5 w-3.5" />
                                        Open source document
                                    </button>
                                    {doc.parseStatus === "completed" ? (
                                        <button
                                            className={compactSecondary}
                                            onClick={() => void handleReviewFacts(doc)}
                                            type="button"
                                        >
                                            <Icon name="spark" aria-hidden="true" className="h-3.5 w-3.5 text-ai-ink" />
                                            Review extracted facts
                                        </button>
                                    ) : null}
                                    {doc.uploadedByRole === UploaderRole.PATIENT &&
                                        doc.reviewStatus === DocumentReviewStatus.PENDING && (
                                            <div className="flex flex-wrap items-center gap-2 sm:ml-auto">
                                                <button
                                                    className="ma-press inline-flex h-8 items-center justify-center rounded-lg bg-ok px-3 text-[13px] font-semibold text-white hover:bg-ok-strong disabled:cursor-not-allowed disabled:bg-track disabled:text-[#94A3B8]"
                                                    disabled={reviewingDocumentId === doc.id}
                                                    onClick={() => void handleApproveDocument(doc.id)}
                                                    type="button"
                                                >
                                                    {reviewingDocumentId === doc.id
                                                        ? "Saving..."
                                                        : "Approve"}
                                                </button>
                                                <button
                                                    className="ma-press inline-flex h-8 items-center justify-center rounded-lg border border-risk-line bg-surface px-3 text-[13px] font-semibold text-risk-ink hover:bg-risk-soft disabled:cursor-not-allowed disabled:border-line disabled:text-[#94A3B8]"
                                                    disabled={reviewingDocumentId === doc.id}
                                                    onClick={() => {
                                                        setReviewError(null);
                                                        setRejectingDocumentId(doc.id);
                                                        setRejectNote(doc.reviewNote ?? "");
                                                    }}
                                                    type="button"
                                                >
                                                    Reject
                                                </button>
                                            </div>
                                        )}
                                </div>

                                {doc.aiSummary && doc.parseStatus !== "duplicate" ? (
                                    <DocumentSummary
                                        documentId={doc.id}
                                        existingAnnotation={doc.clinicianAnnotation}
                                        patientId={patientId}
                                        summaryText={doc.aiSummary}
                                    />
                                ) : (
                                    summaryMessage(doc) && (
                                        <div className="rounded-xl border border-line bg-surface-2 px-4 py-3">
                                            <div className="flex items-start gap-2.5">
                                                <span aria-hidden="true" className="mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-ai-tint text-ai-ink">
                                                    <Icon name="spark" className="h-3 w-3" />
                                                </span>
                                                <p className="max-w-[80ch] text-sm text-ink-2">
                                                    {summaryMessage(doc)}
                                                    {doc.summaryStatus === "processing" ? (
                                                        <span className="ml-2 inline-flex align-middle"><ProcessingDots className="bg-ai-ink" /></span>
                                                    ) : null}
                                                </p>
                                            </div>
                                            {doc.summaryStatus === "failed" && (
                                                <button
                                                    className={`${compactSecondary} ml-[30px] mt-3`}
                                                    disabled={retryingSummaryId === doc.id}
                                                    onClick={() => void handleRetrySummary(doc.id)}
                                                    type="button"
                                                >
                                                    <Icon name="refresh" aria-hidden="true" className="h-3.5 w-3.5" />
                                                    {retryingSummaryId === doc.id
                                                        ? "Requesting..."
                                                        : "Retry patient explanation"}
                                                </button>
                                            )}
                                        </div>
                                    )
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}

            <Modal
                onClose={() => {
                    if (reviewingDocumentId) {
                        return;
                    }
                    setRejectingDocumentId(null);
                    setRejectNote("");
                }}
                open={Boolean(rejectingDocumentId)}
                title="Reject patient upload"
            >
                <div className="space-y-4">
                    <p className="text-sm text-ink-2">
                        Add an optional note to explain why this patient-uploaded
                        document needs follow-up or correction.
                    </p>
                    <label className="block text-[13px] font-medium text-ink-2">
                        Review note
                        <textarea
                            className="mt-1.5 min-h-28 w-full rounded-[10px] border border-line-strong bg-surface px-3.5 py-2.5 text-sm text-ink outline-none transition placeholder:text-[#94A3B8] focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)]"
                            onChange={(event) => setRejectNote(event.target.value)}
                            placeholder="Optional note for the care team."
                            value={rejectNote}
                        />
                    </label>
                    <div className="flex justify-end gap-2">
                        <button
                            className="ma-press h-[34px] rounded-[9px] border border-line-strong bg-surface px-4 text-[13px] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink"
                            onClick={() => {
                                setRejectingDocumentId(null);
                                setRejectNote("");
                            }}
                            type="button"
                        >
                            Cancel
                        </button>
                        <button
                            className="ma-press h-[34px] rounded-[9px] bg-risk px-4 text-[13px] font-semibold text-white hover:bg-risk-strong disabled:cursor-not-allowed disabled:bg-track disabled:text-[#94A3B8]"
                            disabled={!rejectingDocumentId || reviewingDocumentId !== null}
                            onClick={() => void handleRejectDocument()}
                            type="button"
                        >
                            {reviewingDocumentId ? "Saving..." : "Confirm rejection"}
                        </button>
                    </div>
                </div>
            </Modal>

            <Modal
                onClose={() => {
                    if (!factsLoading) {
                        setFactsDocument(null);
                        setFacts([]);
                        setFactsError(null);
                        setFactsSource(null);
                        setFactsSourceError(null);
                        setSelectedFactId(null);
                    }
                }}
                contentClassName="max-w-6xl"
                open={Boolean(factsDocument)}
                title={factsDocument ? `Extracted facts — ${factsDocument.fileName}` : "Extracted facts"}
            >
                <div className="space-y-3">
                    <p className="flex items-start gap-2.5 rounded-xl border border-warn-line bg-warn-soft px-4 py-3 text-sm font-semibold text-warn-ink">
                        <Icon name="alert" aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
                        <span>Pending clinician review — these are evidence-backed candidates, not clinical truth.</span>
                    </p>
                    {factsLoading ? <p className="flex items-center gap-2 text-sm text-ink-2">Loading extracted facts…<ProcessingDots /></p> : null}
                    {factsError ? <p className="flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink"><Icon name="alert" aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" /><span>{factsError}</span></p> : null}
                    {!factsLoading && !factsError && facts.length === 0 ? <p className="text-sm text-ink-2">No grounded facts were extracted from this document.</p> : null}
                    {facts.length > 0 ? (
                        <div className="grid gap-4 lg:grid-cols-2">
                            <div className="space-y-2.5">
                                <AiChip>AI-extracted candidates</AiChip>
                                <div className="space-y-2.5" role="list" aria-label="Extracted fact candidates">
                                    {facts.map((fact) => (
                                        <button
                                            aria-pressed={selectedFactId === fact.id}
                                            className={`ma-press w-full rounded-xl border p-3.5 text-left ${selectedFactId === fact.id ? "border-primary bg-primary-tint" : "border-line bg-surface hover:bg-surface-2"}`}
                                            key={fact.id}
                                            onClick={() => setSelectedFactId(fact.id)}
                                            type="button"
                                        >
                                            <div className="flex items-start justify-between gap-3">
                                                <div>
                                                    <p className="text-sm font-semibold capitalize text-ink">{fact.fact_type}</p>
                                                    <p className="mt-1 text-xs font-medium text-warn-ink">{candidateState(fact)}</p>
                                                </div>
                                                <span className="whitespace-nowrap rounded-[7px] bg-warn-soft px-2 py-1 text-xs font-medium text-warn-ink">
                                                    {fact.confidence_score === null || fact.confidence_score === undefined ? "Confidence unavailable" : <><span className="font-mono">{Math.round(fact.confidence_score * 100)}%</span> confidence</>}
                                                </span>
                                            </div>
                                            <dl className="mt-3 space-y-1 text-sm text-ink-2">
                                                {factFields(fact).map(([label, value]) => (
                                                    <div className="grid grid-cols-[7rem_1fr] gap-2" key={label}>
                                                        <dt className="text-[13px] font-medium capitalize text-muted">{label}</dt>
                                                        <dd className="break-words">{value}</dd>
                                                    </div>
                                                ))}
                                            </dl>
                                            {fact.citations?.[0]?.excerpt ? <p className="mt-3 border-l-2 border-line-strong pl-3 text-xs text-ink-2">“{fact.citations[0].excerpt}”{fact.citations[0].location?.page ? ` · page ${fact.citations[0].location.page}` : ""}</p> : null}
                                        </button>
                                    ))}
                                </div>
                            </div>
                            <div className="min-h-80 space-y-3">
                                <p className="text-sm font-semibold text-ink">Protected source preview</p>
                                {factsSourceLoading ? <p className="flex items-center gap-2 text-sm text-muted">Loading source preview…<ProcessingDots /></p> : null}
                                {factsSourceError ? <p className="flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink"><Icon name="alert" aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" /><span>{factsSourceError}</span></p> : null}
                                {factsSource ? (
                                    <DocumentSourceViewer
                                        initialPage={facts.find((fact) => fact.id === selectedFactId)?.citations?.[0]?.location?.page ?? 1}
                                        fileName={factsSource.file_name}
                                        previewMimeType={factsSource.preview_mime_type}
                                        previewStatus={factsSource.preview_status}
                                        previewUrl={factsSource.preview_url}
                                        sourceMimeType={factsSource.mime_type}
                                        sourceUrl={factsSource.file_url}
                                    />
                                ) : null}
                            </div>
                        </div>
                    ) : null}
                </div>
            </Modal>

            <Modal
                onClose={() => {
                    if (sourceLoading) return;
                    setSourceDocument(null);
                    setSource(null);
                    setSourceError(null);
                }}
                open={Boolean(sourceDocument)}
                title={sourceDocument?.fileName ?? "Source document"}
            >
                {sourceLoading ? <p className="flex items-center gap-2 text-sm text-ink-2">Loading source document…<ProcessingDots /></p> : null}
                {sourceError ? <p className="flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink"><Icon name="alert" aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" /><span>{sourceError}</span></p> : null}
                {source && sourceDocument ? (
                    <DocumentSourceViewer
                        fileName={source.file_name}
                        previewMimeType={source.preview_mime_type}
                        previewStatus={source.preview_status}
                        previewUrl={source.preview_url}
                        sourceMimeType={source.mime_type}
                        sourceUrl={source.file_url}
                    />
                ) : null}
            </Modal>
        </div>
    );
}
