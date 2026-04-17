"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { HiOutlineBeaker, HiOutlineClipboardDocumentList, HiOutlineDocumentText, HiOutlineFolder } from "react-icons/hi2";
import { DocumentCard, PdfViewer } from "@/components/features";
import { PageHeader } from "@/components/layouts";
import { Button, EmptyState, ErrorState, Modal, ProgressBar } from "@/components/ui";
import { api } from "@/services/api";
import {
    buildDocumentChatHref,
    buildSuggestedDocumentQuestion,
    storePendingChatDocumentContext,
} from "@/services/chat-bridge";
import { uploadDocumentToStorage } from "@/services/storage";
import type { RootState } from "@/store/store";
import {
    DocumentType,
    Language,
    type Document,
} from "@/types";
import { useSelector } from "react-redux";

type PortalDocument = Document & { icon: ReactNode; provider: string };

interface DocumentApiRecord {
    id: string;
    patient_id: string;
    uploaded_by: string;
    uploaded_by_role: Document["uploadedByRole"];
    document_type: DocumentType;
    file_name: string;
    file_url: string;
    mime_type: string;
    file_size_bytes: number;
    parsed: boolean;
    ai_summary?: string | null;
    parse_status?: "none" | "pending" | "processing" | "completed" | "failed";
    parse_error?: string | null;
    parse_attempts?: number;
    source_clinic?: string | null;
    visibility: Document["visibility"];
    created_at: string;
}

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
        parseStatus: record.parse_status ?? (record.parsed ? "completed" : "none"),
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

function inferDocumentType(file: File): DocumentType {
    const normalizedName = file.name.toLowerCase();
    const normalizedType = file.type.toLowerCase();

    if (normalizedType.includes("pdf") || normalizedName.endsWith(".pdf")) {
        return DocumentType.LAB_REPORT;
    }
    if (normalizedType.startsWith("image/")) {
        return DocumentType.DIAGNOSTIC_REPORT;
    }
    if (normalizedType === "text/csv" || normalizedName.endsWith(".csv")) {
        return DocumentType.LAB_REPORT;
    }
    if (normalizedType === "text/plain" || normalizedName.endsWith(".txt")) {
        return DocumentType.DISCHARGE_SUMMARY;
    }
    return DocumentType.OTHER;
}

