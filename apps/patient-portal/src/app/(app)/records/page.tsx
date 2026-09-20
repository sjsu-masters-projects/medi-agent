"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useDispatch, useSelector } from "react-redux";
import {
  HiMiniSpeakerWave,
  HiOutlineBeaker,
  HiOutlineClipboardDocumentList,
  HiOutlineDocumentText,
  HiOutlineFolder,
} from "react-icons/hi2";
import { DocumentCard, DocumentSourceViewer } from "@/components/features";
import { PageHeader } from "@/components/layouts";
import {
  Button,
  EmptyState,
  ErrorState,
  Modal,
  ProgressBar,
} from "@/components/ui";
import { api } from "@/services/api";
import { redirectToLogin } from "@/services/auth-redirect";
import { refreshPatientSession } from "@/services/auth-refresh";
import { writeStoredSession } from "@/services/auth-session";
import {
  buildDocumentChatHref,
  buildSuggestedDocumentQuestion,
  storePendingChatDocumentContext,
} from "@/services/chat-bridge";
import { playAssistantVoiceResponse } from "@/services/browser-voice";
import {
  inferDocumentType,
  normalizePatientSummary,
  type DocumentApiRecord,
} from "@/services/documents";
import { hashDocumentFile, uploadDocumentToStorage } from "@/services/storage";
import { hydrateSession, logout } from "@/store/slices/auth-slice";
import type { AppDispatch, RootState } from "@/store/store";
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
import { getEffectiveSessionExpiresAt } from "../../../../../../packages/shared/src/utils/jwt-expiry";

type PortalDocument = Document & {
  icon: ReactNode;
  previewMimeType?: string;
  previewStatus?: string;
  previewUrl?: string;
  provider: string;
};

const EXPLANATION_UNAVAILABLE_MESSAGE =
  "Translation is currently unavailable. Please try again later.";
const PARSING_IN_PROGRESS_MESSAGE =
  "Processing this document. AI summary will appear when parsing completes.";
const PARSING_FAILED_FALLBACK_MESSAGE = "This document could not be processed.";

/**
 * Why a document failed, in words a patient can act on.
 *
 * The backend stores a short code (migration 034 constrains it to this set), not a
 * sentence. Rendering the code itself would show a patient "source_unreadable", so each
 * one is mapped here. An unknown code falls back rather than leaking through: the set is
 * constrained in the database, but a newer backend may add one before this list catches
 * up, and a raw enum is never an acceptable thing to put in front of a patient.
 */
const PARSE_FAILURE_MESSAGES: Record<string, string> = {
  attempt_limit_reached:
    "We tried several times and could not process this document. Someone on your care team can review it.",
  evidence_not_grounded:
    "We could not match what we found back to the document, so nothing was saved. Someone on your care team can review it.",
  invalid_model_response:
    "We could not read the details from this document. Someone on your care team can review it.",
  needs_ocr:
    "We could not read this scan reliably, so nothing was saved. Someone on your care team can review it.",
  provider_unavailable:
    "The document service was briefly unavailable. Please try again in a moment.",
  source_unreadable:
    "This file could not be opened. It may be damaged, or password protected.",
};

function describeParseFailure(code?: string): string {
  return (code && PARSE_FAILURE_MESSAGES[code]) || PARSING_FAILED_FALLBACK_MESSAGE;
}
const INITIAL_POLL_DELAY_MS = 3_000;
const MAX_POLL_DELAY_MS = 30_000;
const MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024;
const SUPPORTED_UPLOAD_MIME_TYPES = new Set([
  "application/pdf",
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/tiff",
]);
const UPLOAD_ACCEPT_ATTRIBUTE = ".pdf,.jpg,.jpeg,.png,.webp,.tif,.tiff";
const UNSUPPORTED_UPLOAD_MESSAGE =
  "Choose a PDF, JPG, PNG, WebP, or TIFF file up to 20 MB.";

