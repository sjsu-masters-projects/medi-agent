"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
    HiMiniSpeakerWave,
    HiOutlineBeaker,
    HiOutlineClipboardDocumentList,
    HiOutlineDocumentText,
    HiOutlineFolder,
} from "react-icons/hi2";
import { DocumentCard, PdfViewer } from "@/components/features";
import { PageHeader } from "@/components/layouts";
import { Button, EmptyState, ErrorState, Modal, ProgressBar } from "@/components/ui";
import { api } from "@/services/api";
import {
    buildDocumentChatHref,
    buildSuggestedDocumentQuestion,
    storePendingChatDocumentContext,
} from "@/services/chat-bridge";
import { playAssistantVoiceResponse } from "@/services/browser-voice";
import { inferDocumentType, type DocumentApiRecord } from "@/services/documents";
import { uploadDocumentToStorage } from "@/services/storage";
import type { RootState } from "@/store/store";
import {
    DEFAULT_LOCALE,
    DocumentParseStatus,
    DocumentType,
    Locale,
    SUPPORTED_LOCALES,
    getLocaleLabel,
    normalizeLocale,
    type Document,
} from "@/types";
import { useSelector } from "react-redux";

type PortalDocument = Document & { icon: ReactNode; provider: string };

const EXPLANATION_UNAVAILABLE_MESSAGE =
    "Translation is currently unavailable. Please try again later.";
const PARSING_IN_PROGRESS_MESSAGE =
    "Processing this document. AI summary will appear when parsing completes.";
const PARSING_FAILED_FALLBACK_MESSAGE = "This document could not be processed.";
const PARSING_TIMEOUT_MESSAGE =
    "Timed out while waiting for document processing to finish.";

function addTrackedDocumentId(current: Set<string>, documentId: string) {
    const next = new Set(current);
    next.add(documentId);
    return next;
}

function removeTrackedDocumentId(current: Set<string>, documentId: string) {
    const next = new Set(current);
    next.delete(documentId);
    return next;
}

function getDocumentIcon(documentType: DocumentType) {
    switch (documentType) {
        case DocumentType.LAB_REPORT:
            return <HiOutlineBeaker />;
        case DocumentType.PRESCRIPTION:
            return <HiOutlineClipboardDocumentList />;
        case DocumentType.DISCHARGE_SUMMARY:
            return <HiOutlineDocumentText />;
        case DocumentType.DIAGNOSTIC_REPORT:
            return <HiOutlineBeaker />;
        default:
            return <HiOutlineDocumentText />;
    }
}

function mapDocument(record: DocumentApiRecord): PortalDocument {
    return {
        aiSummary: record.ai_summary ?? undefined,
        createdAt: record.created_at,
        documentType: record.document_type,
        fileName: record.file_name,
        fileSizeBytes: record.file_size_bytes,
        fileUrl: record.file_url,
        icon: getDocumentIcon(record.document_type),
        id: record.id,
        mimeType: record.mime_type,
        parseAttempts: record.parse_attempts ?? 0,
        parseError: record.parse_error ?? undefined,
        parseStatus:
            record.parse_status
            ?? (record.parsed ? DocumentParseStatus.COMPLETED : DocumentParseStatus.NONE),
        parsed: record.parsed,
        patientId: record.patient_id,
        provider: record.source_clinic ?? "Care team",
        sourceClinic: record.source_clinic ?? undefined,
        uploadedBy: record.uploaded_by,
        uploadedByRole: record.uploaded_by_role,
        visibility: record.visibility,
    };
}

function getDocumentStatus(document: PortalDocument) {
    if (document.parseStatus === "processing" || document.parseStatus === "pending") {
        return { label: "Processing...", variant: "warning" as const };
    }
    if (document.parseStatus === "failed") {
        return { label: "Parse failed", variant: "danger" as const };
    }
    if (document.parsed && document.aiSummary) {
        return { label: "AI Summary", variant: "info" as const };
    }
    return null;
}