export default function RecordsPage() {
    const router = useRouter();
    const [documents, setDocuments] = useState<PortalDocument[]>([]);
    const [selectedDocument, setSelectedDocument] = useState<PortalDocument | null>(null);
    const [explanationLang, setExplanationLang] = useState<Language>(Language.EN);
    const [explanationText, setExplanationText] = useState<string | null>(null);
    const [explanationLoading, setExplanationLoading] = useState(false);
    const [loading, setLoading] = useState(true);
    const [pageError, setPageError] = useState<string | null>(null);
    const [parseError, setParseError] = useState<string | null>(null);
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
        setExplanationLang(Language.EN);
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

<<<<<<< HEAD
    async function handleLanguageChange(language: Language) {
        setExplanationLang(language);
        if (language === Language.EN && selectedDocument?.parseStatus === "completed") {
            setExplanationText(selectedDocument.aiSummary ?? null);
            return;
        }

=======
    async function handleLanguageChange(lang: Language) {
        setExplanationLang(lang);
>>>>>>> c0aa63a (refactor(frontend): tighten shared portal typing and UI contracts)
        if (!selectedDocument) {
            return;
        }

        if (selectedDocument.parseStatus !== "completed") {
            return;
        }

<<<<<<< HEAD
=======
        if (lang === Language.EN) {
            setExplanationText(selectedDocument.aiSummary ?? null);
            return;
        }

>>>>>>> c0aa63a (refactor(frontend): tighten shared portal typing and UI contracts)
        setExplanationLoading(true);
        try {
            const result = await api.post<{ summary: string }>(
                `/api/v1/documents/${selectedDocument.id}/explain`,
                { language },
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

        setSelectedDocument(null);
        router.push(buildDocumentChatHref(selectedDocument.id));
    }

    const processingCount = documents.filter(
        (document) =>
            parsingDocIds.has(document.id)
            || document.parseStatus === "pending"
            || document.parseStatus === "processing",
    ).length;

    return (
        <div className="space-y-4 bg-gray-50 pb-8">
            <PageHeader
                rightAction={<Button onClick={() => fileInputRef.current?.click()} variant="secondary">Upload</Button>}
                subtitle="View clinical records and plain-language explanations."
                title="My Records"
            />
            <input className="hidden" onChange={handleFileChange} ref={fileInputRef} type="file" />
            <div className="-mt-4 space-y-4 px-5">
                <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-2xl bg-white px-4 py-3 shadow-sm ring-1 ring-slate-100">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Stored</p>
                        <p className="mt-1 text-2xl font-bold text-slate-900">{documents.length}</p>
                        <p className="text-xs text-slate-500">Secure records</p>
                    </div>
                    <div className="rounded-2xl bg-sky-50 px-4 py-3 shadow-sm ring-1 ring-sky-100">
                        <p className="text-xs font-semibold uppercase tracking-wide text-sky-700">
                            {processingCount > 0 ? "Parsing" : "AI Ready"}
                        </p>
                        <p className="mt-1 text-2xl font-bold text-slate-900">
                            {processingCount > 0
                                ? processingCount
                                : documents.filter((document) => document.parsed && document.aiSummary).length}
                        </p>
                        <p className="text-xs text-slate-500">
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
                    <p className="text-sm text-slate-500">Loading documents...</p>
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
                        date={new Date(document.createdAt).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                        hasAiSummary={document.parsed && Boolean(document.aiSummary)}
                        icon={document.icon}
                        id={document.id}
                        key={document.id}
                        name={document.fileName}
<<<<<<< HEAD
                        onClick={() => {
                            setSelectedDocument(document);
                            setExplanationLang(Language.EN);
                            setExplanationLoading(false);
                            if (document.parseStatus === "failed") {
                                setExplanationText(
                                    document.parseError ?? "This document could not be processed.",
                                );
                                return;
                            }
                            if (
                                document.parseStatus === "pending"
                                || document.parseStatus === "processing"
                                || parsingDocIds.has(document.id)
                            ) {
                                setExplanationText(
                                    "Processing this document. AI summary will appear when parsing completes.",
                                );
                                return;
                            }
                            setExplanationText(document.aiSummary ?? null);
                        }}
=======
                        onClick={() => openDocument(document)}
>>>>>>> c0aa63a (refactor(frontend): tighten shared portal typing and UI contracts)
                        provider={document.provider}
                        statusLabel={status?.label}
                        statusVariant={status?.variant}
                        type={document.documentType.replaceAll("_", " ")}
                    />
                    );
                })}
            </div>
            <Modal onClose={() => setSelectedDocument(null)} open={Boolean(selectedDocument)} title={selectedDocument?.fileName ?? "Record details"}>
                <div className="space-y-4">
                    <div className="rounded-2xl bg-slate-50 px-4 py-3">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Source</p>
                        <p className="mt-1 text-sm font-medium text-slate-700">{selectedDocument?.provider}</p>
                    </div>
                    {selectedDocument?.mimeType === "application/pdf" && selectedDocument.fileUrl ? (
                        <PdfViewer documentUrl={selectedDocument.fileUrl} height="400px" />
                    ) : null}
                    <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
                        <div className="flex items-center justify-between gap-3">
                            <p className="text-xs font-semibold uppercase tracking-wide text-blue-600">Explain this to me</p>
                            <select
                                className="rounded-lg border border-blue-200 bg-white px-2 py-1 text-xs text-blue-700"
<<<<<<< HEAD
                                onChange={(event) => handleLanguageChange(event.target.value as Language)}
=======
                                onChange={(event) =>
                                    handleLanguageChange(
                                        event.target.value === Language.ES
                                            ? Language.ES
                                            : Language.EN,
                                    )
                                }
>>>>>>> c0aa63a (refactor(frontend): tighten shared portal typing and UI contracts)
                                value={explanationLang}
                            >
                                <option value={Language.EN}>English</option>
                                <option value={Language.ES}>Español</option>
                            </select>
                        </div>
                        <p className="mt-2 text-sm text-gray-700">
                            {explanationLoading
                                ? "Translating..."
                                : explanationText ?? "AI summary will appear here after parsing completes."}
                        </p>
                    </div>
                    <div className="space-y-3">
                        <Button fullWidth onClick={handleAskAboutDocument}>
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
                    </div>
                </div>
            </Modal>
        </div>
    );
}
