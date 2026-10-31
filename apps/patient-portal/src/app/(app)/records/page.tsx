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
import { RecordActions } from "@/components/features/record-actions";
import { RecordOrigin, recordOriginLabel } from "@/components/features/record-origin";
import { RecordReviewStatus } from "@/components/features/record-review-status";
import {
  EXPLANATION_SLOW_MS,
  ExplanationPending,
  ExplanationSections,
} from "@/components/features/explanation-sections";
import { useDocumentExplanation } from "@/hooks/use-document-explanation";
import { ListenBars, ProcessingDots, useReducedMotion } from "@/components/ui/motion";
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
import { apiErrorCode, fetchUploadCareTeamOptions, type DocumentRoutingChoice } from "@/services/care-team-routing";
import { ConditionsPrivacy } from "@/components/features/conditions-privacy";
import { UploadCareTeamPicker } from "@/components/features/upload-care-team-picker";
import { hydrateSession, logout } from "@/store/slices/auth-slice";
import type { AppDispatch, RootState } from "@/store/store";
import {
  DEFAULT_LOCALE,
  DocumentParseStatus,
  Locale,
  getDocumentTypeLabel,
  type Document,
  type UploadCareTeamOption,
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
  "The explanation is unavailable in your language right now. Please try again.";
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
    "There are no saved details from this document to explain. You can still open the original document above or ask your care team about it.",
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
    ? "Este mismo archivo ya está en tus documentos. Guardamos esta copia sin agregar nuevos datos médicos ni indicaciones al plan de atención. Puedes abrir el original o consultar a tu equipo de atención."
    : "This file is already in your records. We kept this copy without adding new medical details or care-plan instructions. You can open the original or ask your care team about it.";
}
const INITIAL_POLL_DELAY_MS = 3_000;
const MAX_POLL_DELAY_MS = 30_000;
/** Visible checking time before a document is shown as "Still processing" with Refresh. */
const POLL_WATCH_LIMIT_MS = 10 * 60_000;
/** Matches the record modal's exit and the row's `ma-leave`. */
const MODAL_EXIT_MS = 160;
const ROW_LEAVE_MS = 160;

type UploadPhase = "preparing" | "uploading";
type UploadError = { message: string; action: "choose" | "refresh" | null };
type ProcessingOutcome = "ready" | "duplicate" | "failed";

/** Resolves after `ms`, or at once when the page stops watching. */
function pause(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve) => {
    const timer = window.setTimeout(done, ms);
    function done() {
      window.clearTimeout(timer);
      signal.removeEventListener("abort", done);
      resolve();
    }
    signal.addEventListener("abort", done, { once: true });
  });
}

/** A hidden tab does not poll; checking resumes when the patient comes back. */
function untilVisible(signal: AbortSignal) {
  if (document.visibilityState !== "hidden" || signal.aborted) return Promise.resolve();
  return new Promise<void>((resolve) => {
    function done() {
      if (document.visibilityState === "hidden" && !signal.aborted) return;
      document.removeEventListener("visibilitychange", done);
      signal.removeEventListener("abort", done);
      resolve();
    }
    document.addEventListener("visibilitychange", done);
    signal.addEventListener("abort", done, { once: true });
  });
}
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

function isDocumentWorkPending(document: PortalDocument) {
  return isDocumentProcessing(document.parseStatus) || (
    document.parseStatus === DocumentParseStatus.COMPLETED &&
    !document.aiSummary &&
    (document.summaryStatus === "pending" || document.summaryStatus === "processing")
  );
}

/** Where a polled document ended up; null while it is still being read. */
function processingOutcome(document: PortalDocument): ProcessingOutcome | null {
  if (document.parseStatus === DocumentParseStatus.DUPLICATE) return "duplicate";
  if (
    document.parseStatus === DocumentParseStatus.FAILED ||
    needsHumanDocumentReview(document.parseStatus)
  )
    return "failed";
  if (isDocumentWorkPending(document)) return null;
  if (document.parsed || document.parseStatus === DocumentParseStatus.COMPLETED)
    return "ready";
  return null;
}