export default function RecordsPage() {
    const router = useRouter();
    const [documents, setDocuments] = useState<PortalDocument[]>([]);
    const [selectedDocument, setSelectedDocument] = useState<PortalDocument | null>(null);
    const [deleteConfirming, setDeleteConfirming] = useState(false);
    const [deleteError, setDeleteError] = useState<string | null>(null);
    const [deletingDocumentId, setDeletingDocumentId] = useState<string | null>(null);
    const [explanationLang, setExplanationLang] = useState<Locale>(DEFAULT_LOCALE);
    const [explanationText, setExplanationText] = useState<string | null>(null);
    const [explanationLoading, setExplanationLoading] = useState(false);
    const [loading, setLoading] = useState(true);
    const [pageError, setPageError] = useState<string | null>(null);
    const [parseError, setParseError] = useState<string | null>(null);
    const [readbackActive, setReadbackActive] = useState(false);
    const [parsingDocIds, setParsingDocIds] = useState<Set<string>>(new Set());
    const [uploadProgress, setUploadProgress] = useState(0);
    const [uploading, setUploading] = useState(false);
    const fileInputRef = useRef<HTMLInputElement | null>(null);
    const { accessToken, user } = useSelector((state: RootState) => state.auth);

    const loadDocuments = useCallback(async () => {
        if (!accessToken) {
            return;
        }

        setLoading(true);
        try {
            const result = await api.get<DocumentApiRecord[]>("/api/v1/documents/", {
                token: accessToken,
            });
            setDocuments(result.map(mapDocument));
            setPageError(null);
        } catch (error) {
            setPageError((error as Error).message);
        } finally {
            setLoading(false);
        }
    }, [accessToken]);

    const openDocument = useCallback((document: PortalDocument) => {
        setSelectedDocument(document);
        setDeleteConfirming(false);
        setDeleteError(null);
        setExplanationLang(DEFAULT_LOCALE);
        setExplanationLoading(false);

        if (document.parseStatus === "failed") {
            setExplanationText(document.parseError ?? PARSING_FAILED_FALLBACK_MESSAGE);
            return;
        }

        if (
            document.parseStatus === "pending"
            || document.parseStatus === "processing"
            || parsingDocIds.has(document.id)
        ) {
            setExplanationText(PARSING_IN_PROGRESS_MESSAGE);
            return;
        }

        setExplanationText(document.aiSummary ?? null);
    }, [parsingDocIds]);

    const closeDocumentModal = useCallback(() => {
        setSelectedDocument(null);
        setDeleteConfirming(false);
        setDeleteError(null);
    }, []);

    useEffect(() => {
        if (!accessToken) {
            return;
        }

        void loadDocuments();
    }, [accessToken, loadDocuments]);

    async function pollForParsedStatus(docId: string) {
        setParsingDocIds((current) => addTrackedDocumentId(current, docId));

        for (let attempt = 0; attempt < 10; attempt += 1) {
            await new Promise((resolve) => window.setTimeout(resolve, 3000));

            try {
                const record = await api.get<DocumentApiRecord>(
                    `/api/v1/documents/${docId}`,
                    { token: accessToken ?? undefined },
                );
                const nextDocument = mapDocument(record);

                setDocuments((current) =>
                    current.map((document) =>
                        document.id === docId ? nextDocument : document,
                    ),
                );

                if (nextDocument.parsed || nextDocument.parseStatus === "completed") {
                    setParsingDocIds((current) => removeTrackedDocumentId(current, docId));
                    return;
                }

                if (nextDocument.parseStatus === "failed") {
                    setParseError(
                        nextDocument.parseError
                            ? `Failed to process document: ${nextDocument.parseError}`
                            : "Failed to process document.",
                    );
                    setParsingDocIds((current) => removeTrackedDocumentId(current, docId));
                    return;
                }
            } catch {
                // Keep polling until attempts are exhausted.
            }
        }

        setParsingDocIds((current) => removeTrackedDocumentId(current, docId));
        setParseError(PARSING_TIMEOUT_MESSAGE);
    }

    async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
        const file = event.target.files?.[0];
        if (!file) {
            return;
        }

        if (!accessToken || !user) {
            setPageError("Please sign in again before uploading a document.");
            return;
        }

        setPageError(null);
        setParseError(null);
        setUploading(true);
        for (const value of [20, 45, 70, 100]) {
            setUploadProgress(value);
            await new Promise((resolve) => window.setTimeout(resolve, 150));
        }

        try {
            const filePath = await uploadDocumentToStorage({
                file,
                patientId: user.id,
                token: accessToken,
            });
            const created = await api.post<DocumentApiRecord>(
                "/api/v1/documents/",
                {
                    document_type: inferDocumentType(file),
                    file_name: file.name,
                    file_path: filePath,
                    file_size_bytes: file.size,
                    mime_type: file.type || "application/octet-stream",
                },
                { token: accessToken },
            );
            const nextDocument = mapDocument(created);
            setDocuments((current) => [nextDocument, ...current]);
            void pollForParsedStatus(nextDocument.id);
        } catch (error) {
            setPageError((error as Error).message || "Upload failed. Please try again.");
        } finally {
            setUploading(false);
            setUploadProgress(0);
            event.target.value = "";
        }
    }

    async function handleLanguageChange(language: Locale) {
        const nextLocale = normalizeLocale(language);
        setExplanationLang(nextLocale);
        if (
            nextLocale === DEFAULT_LOCALE
            && selectedDocument?.parseStatus === DocumentParseStatus.COMPLETED
        ) {
            setExplanationText(selectedDocument.aiSummary ?? null);
            return;
        }
        if (!selectedDocument) {
            return;
        }

        if (selectedDocument.parseStatus !== DocumentParseStatus.COMPLETED) {
            return;
        }

        setExplanationLoading(true);
        try {
            const result = await api.post<{ summary: string }>(
                `/api/v1/documents/${selectedDocument.id}/explain`,
                { language: nextLocale },
                { token: accessToken ?? undefined },
            );
            setExplanationText(result.summary);
        } catch {
            setExplanationText(EXPLANATION_UNAVAILABLE_MESSAGE);
        } finally {
            setExplanationLoading(false);
        }
    }

    function handleAskAboutDocument() {
        if (!selectedDocument) {
            return;
        }

        storePendingChatDocumentContext({
            documentId: selectedDocument.id,
            documentName: selectedDocument.fileName,
            documentType: selectedDocument.documentType,
            preferredLanguage: explanationLang,
            provider: selectedDocument.provider,
            suggestedQuestion: buildSuggestedDocumentQuestion({
                documentName: selectedDocument.fileName,
                documentType: selectedDocument.documentType,
                preferredLanguage: explanationLang,
                provider: selectedDocument.provider,
            }),
            summary: explanationText ?? selectedDocument.aiSummary,
        });

        closeDocumentModal();
        router.push(buildDocumentChatHref(selectedDocument.id));
    }

    async function handleDeleteDocument() {
        if (!selectedDocument) {
            return;
        }

        if (!accessToken) {
            setDeleteError("Please sign in again before deleting this document.");
            return;
        }

        setDeletingDocumentId(selectedDocument.id);
        setDeleteError(null);
        try {
            await api.delete<void>(`/api/v1/documents/${selectedDocument.id}`, {
                token: accessToken,
            });
            setDocuments((current) =>
                current.filter((document) => document.id !== selectedDocument.id),
            );
            setParsingDocIds((current) => removeTrackedDocumentId(current, selectedDocument.id));
            closeDocumentModal();
        } catch (error) {
            setDeleteError((error as Error).message || "Delete failed. Please try again.");
        } finally {
            setDeletingDocumentId(null);
        }
    }

    function handleReadSummary() {
        const text = explanationText ?? selectedDocument?.aiSummary;
        if (!text) {
            return;
        }

        const stop = playAssistantVoiceResponse({
            language: explanationLang,
            onEnd: () => setReadbackActive(false),
            onStart: () => setReadbackActive(true),
            text,
        });

        if (!stop) {
            setReadbackActive(false);
        }
    }

    const processingCount = documents.filter(
        (document) =>
            parsingDocIds.has(document.id)
            || document.parseStatus === "pending"
            || document.parseStatus === "processing",
    ).length;
    const isDeletingSelectedDocument = deletingDocumentId === selectedDocument?.id;

    return (
        <div className="patient-page space-y-4 pb-8">
            <PageHeader
                rightAction={<Button onClick={() => fileInputRef.current?.click()} variant="secondary">Upload</Button>}
                subtitle="View clinical records and plain-language explanations."
                title="My Records"
            />
            <input className="hidden" onChange={handleFileChange} ref={fileInputRef} type="file" />
            <div className="patient-stack -mt-4 space-y-4 px-5">
                <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-[1.4rem] bg-white/90 px-4 py-4 shadow-[0_12px_28px_rgba(37,52,82,0.08)] ring-1 ring-[#eaded3]">
                        <p className="text-xs font-semibold uppercase tracking-wide text-[#7b8798]">Stored</p>
                        <p className="mt-1 text-3xl font-bold text-[#17233a]">{documents.length}</p>
                        <p className="text-sm text-[#5b6b83]">Secure records</p>
                    </div>
                    <div className="rounded-[1.4rem] bg-[#e7f4f1] px-4 py-4 shadow-[0_12px_28px_rgba(20,116,101,0.10)] ring-1 ring-[#b9ded6]">
                        <p className="text-xs font-semibold uppercase tracking-wide text-[#147465]">
                            {processingCount > 0 ? "Parsing" : "AI Ready"}
                        </p>
                        <p className="mt-1 text-3xl font-bold text-[#17233a]">
                            {processingCount > 0
                                ? processingCount
                                : documents.filter((document) => document.parsed && document.aiSummary).length}
                        </p>
                        <p className="text-sm text-[#48627c]">
                            {processingCount > 0 ? "Documents in progress" : "Summaries available"}
                        </p>
                    </div>
                </div>
                {uploading ? <ProgressBar value={uploadProgress} /> : null}
                {pageError && documents.length === 0 ? (
                    <ErrorState
                        description={pageError}
                        onRetry={() => void loadDocuments()}
                        title="Could not load records"
                    />
                ) : null}
                {pageError && documents.length > 0 ? (
                    <ErrorState
                        description={pageError}
                        onRetry={() => {
                            setPageError(null);
                            void loadDocuments();
                        }}
                        title="Action failed"
                    />
                ) : null}
                {parseError ? (
                    <ErrorState
                        description={parseError}
                        onRetry={() => {
                            setParseError(null);
                            fileInputRef.current?.click();
                        }}
                        title="Document processing failed"
                    />
                ) : null}
                {loading ? (
                    <p className="rounded-2xl bg-white/80 px-4 py-3 text-sm font-medium text-[#5b6b83] shadow-sm ring-1 ring-[#eaded3]">Loading documents...</p>
                ) : null}
                {!loading && !pageError && documents.length === 0 ? (
                    <EmptyState description="Upload PDFs or images from your clinic visits." icon={<HiOutlineFolder />} title="No records yet" />
                ) : null}
                {documents.map((document) => {
                    const displayDocument = parsingDocIds.has(document.id)
                        ? { ...document, parseStatus: "processing" as const }
                        : document;
                    const status = getDocumentStatus(displayDocument);

                    return (
                        <DocumentCard
                            date={new Date(document.createdAt).toLocaleDateString(explanationLang, { month: "short", day: "numeric", year: "numeric" })}
                            hasAiSummary={document.parsed && Boolean(document.aiSummary)}
                            icon={document.icon}
                            id={document.id}
                            key={document.id}
                            name={document.fileName}
                            onClick={() => openDocument(document)}
                            provider={document.provider}
                            statusLabel={status?.label}
                            statusVariant={status?.variant}
                            type={document.documentType.replaceAll("_", " ")}
                        />
                    );
                })}
            </div>
            <Modal onClose={closeDocumentModal} open={Boolean(selectedDocument)} title={selectedDocument?.fileName ?? "Record details"}>
                <div className="space-y-4">
                    <div className="rounded-2xl bg-[#fff7ed] px-4 py-3 ring-1 ring-[#eaded3]">
                        <p className="text-xs font-semibold uppercase tracking-wide text-[#7b8798]">Source</p>
                        <p className="mt-1 text-sm font-semibold text-[#30415f]">{selectedDocument?.provider}</p>
                    </div>
                    {selectedDocument?.mimeType === "application/pdf" && selectedDocument.fileUrl ? (
                        <PdfViewer documentUrl={selectedDocument.fileUrl} height="400px" />
                    ) : null}
                    <div className="rounded-3xl border border-[#b9ded6] bg-[#e7f4f1] p-4">
                        <div className="flex items-center justify-between gap-3">
                            <p className="text-xs font-semibold uppercase tracking-wide text-[#147465]">Explain this to me</p>
                            <div className="flex items-center gap-2">
                                <button
                                    aria-label="Read summary aloud"
                                    className="flex h-11 w-11 items-center justify-center rounded-xl border border-[#b9ded6] bg-white text-[#147465] transition hover:bg-[#f8fffd] disabled:cursor-not-allowed disabled:text-[#8aa39e]"
                                    disabled={!explanationText && !selectedDocument?.aiSummary}
                                    onClick={handleReadSummary}
                                    type="button"
                                >
                                    <HiMiniSpeakerWave className="h-5 w-5" />
                                </button>
                                <select
                                    className="min-h-11 rounded-xl border border-[#b9ded6] bg-white px-3 py-2 text-sm font-medium text-[#147465] outline-none focus:ring-4 focus:ring-[#147465]/15"
                                    onChange={(event) => handleLanguageChange(event.target.value as Locale)}
                                    value={explanationLang}
                                >
                                    {SUPPORTED_LOCALES.map((locale) => (
                                        <option key={locale} value={locale}>
                                            {getLocaleLabel(locale)}
                                        </option>
                                    ))}
                                </select>
                            </div>
                        </div>
                        <p className="mt-3 text-base leading-7 text-[#30415f]">
                            {explanationLoading
                                ? "Translating..."
                                : readbackActive
                                  ? `Reading in ${getLocaleLabel(explanationLang)}...`
                                : explanationText ?? "AI summary will appear here after parsing completes."}
                        </p>
                    </div>
                    <div className="space-y-3">
                        <Button fullWidth onClick={handleAskAboutDocument} size="lg">
                            Ask about this document
                        </Button>
                        <div className="grid grid-cols-2 gap-3">
                            <Button fullWidth onClick={() => setSelectedDocument(null)} variant="secondary">
                                Close
                            </Button>
                            <Button fullWidth onClick={() => fileInputRef.current?.click()} variant="secondary">
                                Upload another
                            </Button>
                        </div>
                        {deleteError ? (
                            <ErrorState
                                description={deleteError}
                                onRetry={() => void handleDeleteDocument()}
                                title="Could not delete document"
                            />
                        ) : null}
                        {deleteConfirming ? (
                            <div className="rounded-3xl border border-[#f0b8ae] bg-[#fff2ef] p-4">
                                <p className="text-base font-bold text-[#7f2c23]">Delete this document?</p>
                                <p className="mt-1 text-sm leading-6 text-[#9b4539]">
                                    This removes the record from your documents. Existing care-plan items created from prior parsing are not removed.
                                </p>
                                <div className="mt-3 grid grid-cols-2 gap-3">
                                    <Button
                                        disabled={isDeletingSelectedDocument}
                                        fullWidth
                                        onClick={() => setDeleteConfirming(false)}
                                        variant="secondary"
                                    >
                                        Cancel
                                    </Button>
                                    <Button
                                        disabled={isDeletingSelectedDocument}
                                        fullWidth
                                        onClick={() => void handleDeleteDocument()}
                                        variant="danger"
                                    >
                                        {isDeletingSelectedDocument ? "Deleting" : "Delete permanently"}
                                    </Button>
                                </div>
                            </div>
                        ) : (
                            <Button
                                disabled={isDeletingSelectedDocument}
                                fullWidth
                                onClick={() => setDeleteConfirming(true)}
                                variant="danger"
                            >
                                Delete document
                            </Button>
                        )}
                    </div>
                </div>
            </Modal>
        </div>
    );
}