function getUploadValidationError(file: File): string | null {
  if (!SUPPORTED_UPLOAD_MIME_TYPES.has(file.type)) {
    return UNSUPPORTED_UPLOAD_MESSAGE;
  }
  if (file.size > MAX_UPLOAD_SIZE_BYTES) {
    return "Each file must be 20 MB or smaller.";
  }
  return null;
}

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

function isDocumentProcessing(status: string) {
  return (
    status === DocumentParseStatus.PENDING ||
    status === DocumentParseStatus.PROCESSING
  );
}

function needsHumanDocumentReview(status: string) {
  return (
    status === DocumentParseStatus.NEEDS_OCR ||
    status === DocumentParseStatus.NEEDS_EVIDENCE_REVIEW
  );
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
    aiSummary: normalizePatientSummary(record.ai_summary),
    createdAt: record.created_at,
    documentType: record.document_type,
    fileName: record.file_name,
    fileSizeBytes: record.file_size_bytes,
    fileUrl: record.file_url,
    icon: getDocumentIcon(record.document_type),
    id: record.id,
    mimeType: record.mime_type,
    previewMimeType: record.preview_mime_type ?? undefined,
    previewStatus: record.preview_status ?? undefined,
    previewUrl: record.preview_url ?? undefined,
    parseAttempts: record.parse_attempts ?? 0,
    parseFailureCode: record.parse_failure_code ?? undefined,
    parseStatus:
      record.parse_status ??
      (record.parsed
        ? DocumentParseStatus.COMPLETED
        : DocumentParseStatus.NONE),
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
  if (isDocumentProcessing(document.parseStatus)) {
    return { label: "Processing...", variant: "warning" as const };
  }
  if (needsHumanDocumentReview(document.parseStatus)) {
    return { label: "Needs care-team review", variant: "warning" as const };
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
  const dispatch = useDispatch<AppDispatch>();
  const router = useRouter();
  const [documents, setDocuments] = useState<PortalDocument[]>([]);
  const [selectedDocument, setSelectedDocument] =
    useState<PortalDocument | null>(null);
  const [deleteConfirming, setDeleteConfirming] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deletingDocumentId, setDeletingDocumentId] = useState<string | null>(
    null,
  );
  const [explanationLang, setExplanationLang] =
    useState<Locale>(DEFAULT_LOCALE);
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
  const activePollsRef = useRef(new Set<string>());
  const { accessToken, expiresAt, refreshToken, user } = useSelector(
    (state: RootState) => state.auth,
  );

  const IMPORT_REFRESH_WINDOW_SECONDS = 2 * 60;

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

  const openDocument = useCallback(
    (document: PortalDocument) => {
      setSelectedDocument(document);
      setDeleteConfirming(false);
      setDeleteError(null);
      setExplanationLang(DEFAULT_LOCALE);
      setExplanationLoading(false);

      if (
        document.parseStatus === "failed" ||
        needsHumanDocumentReview(document.parseStatus)
      ) {
        setExplanationText(describeParseFailure(document.parseFailureCode));
        return;
      }

      if (
        isDocumentProcessing(document.parseStatus) ||
        parsingDocIds.has(document.id)
      ) {
        setExplanationText(PARSING_IN_PROGRESS_MESSAGE);
        return;
      }

      setExplanationText(document.aiSummary ?? null);
    },
    [parsingDocIds],
  );

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

  useEffect(() => {
    const activePolls = activePollsRef.current;
    return () => activePolls.clear();
  }, []);

  async function pollForParsedStatus(docId: string) {
    if (activePollsRef.current.has(docId)) return;
    activePollsRef.current.add(docId);
    setParsingDocIds((current) => addTrackedDocumentId(current, docId));

    let delayMs = INITIAL_POLL_DELAY_MS;
    try {
      while (activePollsRef.current.has(docId)) {
        await new Promise((resolve) => window.setTimeout(resolve, delayMs));
        if (!activePollsRef.current.has(docId)) return;
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
          if (nextDocument.parsed || nextDocument.parseStatus === "completed") return;
          if (
            nextDocument.parseStatus === "failed" ||
            needsHumanDocumentReview(nextDocument.parseStatus)
          ) {
            setParseError(describeParseFailure(nextDocument.parseFailureCode));
            return;
          }
        } catch {
          // A queue-backed worker can outlive a short network failure.
        }
        delayMs = Math.min(delayMs * 2, MAX_POLL_DELAY_MS);
      }
    } finally {
      activePollsRef.current.delete(docId);
      setParsingDocIds((current) => removeTrackedDocumentId(current, docId));
    }
  }

  async function getUploadSession() {
    if (!accessToken || !user) {
      setPageError("Please sign in again before uploading a document.");
      return null;
    }

    const effectiveExpiresAt = getEffectiveSessionExpiresAt(
      expiresAt,
      accessToken,
    );
    const shouldRefresh =
      !effectiveExpiresAt ||
      effectiveExpiresAt - Math.floor(Date.now() / 1000) <=
        IMPORT_REFRESH_WINDOW_SECONDS;

    if (!shouldRefresh) {
      return { accessToken, user };
    }

    if (!refreshToken) {
      dispatch(logout());
      redirectToLogin({ reason: "session_expired" });
      setPageError(
        "Your session expired. Please sign in again before uploading.",
      );
      return null;
    }

    try {
      const session = await refreshPatientSession(refreshToken);
      writeStoredSession(session);
      dispatch(hydrateSession(session));
      return session;
    } catch {
      dispatch(logout());
      redirectToLogin({ reason: "session_expired" });
      setPageError(
        "Your session expired. Please sign in again before uploading.",
      );
      return null;
    }
  }

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    const validationError = getUploadValidationError(file);
    if (validationError) {
      setPageError(validationError);
      event.target.value = "";
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
      const session = await getUploadSession();
      if (!session) {
        return;
      }

      const [filePath, contentHash] = await Promise.all([
        uploadDocumentToStorage({
          file,
          patientId: session.user.id,
          token: session.accessToken,
        }),
        hashDocumentFile(file),
      ]);
      const created = await api.post<DocumentApiRecord>(
        "/api/v1/documents/",
        {
          document_type: inferDocumentType(file),
          file_name: file.name,
          file_path: filePath,
          file_size_bytes: file.size,
          mime_type: file.type || "application/octet-stream",
          source_clinic: "Patient uploaded document",
          content_hash: contentHash,
          start_ingestion: true,
        },
        { token: session.accessToken },
      );
      const nextDocument = mapDocument(created);
      setDocuments((current) => [nextDocument, ...current]);
      // Candidate-only ingestion runs in the background. It never updates
      // the patient's canonical profile until a clinician reconciles it.
      void pollForParsedStatus(nextDocument.id);
    } catch (error) {
      setPageError(
        (error as Error).message || "Upload failed. Please try again.",
      );
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
      nextLocale === DEFAULT_LOCALE &&
      selectedDocument?.parseStatus === DocumentParseStatus.COMPLETED
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
      setParsingDocIds((current) =>
        removeTrackedDocumentId(current, selectedDocument.id),
      );
      closeDocumentModal();
    } catch (error) {
      setDeleteError(
        (error as Error).message || "Delete failed. Please try again.",
      );
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
      parsingDocIds.has(document.id) ||
      isDocumentProcessing(document.parseStatus),
  ).length;
  const isDeletingSelectedDocument =
    deletingDocumentId === selectedDocument?.id;

  return (
    <div className="patient-page space-y-4 pb-8">
      <PageHeader
        rightAction={
          <Button
            onClick={() => fileInputRef.current?.click()}
            variant="secondary"
          >
            Upload
          </Button>
        }
        subtitle="View clinical records and plain-language explanations."
        title="My Records"
      />
      <input
        accept={UPLOAD_ACCEPT_ATTRIBUTE}
        className="hidden"
        onChange={handleFileChange}
        ref={fileInputRef}
        type="file"
      />
      <div className="patient-stack -mt-4 space-y-4 px-5">
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-[1.4rem] bg-white/90 px-4 py-4 shadow-[0_12px_28px_rgba(37,52,82,0.08)] ring-1 ring-[#eaded3]">
            <p className="text-xs font-semibold uppercase tracking-wide text-[#7b8798]">
              Stored
            </p>
            <p className="mt-1 text-3xl font-bold text-[#17233a]">
              {documents.length}
            </p>
            <p className="text-sm text-[#5b6b83]">Secure records</p>
          </div>
          <div className="rounded-[1.4rem] bg-[#e7f4f1] px-4 py-4 shadow-[0_12px_28px_rgba(20,116,101,0.10)] ring-1 ring-[#b9ded6]">
            <p className="text-xs font-semibold uppercase tracking-wide text-[#147465]">
              {processingCount > 0 ? "Parsing" : "AI Ready"}
            </p>
            <p className="mt-1 text-3xl font-bold text-[#17233a]">
              {processingCount > 0
                ? processingCount
                : documents.filter(
                    (document) => document.parsed && document.aiSummary,
                  ).length}
            </p>
            <p className="text-sm text-[#48627c]">
              {processingCount > 0
                ? "Documents in progress"
                : "Summaries available"}
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
          <p className="rounded-2xl bg-white/80 px-4 py-3 text-sm font-medium text-[#5b6b83] shadow-sm ring-1 ring-[#eaded3]">
            Loading documents...
          </p>
        ) : null}
        {!loading && !pageError && documents.length === 0 ? (
          <EmptyState
            description="Upload PDFs or images from your clinic visits."
            icon={<HiOutlineFolder />}
            title="No records yet"
          />
        ) : null}
        {documents.map((document) => {
          const displayDocument = parsingDocIds.has(document.id)
            ? { ...document, parseStatus: "processing" as const }
            : document;
          const status = getDocumentStatus(displayDocument);

          return (
            <DocumentCard
              date={new Date(document.createdAt).toLocaleDateString(
                explanationLang,
                { month: "short", day: "numeric", year: "numeric" },
              )}
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
      <Modal
        onClose={closeDocumentModal}
        open={Boolean(selectedDocument)}
        size="wide"
        title={selectedDocument?.fileName ?? "Record details"}
      >
        <div className="space-y-4">
          <div className="rounded-2xl bg-[#fff7ed] px-4 py-3 ring-1 ring-[#eaded3]">
            <p className="text-xs font-semibold uppercase tracking-wide text-[#7b8798]">
              Source
            </p>
            <p className="mt-1 text-sm font-semibold text-[#30415f]">
              {selectedDocument?.provider}
            </p>
          </div>
          <DocumentSourceViewer
            fileName={selectedDocument?.fileName ?? "Document"}
            previewMimeType={selectedDocument?.previewMimeType}
            previewStatus={selectedDocument?.previewStatus}
            previewUrl={selectedDocument?.previewUrl}
            sourceMimeType={selectedDocument?.mimeType}
            sourceUrl={selectedDocument?.fileUrl}
          />
          <div className="rounded-3xl border border-[#b9ded6] bg-[#e7f4f1] p-4">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-[#147465]">
                Explain this to me
              </p>
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
                  onChange={(event) =>
                    handleLanguageChange(event.target.value as Locale)
                  }
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
                  : (explanationText ??
                    "AI summary will appear here after parsing completes.")}
            </p>
          </div>
          <div className="space-y-3">
            <Button fullWidth onClick={handleAskAboutDocument} size="lg">
              Ask about this document
            </Button>
            <div className="grid grid-cols-2 gap-3">
              <Button
                fullWidth
                onClick={() => setSelectedDocument(null)}
                variant="secondary"
              >
                Close
              </Button>
              <Button
                fullWidth
                onClick={() => fileInputRef.current?.click()}
                variant="secondary"
              >
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
                <p className="text-base font-bold text-[#7f2c23]">
                  Delete this document?
                </p>
                <p className="mt-1 text-sm leading-6 text-[#9b4539]">
                  This removes the record from your documents. Existing
                  care-plan items created from prior parsing are not removed.
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
                    {isDeletingSelectedDocument
                      ? "Deleting"
                      : "Delete permanently"}
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