function announceOutcome(title: string, outcome: ProcessingOutcome, locale: Locale) {
  const spanish = locale === "es-MX";
  if (outcome === "ready")
    return spanish ? `Ya puedes consultar ${title}.` : `${title} is ready to view.`;
  if (outcome === "duplicate")
    return spanish ? `Ya tenías este archivo: ${title}.` : `${title} was already on file.`;
  return spanish ? `No pudimos procesar ${title}.` : `We could not process ${title}.`;
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
    reviewStatus: record.review_status ?? undefined,
    reviewedAt: record.reviewed_at ?? undefined,
    parsed: record.parsed,
    patientId: record.patient_id,
    // The recorded clinic only; who uploaded it is shown separately (RecordOrigin).
    provider: record.source_clinic ?? "",
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
  const actorId = useSelector((state: RootState) => state.auth.user?.id);
  return <RecordsWorkspace key={actorId ?? "signed-out"} />;
}

function RecordsWorkspace() {
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
  const [selectedRecord, setSelectedDocument] =
    useState<PortalDocument | null>(null);
  const selectedDocument = documents.find((document) => document.id === selectedRecord?.id) ?? selectedRecord;
  const [loading, setLoading] = useState(true);
  // A count or empty state is shown only after a successful read, never an invented zero.
  const [hasLoaded, setHasLoaded] = useState(false);
  // List-loading errors only; upload problems use `uploadError`.
  const [pageError, setPageError] = useState<string | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<UploadError | null>(null);
  const [readbackKey, setReadbackKey] = useState<string | null>(null);
  const stopReadback = useRef<(() => void) | null>(null);
  const [parsingDocIds, setParsingDocIds] = useState<Set<string>>(new Set());
  const [stalledDocIds, setStalledDocIds] = useState<Set<string>>(new Set());
  const [readyDocIds, setReadyDocIds] = useState<Set<string>>(new Set());
  const [addedDocIds, setAddedDocIds] = useState<Set<string>>(new Set());
  const [leavingDocIds, setLeavingDocIds] = useState<Set<string>>(new Set());
  const [lastOutcome, setLastOutcome] = useState<{ id: string; outcome: ProcessingOutcome } | null>(null);
  const [removalNotice, setRemovalNotice] = useState(false);
  const [closingModal, setClosingModal] = useState(false);
  const [uploadPhase, setUploadPhase] = useState<UploadPhase | null>(null);
  const uploading = uploadPhase !== null;
  const [routingPrompt, setRoutingPrompt] = useState<{ file: File; options: UploadCareTeamOption[] } | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const statusAreaRef = useRef<HTMLDivElement | null>(null);
  const activePollsRef = useRef(new Set<string>());
  const pollController = useRef<AbortController | null>(null);
  const listVersion = useRef({ value: 0 });
  const reducedMotion = useReducedMotion();
  const { accessToken, expiresAt, refreshToken, user } = useSelector(
    (state: RootState) => state.auth,
  );
  // Polls can outlive a token refresh; each request uses the current session.
  const tokenRef = useRef(accessToken);
  useEffect(() => {
    tokenRef.current = accessToken;
  }, [accessToken]);

  const eligibleForExplanation =
    selectedDocument?.parseStatus === DocumentParseStatus.COMPLETED &&
    !parsingDocIds.has(selectedDocument.id);
  const explanation = useDocumentExplanation({
    documentId: eligibleForExplanation ? selectedDocument.id : null,
    source: selectedDocument?.aiSummary,
    locale,
    token: accessToken,
    actorId: user?.id,
  });
  const explanationLang = locale;
  const explanationLoading = explanation.loading;
  const explanationAvailable = Boolean(explanation.data);
  const explanationText = (() => {
    if (!selectedDocument) return null;
    if (selectedDocument.parseStatus === DocumentParseStatus.DUPLICATE)
      return duplicateUploadMessage(locale);
    if (isDocumentProcessing(selectedDocument.parseStatus))
      return copy(PARSING_IN_PROGRESS_MESSAGE);
    if (
      selectedDocument.parseStatus === "failed" ||
      needsHumanDocumentReview(selectedDocument.parseStatus)
    )
      return describeParseFailure(selectedDocument.parseFailureCode, locale);
    if (!selectedDocument.aiSummary)
      return describeMissingSummary(selectedDocument, locale);
    if (explanation.data) return explanation.data.summary;
    return explanation.loading
      ? copy("Preparing your explanation…")
      : copy(EXPLANATION_UNAVAILABLE_MESSAGE);
  })();
  const playbackKey = JSON.stringify([
    selectedDocument?.id,
    locale,
    user?.id,
    accessToken,
    explanation.data?.summary,
  ]);
  const readbackActive = readbackKey === playbackKey;
  useEffect(
    () => () => {
      stopReadback.current?.();
      stopReadback.current = null;
    },
    [playbackKey],
  );

  const IMPORT_REFRESH_WINDOW_SECONDS = 2 * 60;

  const loadDocuments = useCallback(async () => {
    if (!accessToken) {
      return;
    }

    const request = ++listVersion.current.value;
    setLoading(true);
    setRemovalNotice(false);
    try {
      const result = await api.get<DocumentApiRecord[]>("/api/v1/documents/", {
        token: accessToken,
      });
      if (request !== listVersion.current.value) return;
      setDocuments(result.map(mapDocument));
      setPageError(null);
      setHasLoaded(true);
      // A successful Refresh resumes checking documents that were left "Still processing".
      setStalledDocIds(new Set());
    } catch {
      if (request === listVersion.current.value)
        setPageError(copy("We could not load your documents. Please try again."));
    } finally {
      if (request === listVersion.current.value) setLoading(false);
    }
  }, [accessToken, copy]);

  const openDocument = useCallback(
    (document: PortalDocument) => {
      setRemovalNotice(false);
      setClosingModal(false);
      setSelectedDocument(document);
    },
    [],
  );

  // The record stays selected through the modal's short exit so its content does not
  // flash; speech stops at once because closing is the patient's stop signal.
  const closeDocumentModal = useCallback(() => {
    stopReadback.current?.();
    stopReadback.current = null;
    setReadbackKey(null);
    setClosingModal(true);
  }, []);

  const finishModalExit = useCallback(() => {
    setSelectedDocument(null);
    setClosingModal(false);
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
    const controller = new AbortController();
    pollController.current = controller;
    const activePolls = activePollsRef.current;
    const listRequests = listVersion.current;
    return () => {
      listRequests.value++;
      controller.abort();
      activePolls.clear();
    };
  }, []);

  /**
   * Watches one document until it is read, with 3s→30s backoff. Hidden tabs pause, and
   * after ten minutes of visible checking the row becomes "Still processing" with
   * Refresh, so the moving dots never promise an update the page is not waiting for.
   */
  const pollForParsedStatus = useCallback(
    async (docId: string) => {
      const signal = pollController.current?.signal;
      if (!signal || signal.aborted || activePollsRef.current.has(docId)) return;
      activePollsRef.current.add(docId);
      setParsingDocIds((current) => addTrackedDocumentId(current, docId));

      let delayMs = INITIAL_POLL_DELAY_MS;
      let watchedMs = 0;
      try {
        while (activePollsRef.current.has(docId)) {
          await pause(delayMs, signal);
          watchedMs += delayMs;
          await untilVisible(signal);
          if (!activePollsRef.current.has(docId)) return;
          try {
            const record = await api.get<DocumentApiRecord>(
              `/api/v1/documents/${docId}`,
              { token: tokenRef.current ?? undefined },
            );
            if (!activePollsRef.current.has(docId)) return;
            const nextDocument = mapDocument(record);
            setDocuments((current) =>
              current.map((document) =>
                document.id === docId ? {
                  ...nextDocument,
                  // Background metadata reads renew signed URLs. Keep an already
                  // available preview steady while the patient reads it; explicit
                  // Refresh still obtains fresh URLs, including after expiry.
                  fileUrl: document.fileUrl,
                  previewUrl: document.previewStatus === "ready"
                    ? document.previewUrl
                    : nextDocument.previewUrl,
                } : document,
              ),
            );
            const outcome = processingOutcome(nextDocument);
            if (outcome) {
              // Drop the entrance mark first so the row does not replay it after the highlight.
              setAddedDocIds((current) => removeTrackedDocumentId(current, docId));
              setReadyDocIds((current) => addTrackedDocumentId(current, docId));
              setLastOutcome({ id: docId, outcome });
              if (outcome === "failed")
                setParseError(
                  describeParseFailure(nextDocument.parseFailureCode, locale),
                );
              return;
            }
          } catch {
            // A queue-backed worker can outlive a short network failure.
          }
          if (watchedMs >= POLL_WATCH_LIMIT_MS) {
            setStalledDocIds((current) => addTrackedDocumentId(current, docId));
            return;
          }
          delayMs = Math.min(delayMs * 2, MAX_POLL_DELAY_MS);
        }
      } finally {
        activePollsRef.current.delete(docId);
        setParsingDocIds((current) => removeTrackedDocumentId(current, docId));
      }
    },
    [locale],
  );

  // Documents already processing when the page loads are watched too, not only new uploads.
  useEffect(() => {
    for (const document of documents) {
      if (
        isDocumentWorkPending(document) &&
        !stalledDocIds.has(document.id)
      )
        void pollForParsedStatus(document.id);
    }
  }, [documents, stalledDocIds, pollForParsedStatus]);

  // A patient-started upload or upload error is brought into view; background changes are not.
  useEffect(() => {
    if (!uploadPhase && !uploadError) return;
    statusAreaRef.current?.scrollIntoView?.({
      block: "nearest",
      behavior: reducedMotion ? "auto" : "smooth",
    });
  }, [uploadPhase, uploadError, reducedMotion]);

  async function getUploadSession() {
    if (!accessToken || !user) {
      setUploadError({
        message: copy("Please sign in again before uploading a document."),
        action: null,
      });
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
      setUploadError({
        message: copy("Your session expired. Please sign in again before uploading."),
        action: null,
      });
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
    setUploadError({
      message: copy("Your session expired. Please sign in again before uploading."),
      action: null,
    });
    return null;
  }

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    // "Upload another" starts from an open record; close it so progress is visible.
    if (selectedDocument) closeDocumentModal();
    setRemovalNotice(false);

    const validationError = getUploadValidationError(file);
    if (validationError) {
      setUploadError({ message: copy(validationError), action: "choose" });
      event.target.value = "";
      return;
    }

    event.target.value = "";
    setUploadError(null);
    setParseError(null);
    // PLAN-002: ask which care team the document is for before anything is uploaded. When
    // the care teams cannot be read, the server's own routing rule applies and any
    // CARE_TEAM_REQUIRED answer reopens this question.
    if (accessToken) {
      setUploadPhase("preparing");
      const options = await fetchUploadCareTeamOptions(accessToken);
      setUploadPhase(null);
      if (options && options.length > 0) {
        setRoutingPrompt({ file, options });
        return;
      }
    }
    await uploadFile(file);
  }

  async function uploadFile(file: File, routing?: DocumentRoutingChoice) {
    setUploadError(null);
    setParseError(null);
    setUploadPhase("uploading");

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
          ...(routing ?? {}),
        },
        { token: session.accessToken },
      );
      const nextDocument = mapDocument(created);
      setAddedDocIds((current) => addTrackedDocumentId(current, nextDocument.id));
      setDocuments((current) => [nextDocument, ...current]);
      // Candidate-only ingestion runs in the background. It never updates
      // the patient's canonical profile until a clinician reconciles it.
      void pollForParsedStatus(nextDocument.id);
    } catch (error) {
      if (apiErrorCode(error) === "CARE_TEAM_REQUIRED" && accessToken) {
        // The server needs an explicit choice: ask, then upload the same file.
        setUploadPhase("preparing");
        const options = await fetchUploadCareTeamOptions(accessToken);
        if (options && options.length > 0) {
          setRoutingPrompt({ file, options });
          return;
        }
      }
      setUploadError({
        message: copy("Upload failed. Please refresh your records before trying again."),
        action: "refresh",
      });
    } finally {
      setUploadPhase(null);
    }
  }

  function handleAskAboutDocument() {
    if (!selectedDocument) {
      return;
    }

    const documentName = recordTitle(selectedDocument, explanationLang, patientName);
    const handoffProvider =
      displayProvider(selectedDocument) ??
      recordOriginLabel(selectedDocument, explanationLang) ??
      undefined;
    storePendingChatDocumentContext({
      documentId: selectedDocument.id,
      documentName,
      documentType: selectedDocument.documentType,
      preferredLanguage: explanationLang,
      // Shown on Nora's "about this record" card, so it must be patient wording in the
      // patient's language, never the internal upload marker.
      provider: handoffProvider,
      suggestedQuestion: buildSuggestedDocumentQuestion({
        documentName,
        documentType: selectedDocument.documentType,
        preferredLanguage: explanationLang,
        provider: handoffProvider,
      }),
      summary: explanationAvailable
        ? explanation.data?.summary
        : undefined,
    });

    closeDocumentModal();
    router.push(buildDocumentChatHref(selectedDocument.id));
  }

  function handleReadSummary() {
    if (!explanation.data) return;
    if (readbackActive) {
      stopReadback.current?.();
      stopReadback.current = null;
      setReadbackKey(null);
      return;
    }
    stopReadback.current?.();
    stopReadback.current = playAssistantVoiceResponse({
      language: explanationLang,
      onEnd: () => setReadbackKey((current) => current === playbackKey ? null : current),
      onStart: () => setReadbackKey(playbackKey),
      text: explanation.data.summary,
    });
  }

  const processingCount = documents.filter(
    (document) =>
      parsingDocIds.has(document.id) ||
      isDocumentWorkPending(document),
  ).length;

  /** Removal reads in order: the record closes, its row leaves, then the notice appears. */
  function removeRowAfterExit(id: string) {
    activePollsRef.current.delete(id);
    window.setTimeout(() => {
      setLeavingDocIds((current) => addTrackedDocumentId(current, id));
      window.setTimeout(() => {
        setDocuments((current) => current.filter((document) => document.id !== id));
        setParsingDocIds((current) => removeTrackedDocumentId(current, id));
        setLeavingDocIds((current) => removeTrackedDocumentId(current, id));
        setRemovalNotice(true);
      }, reducedMotion ? 0 : ROW_LEAVE_MS);
    }, reducedMotion ? 0 : MODAL_EXIT_MS);
  }

  const patientName = [profile?.firstName, profile?.lastName].filter(Boolean).join(" ");
  const spanish = locale === "es-MX";
  const outcomeDocument = lastOutcome
    ? documents.find((document) => document.id === lastOutcome.id)
    : undefined;
  const outcomeAnnouncement =
    lastOutcome && outcomeDocument
      ? announceOutcome(recordTitle(outcomeDocument, locale, patientName), lastOutcome.outcome, locale)
      : "";
  const selectedProcessing = Boolean(
    selectedDocument &&
      selectedDocument.parseStatus !== DocumentParseStatus.DUPLICATE &&
      (isDocumentProcessing(selectedDocument.parseStatus) ||
        parsingDocIds.has(selectedDocument.id)),
  );
  const selectedStalled = Boolean(
    selectedProcessing &&
      selectedDocument &&
      stalledDocIds.has(selectedDocument.id) &&
      !parsingDocIds.has(selectedDocument.id),
  );
  // A real clinic name, or nothing. Upload markers repeated the origin line ("Your upload"
  // beside "Uploaded by you"), and a "Care team" placeholder could contradict it.
  const displayProvider = (document: PortalDocument): string | null => {
    const clinic = document.provider.trim();
    if (!clinic || clinic === "Patient uploaded document" || clinic === "Clinician uploaded document") return null;
    return clinic;
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
      indicateBusy={false}
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
              <button
                type="button"
                aria-label={copy(loading ? "Refreshing..." : "Refresh records")}
                title={copy("Refresh records")}
                disabled={loading || uploading}
                onClick={() => void loadDocuments()}
                className="ma-press flex h-11 w-11 items-center justify-center rounded-[14px] text-ink-2 hover:bg-surface-2 disabled:opacity-50"
              >
                <Icon name="refresh" className={`h-5 w-5 ${loading ? "animate-spin motion-reduce:animate-none" : ""}`} />
              </button>
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
          {/* Keeps the last successful count during a refresh so the list does not jump. */}
          {hasLoaded && !(pageError && documents.length === 0) && <p className="mt-1 text-sm text-muted" role="status">
            {spanish
              ? `${documents.length} ${documents.length === 1 ? "documento" : "documentos"}${processingCount ? ` · ${processingCount} en proceso` : ""}`
              : `${documents.length} ${documents.length === 1 ? "record" : "records"}${processingCount ? ` · ${processingCount} processing` : ""}`}
          </p>}
          <p className="sr-only" role="status">{outcomeAnnouncement}</p>
        </header>
        <input
          accept={UPLOAD_ACCEPT_ATTRIBUTE}
          className="hidden"
          onChange={handleFileChange}
          ref={fileInputRef}
          type="file"
        />
        {routingPrompt ? (
          <UploadCareTeamPicker
            key={routingPrompt.file.name}
            open
            locale={locale}
            fileName={routingPrompt.file.name}
            options={routingPrompt.options}
            busy={uploading}
            onCancel={() => setRoutingPrompt(null)}
            onConfirm={(choice) => {
              const file = routingPrompt.file;
              setRoutingPrompt(null);
              void uploadFile(file, choice);
            }}
          />
        ) : null}
        <div ref={statusAreaRef} className="scroll-mt-4 space-y-3 px-4 pt-4 empty:hidden">
          {documentUnavailable && <p role="alert" className="ma-enter rounded-2xl bg-danger-tint p-3 text-sm text-danger-ink">{spanish ? "Este documento no está disponible. Actualiza tus registros." : "This document is unavailable. Refresh your records."}</p>}
          {uploadPhase ? (
            <p
              role="status"
              className="ma-enter flex items-center gap-3 rounded-[22px] bg-brand-tint px-4 py-3.5 text-sm font-medium text-brand-ink"
            >
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-surface text-brand"><Icon name="up" className="h-[18px] w-[18px]" /></span>
              <span className="flex-1">
                {uploadPhase === "preparing"
                  ? copy("Getting your upload ready…")
                  : spanish ? "Subiendo documento..." : "Uploading document..."}
              </span>
              <ProcessingDots className="bg-brand" />
            </p>
          ) : null}
          {removalNotice ? (
            // Neutral on purpose: removal is a completed patient action, not an approval.
            <p
              role="status"
              className="ma-enter flex items-center gap-2.5 rounded-2xl bg-surface px-4 py-3 text-sm font-medium text-ink-2"
            >
              <Icon name="check" className="h-4 w-4 shrink-0 text-muted" />
              {copy("Your upload was removed.")}
            </p>
          ) : null}
          {uploadError ? (
            <div role="alert" className="ma-enter">
              <ErrorState
                description={uploadError.message}
                action={
                  uploadError.action === "choose" ? (
                    <Button
                      onClick={() => {
                        setUploadError(null);
                        fileInputRef.current?.click();
                      }}
                      variant="secondary"
                      size="sm"
                    >
                      {copy("Choose another file")}
                    </Button>
                  ) : uploadError.action === "refresh" ? (
                    <Button
                      disabled={loading}
                      onClick={() => {
                        setUploadError(null);
                        void loadDocuments();
                      }}
                      variant="secondary"
                      size="sm"
                    >
                      {copy("Refresh records")}
                    </Button>
                  ) : undefined
                }
                title={copy("Could not upload this file")}
              />
            </div>
          ) : null}
          {pageError && documents.length === 0 ? (
            <div role="alert" className="ma-enter">
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
            </div>
          ) : null}
          {pageError && documents.length > 0 ? (
            <div role="alert" className="ma-enter">
              <ErrorState
                description={pageError}
                action={
                  <Button
                    disabled={loading}
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
                title={copy("Could not refresh records")}
              />
            </div>
          ) : null}
          {parseError ? (
            <div role="alert" className="ma-enter">
              <ErrorState
                description={parseError}
                action={
                  // Patients have no processing retry; this starts a new upload.
                  <Button
                    onClick={() => {
                      setParseError(null);
                      fileInputRef.current?.click();
                    }}
                    variant="secondary"
                    size="sm"
                  >
                    {copy("Upload another")}
                  </Button>
                }
                title={copy("Document processing failed")}
              />
            </div>
          ) : null}
          {loading && !hasLoaded ? (
            // Shaped like the grouped list it is replacing.
            <div aria-hidden="true" className="pt-1">
              <Skeleton className="ml-1.5 h-3 w-24" variant="text" />
              <div className="mt-3 overflow-hidden rounded-[22px] bg-surface [&>*+*]:border-t [&>*+*]:border-line">
                {["w-3/5", "w-1/2", "w-2/3"].map((width) => (
                  <div key={width} className="flex items-center gap-3 px-[14px] py-[13px]">
                    <Skeleton className="h-11 w-11 shrink-0 !rounded-[13px]" />
                    <div className="min-w-0 flex-1 space-y-2">
                      <Skeleton className={`h-3.5 ${width}`} variant="text" />
                      <Skeleton className="h-3 w-2/5" variant="text" />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {loading ? (
            <p className="sr-only" role="status">
              {copy("Loading documents...")}
            </p>
          ) : null}
          {hasLoaded && !pageError && documents.length === 0 ? (
            <div className="ma-enter rounded-[22px] bg-surface">
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
                      entering={addedDocIds.has(document.id)}
                      leaving={leavingDocIds.has(document.id)}
                      highlight={readyDocIds.has(document.id)}
                      onHighlightEnd={() =>
                        setReadyDocIds((current) => removeTrackedDocumentId(current, document.id))
                      }
                      stalled={stalledDocIds.has(document.id) && !parsingDocIds.has(document.id)}
                    />
                  );
                })}
              </div>
            </section>
          ))}
        </div>
        {!loading && !pageError ? <ConditionsPrivacy locale={locale} /> : null}
        <Modal
          onClose={closeDocumentModal}
          stickyHeader
          open={Boolean(selectedDocument) && !closingModal}
          animateExit
          onExited={finishModalExit}
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
              {/* The original file name lives with the source below, not under the title. */}
              {selectedDocument ? <RecordOrigin document={selectedDocument} locale={locale} /> : null}
              <RecordReviewStatus status={selectedDocument?.reviewStatus} locale={locale} />
              {selectedDocument?.reviewStatus === "approved" ? <p className="text-sm leading-6 text-muted">{copy("Source approval does not approve this explanation or change your treatment.")}</p> : null}
            </div>
            <details className="group rounded-[22px] border border-line-strong bg-surface">
              <summary className="flex min-h-12 cursor-pointer list-none items-center gap-3 px-4 py-2 font-semibold text-ink [&::-webkit-details-marker]:hidden">
                <Icon name="file" className="h-5 w-5 text-muted" />
                <span className="flex-1">{copy("Source document")}</span>
                <Icon name="chevronDown" className="h-[18px] w-[18px] text-muted transition-transform duration-[240ms] group-open:rotate-180" />
              </summary>
              {/* Restarts its enter animation each time the disclosure opens. */}
              <div className="ma-enter border-t border-line px-4 pt-3 pb-4">
                {selectedDocument?.fileName ? (
                  <p className="mb-2 break-words text-sm text-ink-2 [overflow-wrap:anywhere]">
                    {copy("Original file")}: {selectedDocument.fileName}
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
            <div className="rounded-[22px] bg-surface-2/50 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="inline-flex items-center gap-1.5 rounded-full bg-surface px-2.5 py-1 text-xs font-medium text-muted">
                  <Icon name="spark" className="h-3.5 w-3.5 text-brand" />
                  {copy("AI explanation")}
                </p>
                <div className="flex shrink-0 items-center gap-2">
                  <button
                    aria-label={copy(readbackActive ? "Stop reading" : "Read summary aloud")}
                    className="ma-press flex h-11 w-11 items-center justify-center rounded-xl bg-surface text-brand-ink hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={!explanationAvailable}
                    onClick={handleReadSummary}
                    type="button"
                  >
                    {readbackActive ? <ListenBars /> : <Icon name="speaker" className="h-5 w-5" />}
                  </button>
                </div>
              </div>
              {/* Not aria-busy: the pending status and slow note need to be announced. */}
              <div aria-live="polite">
                {explanation.data ? (
                  <ExplanationSections sections={explanation.data.sections} locale={locale} />
                ) : explanationLoading ? (
                  <ExplanationPending
                    key={`${selectedDocument?.id}:${locale}:explanation`}
                    label={explanationText ?? ""}
                    locale={locale}
                    placeholder
                    slowAfterMs={EXPLANATION_SLOW_MS}
                  />
                ) : selectedProcessing && !selectedStalled ? (
                  <ExplanationPending
                    key={`${selectedDocument?.id}:${locale}:processing`}
                    label={explanationText ?? ""}
                    locale={locale}
                  />
                ) : (
                  <p lang={locale} className="mt-3 break-words text-base leading-7 text-ink">{explanationText}</p>
                )}
                {selectedStalled ? (
                  <div className="ma-enter mt-3 flex flex-wrap items-center gap-3">
                    <p className="min-w-0 flex-1 basis-[200px] text-sm leading-6 text-muted">
                      {copy("We stopped checking automatically. Refresh to see the latest status.")}
                    </p>
                    <Button variant="secondary" size="sm" disabled={loading} onClick={() => void loadDocuments()}>
                      {copy("Refresh records")}
                    </Button>
                  </div>
                ) : null}
                {explanation.failed ? <Button variant="secondary" size="sm" onClick={explanation.retry} className="mt-3">{copy("Try again")}</Button> : null}
              </div>
              {readbackActive ? <p role="status" className="mt-2 text-sm text-brand-ink">{copy("Reading aloud…")}</p> : null}
              <p className="mt-3 border-t border-line-strong pt-3 text-[13px] leading-5 text-muted" lang={explanationLang}>
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
              <Button
                fullWidth
                onClick={() => fileInputRef.current?.click()}
                variant="secondary"
              >
                {copy("Upload another")}
              </Button>
              {selectedDocument && accessToken && user ? <RecordActions
                key={`${user.id}:${accessToken}:${selectedDocument.id}`}
                document={selectedDocument}
                locale={locale}
                token={accessToken}
                actorId={user.id}
                onRemoved={() => {
                  const id = selectedDocument.id;
                  closeDocumentModal();
                  removeRowAfterExit(id);
                }}
                onRequest={() => {
                  const id = selectedDocument.id;
                  closeDocumentModal();
                  router.push(`/chat?view=care-team&record_request=${encodeURIComponent(id)}`);
                }}
              /> : null}
            </div>
          </div>
        </Modal>
      </div>
    </PullToRefresh>
  );
}
