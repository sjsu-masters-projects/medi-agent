"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { ADRReviewCard } from "@/components/features/adr-review-card";
import { ErrorState, Skeleton } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import {
    createMedWatchDraft,
    fetchADRAssessment,
    fetchMedWatchDrafts,
    recordADRClinicianAnswers,
    reviewADRAssessment,
    type ADRClinicianAnswerInput,
    type ADRReviewDecisionInput,
    type ADRReviewQueueItem,
} from "@/services/clinicians";

function CaseSkeleton() {
    return (
        <div aria-label="Loading ADR case" className="space-y-5" role="status">
            <Skeleton className="h-4 w-48" variant="text" />
            <Skeleton className="h-8 w-72" />
            <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
                <div className="space-y-4">
                    <Skeleton className="h-36 w-full" />
                    <Skeleton className="h-48 w-full" />
                </div>
                <Skeleton className="h-56 w-full" />
            </div>
        </div>
    );
}

/** The queue URL (with its tab, search and page) this case was opened from. */
function backHref(from: string | null): string {
    return from ? `/adr-reviews?${from}` : "/adr-reviews";
}

function CaseContent() {
    const params = useParams<{ assessmentId: string }>();
    const assessmentId = params.assessmentId;
    const searchParams = useSearchParams();
    const router = useRouter();
    const [item, setItem] = useState<ADRReviewQueueItem | null>(null);
    const [draftId, setDraftId] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);
    const [notice, setNotice] = useState<string | null>(null);
    const [actionError, setActionError] = useState<string | null>(null);
    const [submitting, setSubmitting] = useState(false);
    const pending = useRef(false);

    const load = useCallback(async () => {
        setLoading(true);
        setError(false);
        try {
            const loaded = await fetchADRAssessment(assessmentId);
            setItem(loaded);
            setDraftId(null);
            if (loaded.status !== "draft") {
                // Past review the case may already have a report; link to it when it does.
                const [active, submitted] = await Promise.all([
                    fetchMedWatchDrafts("active"),
                    fetchMedWatchDrafts("submitted"),
                ]).catch(() => [[], []]);
                setDraftId(
                    [...active, ...submitted].find((draft) => draft.adrAssessmentId === loaded.id)?.id ?? null,
                );
            }
        } catch {
            setItem(null);
            setError(true);
        } finally {
            setLoading(false);
        }
    }, [assessmentId]);

    useEffect(() => {
        void load();
    }, [load]);

    const review = useCallback(
        async (id: string, input: ADRReviewDecisionInput) => {
            if (pending.current) return;
            pending.current = true;
            setSubmitting(true);
            setActionError(null);
            setNotice(null);
            try {
                await reviewADRAssessment(id, input);
                setNotice(
                    input.action === "request_information"
                        ? "Information request saved and audited."
                        : "ADR review saved and audited.",
                );
                await load();
            } catch {
                const message = "Unable to save the ADR review. Your draft is retained. Try again.";
                setActionError(message);
                throw new Error(message);
            } finally {
                pending.current = false;
                setSubmitting(false);
            }
        },
        [load],
    );

    const recordAnswers = useCallback(
        async (id: string, answers: ADRClinicianAnswerInput[], careTeamId?: string) => {
            if (pending.current) throw new Error("Busy");
            pending.current = true;
            setSubmitting(true);
            setActionError(null);
            setNotice(null);
            try {
                await (careTeamId
                    ? recordADRClinicianAnswers(id, answers, careTeamId)
                    : recordADRClinicianAnswers(id, answers));
                setNotice("Clinician answers saved and audited. The score was recalculated.");
                await load();
            } catch {
                const message = "Unable to save the clinician answers. Your answers are retained. Try again.";
                setActionError(message);
                throw new Error(message);
            } finally {
                pending.current = false;
                setSubmitting(false);
            }
        },
        [load],
    );

    const prepare = useCallback(
        async (id: string, rationale: string, careTeamId?: string) => {
            if (pending.current) throw new Error("Busy");
            pending.current = true;
            setSubmitting(true);
            try {
                const draft = await (careTeamId ? createMedWatchDraft(id, rationale, careTeamId) : createMedWatchDraft(id, rationale));
                router.push(`/medwatch/${draft.id}`);
            } catch {
                // The preparation form shows this failure once, inline.
                throw new Error("Unable to prepare the MedWatch draft. Try again.");
            } finally {
                pending.current = false;
                setSubmitting(false);
            }
        },
        [router],
    );

    return (
        <div className="ma-page space-y-5">
            {loading && !item ? <CaseSkeleton /> : null}
            {error ? (
                <ErrorState
                    action={
                        <Link className="text-sm font-semibold text-primary" href={backHref(searchParams.get("from"))}>
                            Back to ADR Reviews
                        </Link>
                    }
                    description="This case could not be loaded. It may no longer be available to you."
                    onRetry={() => void load()}
                    title="Unable to load this ADR case"
                />
            ) : null}
            {notice ? (
                <p className="ma-enter flex items-start gap-2.5 rounded-xl border border-ok-line bg-ok-soft px-4 py-3 text-sm text-ok-ink" role="status">
                    <Icon className="mt-0.5 h-4 w-4 shrink-0" name="check" />
                    {notice}
                </p>
            ) : null}
            {actionError ? (
                <p className="ma-enter flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink" role="alert">
                    <Icon className="mt-0.5 h-4 w-4 shrink-0" name="alert" />
                    {actionError}
                </p>
            ) : null}
            {item ? (
                <ADRReviewCard
                    backHref={backHref(searchParams.get("from"))}
                    item={item}
                    medwatchDraftId={draftId}
                    onPrepareDraft={prepare}
                    onRecordAnswers={recordAnswers}
                    onReview={review}
                    submitting={submitting || loading}
                />
            ) : null}
        </div>
    );
}

export default function ADRCasePage() {
    return (
        <Suspense fallback={<CaseSkeleton />}>
            <CaseContent />
        </Suspense>
    );
}
