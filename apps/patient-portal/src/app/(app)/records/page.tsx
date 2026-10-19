"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useDispatch, useSelector } from "react-redux";
import { DocumentSourceViewer } from "@/components/features";
import { DocumentResults } from "@/components/features/document-results";
import { NotificationBell } from "@/components/features/notification-centre";
import { groupRecordDates, RecordRow, recordTitle } from "@/components/features/record-row";
import { Icon } from "@/components/ui/icons";
import { PullToRefresh } from "@/components/ui/pull-to-refresh";
import { OverflowMenu } from "@/components/ui/overflow-menu";
import { ListenBars, ProcessingDots } from "@/components/ui/motion";
import { usePatientProfile } from "@/hooks/use-patient-profile";
import { recordsCopy } from "@/components/features/records-copy";
import { Button, EmptyState, ErrorState, Modal, Skeleton } from "@/components/ui";
import { api } from "@/services/api";
import { redirectToLogin } from "@/services/auth-redirect";
import { refreshPatientSession } from "@/services/auth-refresh";
import { refreshSingleFlight } from "@/services/auth-session";
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
  Locale,
  SUPPORTED_LOCALES,
  getLocaleLabel,
  getDocumentTypeLabel,
  normalizeLocale,
  type Document,
} from "@/types";
import { getEffectiveSessionExpiresAt } from "../../../../../../packages/shared/src/utils/jwt-expiry";

type PortalDocument = Document & {
  previewMimeType?: string;
  previewStatus?: string;
  previewUrl?: string;
  provider: string;
  summaryFailureCode?: string;
  summaryStatus?: string;
};

const EXPLANATION_UNAVAILABLE_MESSAGE =
  "Translation is currently unavailable. Please try again later.";
const PARSING_IN_PROGRESS_MESSAGE =
  "We are preparing this document. Its explanation will appear when ready.";
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

function describeParseFailure(
  code?: string,
  locale: Locale = DEFAULT_LOCALE,
): string {
  return recordsCopy(
    locale,
    (code && PARSE_FAILURE_MESSAGES[code]) || PARSING_FAILED_FALLBACK_MESSAGE,
  );
}

/**
 * Why the plain-language explanation is missing, for a document that parsed fine.
 *
 * The explanation has its own lifecycle (migration 038): the document, its source, and
 * anything a clinician reviews are unaffected when it fails. Showing nothing here read
 * as "still parsing", which was wrong and left a patient waiting for something that was
 * never coming.
 */
const SUMMARY_UNAVAILABLE_MESSAGES: Record<string, string> = {
  failed:
    "A plain-language explanation is not available for this document right now. Your document and your records are unchanged, and your care team can request it again.",
  not_required:
    "There is no extracted information in this document to explain. You can still open the original document above or ask your care team about it.",
  pending:
    "The plain-language explanation is still being prepared. You can read the original document above and check back shortly.",
};

function describeMissingSummary(
  document: PortalDocument,
  locale: Locale = DEFAULT_LOCALE,
): string {
  const status = document.summaryStatus ?? "pending";
  return recordsCopy(
    locale,
    SUMMARY_UNAVAILABLE_MESSAGES[status] ??
      SUMMARY_UNAVAILABLE_MESSAGES.pending,
  );
}

