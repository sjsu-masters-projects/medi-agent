"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  HiOutlineArrowPath,
  HiOutlineBeaker,
  HiOutlineClipboardDocumentCheck,
  HiOutlineExclamationTriangle,
} from "react-icons/hi2";
import { ADRReviewCard } from "@/components/features/adr-review-card";
import { MedWatchDraftCard } from "@/components/features/medwatch-draft-card";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Skeleton,
} from "@/components/ui";
import {
  fetchADRReviewQueue,
  fetchMedWatchDrafts,
  createMedWatchDraft,
  updateMedWatchDraft,
  approveMedWatchDraft,
  exportMedWatchDraft,
  reviewADRAssessment,
  type ADRReviewDecisionInput,
  type ADRReviewQueueItem,
  type MedWatchDraft,
  type MedWatchFormData,
} from "@/services/clinicians";

function LoadingQueue() {
  return (
    <div className="space-y-4" aria-label="Loading ADR reviews">
      <Skeleton className="h-48 w-full" />
      <Skeleton className="h-48 w-full" />
    </div>
  );
}

export default function MedWatchPage() {
  const [items, setItems] = useState<ADRReviewQueueItem[]>([]);
  const [drafts, setDrafts] = useState<MedWatchDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submittingId, setSubmittingId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const queuePending = useRef(false);
  const reviewPending = useRef(false);

  const loadQueue = useCallback(async () => {
    if (queuePending.current) return;
    queuePending.current = true;
    setLoading(true);
    setError(null);
    try {
      const [queue, medwatchDrafts] = await Promise.all([
        fetchADRReviewQueue(),
        fetchMedWatchDrafts(),
      ]);
      setItems(queue);
      setDrafts(medwatchDrafts);
    } catch {
      setError(
        "Unable to refresh ADR assessments. Try loading the queue again.",
      );
    } finally {
      queuePending.current = false;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadQueue();
  }, [loadQueue]);

  const reviewAssessment = useCallback(
    async (assessmentId: string, input: ADRReviewDecisionInput) => {
      if (reviewPending.current || queuePending.current || error) {
        throw new Error("Refresh the queue before reviewing an assessment.");
      }
      reviewPending.current = true;
      setSubmittingId(assessmentId);
      setReviewError(null);
      setNotice(null);
      try {
        await reviewADRAssessment(assessmentId, input);
        // A confirmed terminal write must not remain available for resubmission.
        if (input.action !== "request_information") {
          setItems((current) =>
            current.filter((item) => item.id !== assessmentId),
          );
        }
        setNotice(
          input.action === "request_information"
            ? "Information request saved and audited."
            : "ADR review saved and audited.",
        );
        await loadQueue();
      } catch {
        const message =
          "Unable to save the ADR review. Your draft is retained. Try again.";
        setReviewError(message);
        throw new Error(message);
      } finally {
        reviewPending.current = false;
        setSubmittingId(null);
      }
    },
    [error, loadQueue],
  );

  const prepareDraft = useCallback(
    async (assessmentId: string, rationale: string) => {
      if (reviewPending.current || queuePending.current || error) {
        throw new Error("Refresh the queue before preparing a draft.");
      }
      reviewPending.current = true;
      setSubmittingId(assessmentId);
      setReviewError(null);
      setNotice(null);
      try {
        const draft = await createMedWatchDraft(assessmentId, rationale);
        setItems((current) =>
          current.filter((item) => item.id !== assessmentId),
        );
        setDrafts((current) => [draft, ...current]);
        setNotice(
          "Editable MedWatch draft created. Nothing was submitted to the FDA.",
        );
      } catch {
        const message = "Unable to prepare the MedWatch draft. Try again.";
        setReviewError(message);
        throw new Error(message);
      } finally {
        reviewPending.current = false;
        setSubmittingId(null);
      }
    },
    [error],
  );

  const replaceDraft = useCallback((updated: MedWatchDraft) => {
    setDrafts((current) =>
      current.map((draft) => (draft.id === updated.id ? updated : draft)),
    );
  }, []);

  const saveDraft = useCallback(
    async (draftId: string, formData: MedWatchFormData, revision: number) => {
      setSubmittingId(draftId);
      setNotice(null);
      try {
        replaceDraft(await updateMedWatchDraft(draftId, formData, revision));
        setNotice("MedWatch draft changes saved and audited.");
      } finally {
        setSubmittingId(null);
      }
    },
    [replaceDraft],
  );

  const approveDraft = useCallback(
    async (draftId: string, note: string, revision: number) => {
      setSubmittingId(draftId);
      setNotice(null);
      try {
        replaceDraft(await approveMedWatchDraft(draftId, note, revision));
        setNotice(
          "MedWatch draft approved for export. It was not submitted to the FDA.",
        );
      } finally {
        setSubmittingId(null);
      }
    },
    [replaceDraft],
  );

  const exportDraft = useCallback(async (draftId: string) => {
    setSubmittingId(draftId);
    setNotice(null);
    try {
      const artifact = await exportMedWatchDraft(draftId);
      const blob = new Blob([JSON.stringify(artifact.content, null, 2)], {
        type: artifact.media_type,
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = artifact.filename;
      anchor.click();
      URL.revokeObjectURL(url);
      setNotice(
        "Approved draft exported locally. No FDA submission was performed.",
      );
    } finally {
      setSubmittingId(null);
    }
  }, []);

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-gray-900">
            ADR Review Queue
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Review deterministic Naranjo assistance and the patient’s source
            evidence.
          </p>
        </div>
        <button
          disabled={loading || Boolean(submittingId)}
          className="flex items-center justify-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50"
          onClick={() => void loadQueue()}
          type="button"
        >
          <HiOutlineArrowPath aria-hidden="true" className="h-4 w-4" />
          Refresh
        </button>
      </div>

      <section className="grid gap-4 md:grid-cols-3">
        <Card className="flex items-center gap-3" padding="sm">
          <div className="rounded-full bg-yellow-100 p-3 text-yellow-800">
            <HiOutlineExclamationTriangle className="h-5 w-5" />
          </div>
          <div>
            <p className="text-sm text-gray-500">Pending ADR reviews</p>
            <p className="text-2xl font-bold text-gray-900">{items.length}</p>
          </div>
        </Card>
        <Card className="flex items-center gap-3" padding="sm">
          <div className="rounded-full bg-blue-100 p-3 text-blue-800">
            <HiOutlineBeaker className="h-5 w-5" />
          </div>
          <div>
            <p className="text-sm text-gray-500">Scoring</p>
            <p className="text-sm font-semibold text-gray-900">
              Deterministic Naranjo assistance
            </p>
          </div>
        </Card>
        <Card className="flex items-center gap-3" padding="sm">
          <div className="rounded-full bg-green-100 p-3 text-green-800">
            <HiOutlineClipboardDocumentCheck className="h-5 w-5" />
          </div>
          <div>
            <p className="text-sm text-gray-500">MedWatch status</p>
            <p className="text-sm font-semibold text-gray-900">
              {drafts.filter((draft) => draft.status === "draft").length}{" "}
              awaiting approval
            </p>
          </div>
        </Card>
      </section>

      {notice ? (
        <p
          className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800"
          role="status"
        >
          {notice}
        </p>
      ) : null}

      {reviewError ? (
        <p
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          {reviewError}
        </p>
      ) : null}
      {loading && items.length === 0 && drafts.length === 0 ? (
        <LoadingQueue />
      ) : null}
      {loading && (items.length > 0 || drafts.length > 0) ? (
        <p role="status">Refreshing ADR reviews…</p>
      ) : null}
      {!loading && error && items.length === 0 && drafts.length === 0 ? (
        <ErrorState
          description={error}
          onRetry={() => void loadQueue()}
          title="Unable to load ADR reviews"
        />
      ) : null}
      {error && (items.length > 0 || drafts.length > 0) ? (
        <Card>
          <p role="alert">{error}</p>
          <Button
            disabled={loading || Boolean(submittingId)}
            onClick={() => void loadQueue()}
            variant="ghost"
          >
            Try again
          </Button>
        </Card>
      ) : null}
      {!loading && !error && items.length === 0 && drafts.length === 0 ? (
        <EmptyState
          description="New patient-grounded ADR assessments will appear here for clinician review."
          icon={<HiOutlineExclamationTriangle />}
          title="No ADR assessments awaiting review"
        />
      ) : null}
      {items.length > 0 ? (
        <section
          className="space-y-4"
          aria-label="ADR assessments awaiting review"
        >
          {items.map((item) => (
            <ADRReviewCard
              item={item}
              key={item.id}
              onPrepareDraft={prepareDraft}
              onReview={reviewAssessment}
              submitting={Boolean(submittingId) || loading || Boolean(error)}
            />
          ))}
        </section>
      ) : null}
      {drafts.length > 0 ? (
        <section className="space-y-4" aria-label="MedWatch drafts">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">
              MedWatch drafts
            </h2>
            <p className="mt-1 text-sm text-gray-500">
              Edit, approve, and export evidence-backed artifacts. This workflow
              never submits to the FDA.
            </p>
          </div>
          {drafts.map((draft) => (
            <MedWatchDraftCard
              busy={Boolean(submittingId) || loading || Boolean(error)}
              draft={draft}
              key={draft.id}
              onApprove={approveDraft}
              onExport={exportDraft}
              onSave={saveDraft}
            />
          ))}
        </section>
      ) : null}
    </div>
  );
}
