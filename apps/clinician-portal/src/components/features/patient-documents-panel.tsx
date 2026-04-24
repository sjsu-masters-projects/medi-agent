"use client";

import { useState } from "react";
import { HiOutlineDocumentText } from "react-icons/hi2";
import { Modal } from "@/components/ui";
import { DocumentSummary } from "@/components/features/document-summary";
import {
    ParseStatusBadge,
    ReviewStatusBadge,
} from "@/components/features/document-review-badges";
import {
    approveDocumentReview,
    rejectDocumentReview,
} from "@/services/clinicians";
import {
    type ClinicianPatientDocument,
    DocumentReviewStatus,
    UploaderRole,
    getDocumentTypeLabel,
} from "@/types";

interface PatientDocumentsPanelProps {
    documents: ClinicianPatientDocument[];
    patientId: string;
    onRefresh: () => void;
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
    const [reviewError, setReviewError] = useState<string | null>(null);
    const [reviewingDocumentId, setReviewingDocumentId] = useState<string | null>(null);
    const [rejectingDocumentId, setRejectingDocumentId] = useState<string | null>(null);
    const [rejectNote, setRejectNote] = useState("");

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

    return (
        <div aria-labelledby="tab-btn-documents" id="tab-panel-documents" role="tabpanel">
            <div className="mb-6 flex items-center justify-between">
                <h2 className="text-lg font-semibold text-gray-900">Documents</h2>
                <a
                    className="rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
                    href={`/patients/${patientId}/upload`}
                    id="clinician-upload-link"
                >
                    + Upload Document
                </a>
            </div>

            {reviewError && (
                <div
                    className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
                    role="alert"
                >
                    {reviewError}
                </div>
            )}

            {documents.length === 0 ? (
                <div className="flex h-40 items-center justify-center text-sm text-gray-400">
                    No documents on file
                </div>
            ) : (
                <div className="space-y-4">
                    {documents.map((doc) => (
                        <div className="rounded-xl border border-gray-200 bg-white" key={doc.id}>
                            <div className="flex items-center justify-between border-b border-gray-100 px-5 py-4">
                                <div className="flex items-center gap-3">
                                    <HiOutlineDocumentText
                                        aria-hidden="true"
                                        className="h-5 w-5 text-blue-500"
                                    />
                                    <div>
                                        <p className="text-sm font-semibold text-gray-900">
                                            {doc.fileName}
                                        </p>
                                        <div className="flex flex-wrap items-center gap-2 text-xs text-gray-400">
                                            <span>
                                                {getDocumentTypeLabel(doc.documentType)} ·{" "}
                                                {new Date(doc.createdAt).toLocaleDateString()} ·
                                                uploaded by {doc.uploadedByRole}
                                            </span>
                                            {doc.uploadedByRole === UploaderRole.PATIENT &&
                                                doc.reviewStatus && (
                                                    <ReviewStatusBadge
                                                        reviewStatus={doc.reviewStatus}
                                                    />
                                                )}
                                        </div>
                                        {doc.uploadedByRole === UploaderRole.PATIENT &&
                                            doc.reviewStatus &&
                                            doc.reviewStatus !==
                                                DocumentReviewStatus.PENDING && (
                                                <p className="mt-1 text-xs text-gray-500">
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
                                                <p className="mt-1 text-xs text-rose-600">
                                                    Review note: {doc.reviewNote}
                                                </p>
                                            )}
                                    </div>
                                </div>
                                <ParseStatusBadge parseStatus={doc.parseStatus} />
                            </div>

                            {doc.uploadedByRole === UploaderRole.PATIENT &&
                                doc.reviewStatus === DocumentReviewStatus.PENDING && (
                                    <div className="flex flex-wrap items-center gap-3 border-b border-gray-100 px-5 py-4">
                                        <button
                                            className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                                            disabled={reviewingDocumentId === doc.id}
                                            onClick={() => void handleApproveDocument(doc.id)}
                                            type="button"
                                        >
                                            {reviewingDocumentId === doc.id
                                                ? "Saving..."
                                                : "Approve"}
                                        </button>
                                        <button
                                            className="rounded-lg border border-rose-200 px-3 py-2 text-sm font-semibold text-rose-600 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-60"
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

                            {doc.aiSummary && (
                                <div className="px-5 py-4">
                                    <DocumentSummary
                                        documentId={doc.id}
                                        existingAnnotation={doc.clinicianAnnotation}
                                        patientId={patientId}
                                        summaryText={doc.aiSummary}
                                    />
                                </div>
                            )}
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
                    <p className="text-sm text-gray-600">
                        Add an optional note to explain why this patient-uploaded
                        document needs follow-up or correction.
                    </p>
                    <label className="block text-sm font-medium text-gray-700">
                        Review note
                        <textarea
                            className="mt-2 min-h-28 w-full rounded-xl border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500"
                            onChange={(event) => setRejectNote(event.target.value)}
                            placeholder="Optional note for the care team."
                            value={rejectNote}
                        />
                    </label>
                    <div className="flex justify-end gap-3">
                        <button
                            className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
                            onClick={() => {
                                setRejectingDocumentId(null);
                                setRejectNote("");
                            }}
                            type="button"
                        >
                            Cancel
                        </button>
                        <button
                            className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
                            disabled={!rejectingDocumentId || reviewingDocumentId !== null}
                            onClick={() => void handleRejectDocument()}
                            type="button"
                        >
                            {reviewingDocumentId ? "Saving..." : "Confirm rejection"}
                        </button>
                    </div>
                </div>
            </Modal>
        </div>
    );
}