function duplicateUploadMessage(locale: Locale): string {
  return locale === "es-MX"
    ? "Este mismo archivo ya se procesó. Se guardó esta copia, pero no se extrajeron datos nuevos ni se agregaron instrucciones al plan de cuidado. Puedes abrir el original o consultar a tu equipo de atención."
    : "These exact file contents were already processed for you. This copy is stored, but no new facts or care-plan instructions were created. You can open the original or ask your care team about it.";
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

function mapDocument(record: DocumentApiRecord): PortalDocument {
  return {
    aiSummary: normalizePatientSummary(record.ai_summary),
    displayTitle: record.display_title ?? undefined,
    createdAt: record.created_at,
    documentType: record.document_type,
    fileName: record.file_name,
    fileSizeBytes: record.file_size_bytes,
    fileUrl: record.file_url,
    id: record.id,
    mimeType: record.mime_type,
    previewMimeType: record.preview_mime_type ?? undefined,
    previewStatus: record.preview_status ?? undefined,
    previewUrl: record.preview_url ?? undefined,
    parseAttempts: record.parse_attempts ?? 0,
    summaryFailureCode: record.summary_failure_code ?? undefined,
    summaryStatus: record.summary_status ?? undefined,
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

function getDocumentStatus(document: PortalDocument, locale: Locale) {
  const copy = (text: string) => recordsCopy(locale, text);
  if (document.parseStatus === DocumentParseStatus.DUPLICATE) {
    return { label: copy("Duplicate upload"), variant: "info" as const };
  }
  if (isDocumentProcessing(document.parseStatus)) {
    return { label: copy("Processing..."), variant: "warning" as const };
  }
  if (needsHumanDocumentReview(document.parseStatus)) {
    return {
      label: copy("Needs care-team review"),
      variant: "warning" as const,
    };
  }
  if (document.parseStatus === "failed") {
    return {
      label: copy("This document could not be processed."),
      variant: "danger" as const,
    };
  }
  if (document.parsed && document.aiSummary) {
    return { label: copy("AI Summary"), variant: "info" as const };
  }
  if (document.summaryStatus === "failed") {
    return {
      label: copy("Explanation unavailable"),
      variant: "warning" as const,
    };
  }
  return null;
}

export default function RecordsPage() {
  const profile = usePatientProfile();
  const locale = profile?.preferredLanguage ?? DEFAULT_LOCALE;
  const copy = useCallback(
    (text: string) => recordsCopy(locale, text),
    [locale],
  );
  const dispatch = useDispatch<AppDispatch>();
  const router = useRouter();
  const requestedDocument = useSearchParams().get("document");
  const handledDocument = useRef<string | null>(null);
  const [documentUnavailable, setDocumentUnavailable] = useState(false);
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
  // Whether the text above is a real explanation or a reason one is missing. The two
  // must not be confused: a reason may never be forwarded as a document's summary.
  const [explanationAvailable, setExplanationAvailable] = useState(false);
  const [explanationLoading, setExplanationLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [readbackActive, setReadbackActive] = useState(false);
  const [parsingDocIds, setParsingDocIds] = useState<Set<string>>(new Set());
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
    } catch {
      setPageError(copy("We could not load your documents. Please try again."));
    } finally {
      setLoading(false);
    }
  }, [accessToken, copy]);

  const openDocument = useCallback(
    (document: PortalDocument) => {
      setSelectedDocument(document);
      setDeleteConfirming(false);
      setDeleteError(null);
      setExplanationLang(locale);
      setExplanationLoading(false);

      setExplanationAvailable(false);

      if (document.parseStatus === DocumentParseStatus.DUPLICATE) {
        setExplanationText(duplicateUploadMessage(locale));
        return;
      }

      if (
        document.parseStatus === "failed" ||
        needsHumanDocumentReview(document.parseStatus)
      ) {
        setExplanationText(
          describeParseFailure(document.parseFailureCode, locale),
        );
        return;
      }

      if (
        isDocumentProcessing(document.parseStatus) ||
        parsingDocIds.has(document.id)
      ) {
        setExplanationText(copy(PARSING_IN_PROGRESS_MESSAGE));
        return;
      }

      if (!document.aiSummary) {
        setExplanationText(describeMissingSummary(document, locale));
        return;
      }

      // Cached source explanations retain their original language until explicitly requested.
      setExplanationLang(DEFAULT_LOCALE);
      setExplanationAvailable(true);
      setExplanationText(document.aiSummary);
    },
    [parsingDocIds, locale, copy],
  );

  const closeDocumentModal = useCallback(() => {
    setSelectedDocument(null);
    setDeleteConfirming(false);
    setDeleteError(null);
  }, []);

  useEffect(() => {
    if (!requestedDocument) { handledDocument.current = null; setDocumentUnavailable(false); return; }
    if (loading || pageError || handledDocument.current === requestedDocument) return;
    const document = documents.find((item) => item.id === requestedDocument);
    if (document) { handledDocument.current = requestedDocument; setDocumentUnavailable(false); openDocument(document); }
    else { setSelectedDocument(null); setDocumentUnavailable(true); }
  }, [requestedDocument, documents, loading, pageError, openDocument]);

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
          if (
            nextDocument.parsed ||
            nextDocument.parseStatus === "completed" ||
            nextDocument.parseStatus === DocumentParseStatus.DUPLICATE
          )
            return;
          if (
            nextDocument.parseStatus === "failed" ||
            needsHumanDocumentReview(nextDocument.parseStatus)
          ) {
            setParseError(
              describeParseFailure(nextDocument.parseFailureCode, locale),
            );
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
      setPageError(copy("Please sign in again before uploading a document."));
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
        copy("Your session expired. Please sign in again before uploading."),
      );
      return null;
    }

    // Single-flight across tabs; a session another tab already refreshed is adopted.
    const outcome = await refreshSingleFlight({
      current: { expiresAt: expiresAt ?? 0, refreshToken },
      refreshSession: refreshPatientSession,
    });
    if (outcome.status === "ok") {
      dispatch(hydrateSession(outcome.session));
      return outcome.session;
    }
    if (outcome.status === "invalid") {
      dispatch(logout());
      redirectToLogin({ reason: "session_expired" });
    }
    setPageError(
      copy("Your session expired. Please sign in again before uploading."),
    );
    return null;
  }

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    const validationError = getUploadValidationError(file);
    if (validationError) {
      setPageError(copy(validationError));
      event.target.value = "";
      return;
    }

    setPageError(null);
    setParseError(null);
    setUploading(true);

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
    } catch {
      setPageError(
        copy("Upload failed. Please refresh your records before trying again."),
      );
    } finally {
      setUploading(false);
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
      setExplanationAvailable(Boolean(selectedDocument.aiSummary));
      setExplanationText(
        selectedDocument.aiSummary ??
          describeMissingSummary(selectedDocument, nextLocale),
      );
      return;
    }
    if (!selectedDocument) {
      return;
    }

    if (selectedDocument.parseStatus === DocumentParseStatus.DUPLICATE) {
      setExplanationAvailable(false);
      setExplanationText(duplicateUploadMessage(nextLocale));
      return;
    }

    if (selectedDocument.parseStatus !== DocumentParseStatus.COMPLETED) {
      setExplanationText(
        isDocumentProcessing(selectedDocument.parseStatus)
          ? recordsCopy(nextLocale, PARSING_IN_PROGRESS_MESSAGE)
          : describeParseFailure(selectedDocument.parseFailureCode, nextLocale),
      );
      return;
    }

    setExplanationLoading(true);
    try {
      const result = await api.post<{
        available?: boolean;
        message?: string | null;
        summary: string | null;
      }>(
        `/api/v1/documents/${selectedDocument.id}/explain`,
        { language: nextLocale },
        { token: accessToken ?? undefined },
      );
      // The backend answers with either an explanation or the reason there is none,
      // already written in the requested locale.
      const available = result.available !== false && Boolean(result.summary);
      setExplanationAvailable(available);
      setExplanationText(
        available
          ? result.summary
          : (result.message ??
              recordsCopy(nextLocale, EXPLANATION_UNAVAILABLE_MESSAGE)),
      );
    } catch {
      setExplanationAvailable(false);
      setExplanationText(
        recordsCopy(nextLocale, EXPLANATION_UNAVAILABLE_MESSAGE),
      );
    } finally {
      setExplanationLoading(false);
    }
  }

  function handleAskAboutDocument() {
    if (!selectedDocument) {
      return;
    }

    const documentName = recordTitle(selectedDocument, explanationLang, patientName);
    storePendingChatDocumentContext({
      documentId: selectedDocument.id,
      documentName,
      documentType: selectedDocument.documentType,
      preferredLanguage: explanationLang,
      provider: selectedDocument.provider,
      suggestedQuestion: buildSuggestedDocumentQuestion({
        documentName,
        documentType: selectedDocument.documentType,
        preferredLanguage: explanationLang,
        provider: selectedDocument.provider,
      }),
      summary: explanationAvailable
        ? (explanationText ?? selectedDocument.aiSummary)
        : undefined,
    });

    closeDocumentModal();
    router.push(buildDocumentChatHref(selectedDocument.id));
  }

  async function handleDeleteDocument() {
    if (!selectedDocument) {
      return;
    }

    if (!accessToken) {
      setDeleteError(
        copy("Please sign in again before deleting this document."),
      );
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
    } catch {
      setDeleteError(
        copy("Delete failed. Please refresh your records before trying again."),
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

  const patientName = [profile?.firstName, profile?.lastName].filter(Boolean).join(" ");
  const spanish = locale === "es-MX";
  const displayProvider = (document: PortalDocument) => {
    if (document.provider === "Patient uploaded document") return spanish ? "Tu documento" : "Your upload";
    if (document.provider === "Clinician uploaded document") return spanish ? "De tu equipo de atención" : "From your care team";
    return copy(document.provider);
  };
  const shortDate = (value: string, withYear = false) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const timeZone = profile?.timezone ?? "UTC";
    const sameYear = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric" }).format(date) === new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric" }).format(new Date());
    return date.toLocaleDateString(locale, { month: "short", day: "numeric", ...(withYear || !sameYear ? { year: "numeric" } : {}), timeZone });
  };

  return (
    <PullToRefresh
      onRefresh={loadDocuments}
      busy={loading || uploading}
      label={copy("Refresh records")}
    >
      <div className="patient-page pb-6">
        <header className="px-[22px] pt-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h1 className="min-w-0 flex-1 basis-[180px] break-words text-[32px] font-semibold leading-[1.1] tracking-[-0.02em] text-ink">
              {copy("My Records")}
            </h1>
            <div className="ml-auto flex shrink-0 items-center gap-1.5">
              <NotificationBell />
              <OverflowMenu
                label={spanish ? "Más opciones" : "More options"}
                items={[
                  {
                    label: copy(loading ? "Refreshing..." : "Refresh records"),
                    icon: "refresh",
                    onSelect: () => void loadDocuments(),
                    disabled: loading || uploading,
                    busy: loading,
                  },
                ]}
              />
              <button
                type="button"
                aria-label={copy("Upload")}
                title={copy("Upload")}
                disabled={uploading}
                onClick={() => fileInputRef.current?.click()}
                className="ma-press flex h-11 w-11 items-center justify-center rounded-[14px] bg-brand text-white shadow-[0_8px_18px_-10px_rgba(20,116,101,.8)] hover:bg-brand-hover disabled:opacity-50"
              >
                <Icon name="up" className="h-5 w-5" />
              </button>
            </div>
          </div>
          <p className="mt-1 text-sm text-muted" role="status">
            {spanish
              ? `${documents.length} documentos · ${processingCount} en proceso`
              : `${documents.length} records · ${processingCount} processing`}
          </p>
        </header>
        <input
          accept={UPLOAD_ACCEPT_ATTRIBUTE}
          className="hidden"
          onChange={handleFileChange}
          ref={fileInputRef}
          type="file"
        />
        <div className="space-y-3 px-4 pt-4 empty:hidden">
          {documentUnavailable && <p role="alert" className="rounded-2xl bg-danger-tint p-3 text-sm text-danger-ink">{spanish ? "Este documento no está disponible. Actualiza tus registros." : "This document is unavailable. Refresh your records."}</p>}
          {uploading ? (
            <p
              role="status"
              className="ma-enter flex items-center gap-3 rounded-[22px] bg-brand-tint px-4 py-3.5 text-sm font-medium text-brand-ink"
            >
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-surface text-brand"><Icon name="up" className="h-[18px] w-[18px]" /></span>
              <span className="flex-1">{spanish ? "Subiendo documento..." : "Uploading document..."}</span>
              <ProcessingDots className="bg-brand" />
            </p>
          ) : null}
          {pageError && documents.length === 0 ? (
            <ErrorState
              description={pageError}
              action={
                <Button
                  disabled={loading}
                  onClick={() => void loadDocuments()}
                  variant="secondary"
                  size="sm"
                >
                  {copy("Try again")}
                </Button>
              }
              title={copy("Could not load records")}
            />
          ) : null}
          {pageError && documents.length > 0 ? (
            <ErrorState
              description={pageError}
              action={
                <Button
                  onClick={() => {
                    setPageError(null);
                    void loadDocuments();
                  }}
                  variant="secondary"
                  size="sm"
                >
                  {copy("Try again")}
                </Button>
              }
              title={copy("Action failed")}
            />
          ) : null}
          {parseError ? (
            <ErrorState
              description={parseError}
              action={
                <Button
                  onClick={() => {
                    setParseError(null);
                    fileInputRef.current?.click();
                  }}
                  variant="secondary"
                  size="sm"
                >
                  {copy("Try again")}
                </Button>
              }
              title={copy("Document processing failed")}
            />
          ) : null}
          {loading && documents.length === 0 ? (
            <div aria-hidden="true" className="space-y-2.5 pt-2">
              <Skeleton className="h-3 w-24" variant="text" />
              <Skeleton className="h-[220px] w-full" />
            </div>
          ) : null}
          {loading ? (
            <p className="sr-only" role="status">
              {copy("Loading documents...")}
            </p>
          ) : null}
          {!loading && !pageError && documents.length === 0 ? (
            <div className="rounded-[22px] bg-surface">
              <EmptyState
                description={copy(
                  "Upload PDFs or images from your clinic visits.",
                )}
                icon={<Icon name="folder" />}
                title={copy("No records yet")}
                action={
                  <Button size="sm" onClick={() => fileInputRef.current?.click()} disabled={uploading}>
                    <Icon name="up" className="h-[18px] w-[18px]" />{copy("Upload")}
                  </Button>
                }
              />
            </div>
          ) : null}
        </div>
        <div className="patient-stack">
          {groupRecordDates(
            documents,
            new Date(),
            profile?.timezone ?? "UTC",
          ).map((group) => (
            <section key={group.key} aria-labelledby={`records-${group.key}`}>
              <h2
                id={`records-${group.key}`}
                className="px-[22px] pt-5 pb-2 font-mono text-xs uppercase tracking-[0.08em] text-muted"
              >
                {group.key === "recent"
                  ? spanish
                    ? "Esta semana"
                    : "This week"
                  : spanish
                    ? "Anteriores"
                    : "Earlier"}
              </h2>
              <div className="mx-4 overflow-hidden rounded-[22px] bg-surface [&>*+*]:border-t [&>*+*]:border-line">
                {group.items.map((document) => {
                  const displayDocument = parsingDocIds.has(document.id)
                    ? { ...document, parseStatus: "processing" as const }
                    : document;
                  const status = getDocumentStatus(displayDocument, locale);

                  return (
                    <RecordRow
                      document={displayDocument}
                      patientName={patientName}
                      locale={locale}
                      date={shortDate(document.createdAt)}
                      key={document.id}
                      onOpen={() => openDocument(document)}
                      provider={displayProvider(document)}
                      statusLabel={status?.label}
                      typeLabel={getDocumentTypeLabel(
                        document.documentType,
                        locale,
                      )}
                    />
                  );
                })}
              </div>
            </section>
          ))}
        </div>
        <Modal
          onClose={closeDocumentModal}
          open={Boolean(selectedDocument)}
          closeLabel={spanish ? "Cerrar ventana" : "Close modal"}
          size="wide"
          title={selectedDocument ? recordTitle(selectedDocument, locale, patientName) : copy("Record details")}
        >
          <div className="space-y-4">
            <div className="-mt-2 space-y-1">
              <p className="break-words text-sm text-muted first-letter:uppercase">
                {selectedDocument
                  ? [getDocumentTypeLabel(selectedDocument.documentType, locale), displayProvider(selectedDocument), shortDate(selectedDocument.createdAt, true)].filter(Boolean).join(" · ")
                  : null}
              </p>
              <p className="break-words font-mono text-xs text-muted [overflow-wrap:anywhere]">{selectedDocument?.fileName}</p>
            </div>
            <details className="group rounded-[22px] border border-line-strong bg-surface">
              <summary className="flex min-h-12 cursor-pointer list-none items-center gap-3 px-4 py-2 font-semibold text-ink [&::-webkit-details-marker]:hidden">
                <Icon name="file" className="h-5 w-5 text-muted" />
                <span className="flex-1">{copy("Source document")}</span>
                <Icon name="chevronDown" className="h-[18px] w-[18px] text-muted transition-transform duration-[240ms] group-open:rotate-180" />
              </summary>
              <div className="border-t border-line px-4 pt-3 pb-4">
                {selectedDocument?.sourceClinic ? (
                  <p className="mb-2 break-words text-sm text-ink-2">
                    {copy("Source")}: {copy(selectedDocument.sourceClinic)}
                  </p>
                ) : null}
                <DocumentSourceViewer
                  locale={locale}
                  fileName={selectedDocument?.fileName ?? copy("Document")}
                  previewMimeType={selectedDocument?.previewMimeType}
                  previewStatus={selectedDocument?.previewStatus}
                  previewUrl={selectedDocument?.previewUrl}
                  sourceMimeType={selectedDocument?.mimeType}
                  sourceUrl={selectedDocument?.fileUrl}
                />
              </div>
            </details>
            <div className="rounded-[22px] bg-brand-tint/70 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="inline-flex items-center gap-2 text-sm font-semibold text-brand-ink">
                  <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-surface text-brand"><Icon name="spark" className="h-3.5 w-3.5" /></span>
                  {copy("Explain this to me")}
                </p>
                <div className="flex min-w-0 w-full flex-wrap items-center gap-2 sm:w-auto">
                  <button
                    aria-label={copy("Read summary aloud")}
                    className="ma-press flex h-11 w-11 items-center justify-center rounded-xl bg-surface text-brand-ink hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={
                      explanationLoading ||
                      (!explanationText && !selectedDocument?.aiSummary)
                    }
                    onClick={handleReadSummary}
                    type="button"
                  >
                    {readbackActive ? <ListenBars /> : <Icon name="speaker" className="h-5 w-5" />}
                  </button>
                  <select
                    aria-label={copy("Explanation language")}
                    className="min-h-11 min-w-0 max-w-full flex-1 rounded-xl border border-line-strong bg-surface pl-3 pr-10 py-2 text-base font-medium text-brand-ink outline-none focus:border-brand focus:ring-4 focus:ring-brand/15"
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
              <p
                aria-live="polite"
                className="mt-3 whitespace-pre-wrap break-words text-base leading-7 text-ink"
              >
                {explanationLoading
                  ? copy("Translating...")
                  : readbackActive
                    ? spanish
                      ? `Escuchando en ${getLocaleLabel(explanationLang)}...`
                      : `Reading in ${getLocaleLabel(explanationLang)}...`
                    : (explanationText ??
                      copy(
                        "A plain-language explanation will appear here once it is ready.",
                      ))}
              </p>
              {/* Written in the explanation's language, which can differ from the app's. */}
              <p className="mt-3 border-t border-brand/15 pt-3 text-[13px] leading-5 text-brand-ink/90" lang={explanationLang}>
                {explanationLang === "es-MX"
                  ? "Esta explicación describe el documento subido. No es un nuevo plan de atención aprobado ni una recomendación para cambiar el tratamiento. Sigue las instrucciones aprobadas por tu equipo de atención."
                  : "This explanation describes the uploaded document. It is not a newly approved care plan or a recommendation to change treatment. Follow your care team's approved instructions."}
              </p>
            </div>
            {selectedDocument &&
            selectedDocument.parseStatus !== DocumentParseStatus.DUPLICATE &&
            !isDocumentProcessing(selectedDocument.parseStatus) &&
            !parsingDocIds.has(selectedDocument.id) ? (
              // Fetched only for the opened document, never for every row in the list.
              <DocumentResults
                key={selectedDocument.id}
                documentId={selectedDocument.id}
                locale={locale}
                token={accessToken}
              />
            ) : null}
            <div className="space-y-3">
              <Button fullWidth onClick={handleAskAboutDocument} size="lg">
                <Icon name="chat" className="h-5 w-5" />{copy("Ask about this document")}
              </Button>
              <div className="grid grid-cols-2 gap-3">
                <Button
                  fullWidth
                  onClick={closeDocumentModal}
                  variant="secondary"
                >
                  {copy("Close")}
                </Button>
                <Button
                  fullWidth
                  onClick={() => fileInputRef.current?.click()}
                  variant="secondary"
                >
                  {copy("Upload another")}
                </Button>
              </div>
              {deleteError ? (
                <ErrorState
                  description={deleteError}
                  action={
                    <Button
                      onClick={() => void handleDeleteDocument()}
                      variant="secondary"
                      size="sm"
                    >
                      {copy("Try again")}
                    </Button>
                  }
                  title={copy("Could not delete document")}
                />
              ) : null}
              {deleteConfirming ? (
                <div className="ma-enter rounded-[22px] bg-danger-tint p-4">
                  <p className="text-base font-semibold text-danger-ink">
                    {copy("Delete this document?")}
                  </p>
                  <p className="mt-1 text-sm leading-6 text-danger-ink">
                    {copy(
                      "This removes the record from your documents. Existing care-plan items created from prior parsing are not removed.",
                    )}
                  </p>
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    <Button
                      disabled={isDeletingSelectedDocument}
                      fullWidth
                      onClick={() => setDeleteConfirming(false)}
                      variant="secondary"
                    >
                      {copy("Cancel")}
                    </Button>
                    <Button
                      disabled={isDeletingSelectedDocument}
                      fullWidth
                      onClick={() => void handleDeleteDocument()}
                      variant="danger"
                      className="!bg-danger-ink !text-white hover:!bg-[#8C2F1F]"
                    >
                      {isDeletingSelectedDocument
                        ? copy("Deleting")
                        : copy("Delete permanently")}
                    </Button>
                  </div>
                </div>
              ) : (
                <button
                  disabled={isDeletingSelectedDocument}
                  onClick={() => setDeleteConfirming(true)}
                  type="button"
                  className="ma-press flex min-h-11 w-full items-center justify-center rounded-2xl text-[15px] font-semibold text-danger-ink hover:bg-danger-tint disabled:opacity-50"
                >
                  {copy("Delete document")}
                </button>
              )}
            </div>
          </div>
        </Modal>
      </div>
    </PullToRefresh>
  );
}
