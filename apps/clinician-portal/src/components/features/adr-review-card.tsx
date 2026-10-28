import Link from "next/link";
import { Badge } from "@/components/ui";
import { AiChip } from "@/components/ui/ai-chip";
import { Icon } from "@/components/ui/icons";
import { ADRClinicianAnswers } from "@/components/features/adr-clinician-answers";
import { questionLabel } from "@/components/features/adr-questions";
import { ADRReviewActions } from "@/components/features/adr-review-actions";
import { EvidenceGlossLine, glossFor, useEvidenceGlosses, type GlossMap } from "@/components/features/evidence-gloss";
import { queueTabOf, STATUS_LABELS, type QueueTab } from "@/components/features/adr-queue";
import { CareTeamSelect, useCareTeamChoice } from "@/components/features/care-team-select";
import { MedWatchPreparationAction } from "@/components/features/medwatch-preparation-action";
import { formatReviewTimestamp } from "@/components/features/review-time";
import { CausalityPill } from "@/components/features/work-list";
import type {
    ADRClinicianAnswerInput,
    ADRReviewDecisionInput,
    ADRReviewEvidence,
    ADRReviewQueueItem,
} from "@/services/clinicians";

const STATUS_VARIANT: Record<QueueTab, "warning" | "info" | "success" | "neutral"> = {
    awaiting: "warning",
    information: "info",
    reviewed: "success",
    dismissed: "neutral",
};

type EvidenceProvenance = "ai" | "patient" | "clinician" | "other";

/** Where an evidence entry came from, based only on what the stored entry records. */
function provenance(entry: ADRReviewEvidence): EvidenceProvenance {
    if (entry.source === "patient_follow_up") return "patient";
    if (entry.source === "clinician_entry") return "clinician";
    if (entry.source === undefined || entry.source === null) return "ai";
    return "other";
}

function ProvenanceLabel({
    entry,
    item,
}: {
    entry: ADRReviewEvidence;
    item: ADRReviewQueueItem;
}) {
    const kind = provenance(entry);
    if (kind === "ai") return <AiChip>AI-extracted</AiChip>;
    if (kind === "other") return <Badge variant="neutral">Other source</Badge>;
    if (kind === "clinician") {
        return (
            <>
                <Badge variant="info">Clinician-entered</Badge>
                {entry.recorded_at ? (
                    <span className="text-xs text-muted">
                        Recorded{" "}
                        <time className="font-mono" dateTime={entry.recorded_at}>
                            {formatReviewTimestamp(entry.recorded_at)}
                        </time>
                    </span>
                ) : null}
            </>
        );
    }

    // Only date the answer when it belongs to the request the response time describes.
    const answeredAt =
        entry.information_request_id &&
        entry.information_request_id === item.informationRequestId &&
        item.patientRespondedAt
            ? item.patientRespondedAt
            : null;

    return (
        <>
            <Badge variant="neutral">Patient-confirmed</Badge>
            <span className="text-xs text-muted">
                {!entry.information_request_id
                    ? "Follow-up request not recorded"
                    : !item.informationRequestId
                      ? "Recorded follow-up"
                      : entry.information_request_id === item.informationRequestId
                        ? "Current follow-up"
                        : "Different follow-up"}
            </span>
            {answeredAt ? (
                <span className="text-xs text-muted">
                    Answered{" "}
                    <time className="font-mono" dateTime={answeredAt}>
                        {formatReviewTimestamp(answeredAt)}
                    </time>
                </span>
            ) : null}
        </>
    );
}

const cardClass = "rounded-xl border border-line bg-surface p-5";
const headingClass = "text-sm font-semibold text-ink";

function EvidenceList({ item, glosses }: { item: ADRReviewQueueItem; glosses: GlossMap }) {
    if (item.evidence.length === 0) {
        return (
            <p className="rounded-xl border border-dashed border-line-strong bg-surface-2 px-4 py-3 text-sm text-muted">
                No Naranjo evidence has been recorded yet.
            </p>
        );
    }

    return (
        <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
            {item.evidence.map((entry, index) => (
                <li
                    className="space-y-2.5 px-4 py-3.5"
                    key={`${index}:${entry.question}:${entry.source ?? "ai"}`}
                >
                    <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1.5">
                        <p className="min-w-0 text-sm font-medium text-ink">
                            {questionLabel(entry.question)}
                        </p>
                        <Badge
                            className="capitalize"
                            variant={entry.answer === "yes" ? "success" : "neutral"}
                        >
                            {entry.answer.replaceAll("_", " ")}
                        </Badge>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <ProvenanceLabel entry={entry} item={item} />
                    </div>
                    {/* LOC-003 item 2: a patient's answer is evidence, so it is quoted as
                        given; the English gloss sits beneath it, never in its place. */}
                    {entry.evidence ? (
                        <blockquote className="max-w-[72ch] border-l-2 border-line-strong pl-3 text-sm leading-relaxed text-ink-2">
                            <span className="block">“{entry.evidence}”</span>
                            <EvidenceGlossLine gloss={glossFor(glosses, entry.evidence)} />
                        </blockquote>
                    ) : null}
                </li>
            ))}
        </ul>
    );
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
    return (
        <div className="min-w-0">
            <dt className="text-xs text-muted">{label}</dt>
            <dd className="mt-0.5 break-words text-sm font-medium text-ink">{children}</dd>
        </div>
    );
}

export function ADRReviewCard({
    item,
    onReview,
    onPrepareDraft,
    onRecordAnswers,
    submitting,
    medwatchDraftId = null,
    backHref = "/adr-reviews",
}: {
    item: ADRReviewQueueItem;
    onReview: (assessmentId: string, input: ADRReviewDecisionInput) => Promise<void>;
    onPrepareDraft: (assessmentId: string, rationale: string, careTeamId?: string) => Promise<void>;
    /** PV-001-D: record clinician Naranjo answers while the case is open. */
    onRecordAnswers?: (
        assessmentId: string,
        answers: ADRClinicianAnswerInput[],
        careTeamId?: string,
    ) => Promise<void>;
    submitting: boolean;
    /** The active MedWatch report for this case, when one exists. */
    medwatchDraftId?: string | null;
    backHref?: string;
}) {
    const missingQuestions = item.naranjoAssessment.missing_questions ?? [];
    const scoringItems = item.naranjoAssessment.items ?? [];
    const patientName = `${item.patientFirstName} ${item.patientLastName}`.trim();
    const tab = queueTabOf(item);
    const open = item.status === "draft";
    /* LOC-003 item 2: one gloss request covers every Spanish answer quoted on this card. */
    const glosses = useEvidenceGlosses(item.patientId, [
        ...item.evidence.map((entry) => entry.evidence),
        ...item.patientResponses.map((response) => response.evidence),
    ]);
    const careTeam = useCareTeamChoice(item.patientId, open);

    return (
        <article className="ma-enter space-y-6">
            <div className="space-y-3">
                <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-sm">
                    <Link className="rounded-md text-muted hover:text-ink" href={backHref}>
                        ADR Reviews
                    </Link>
                    <Icon aria-hidden="true" className="h-3.5 w-3.5 text-[#94A3B8]" name="chevron" />
                    <span aria-current="page" className="font-medium text-ink">
                        {patientName}
                    </span>
                </nav>
                <header className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                        <h1 className="text-[26px] font-semibold leading-tight tracking-[-0.02em] text-ink">
                            {patientName}
                        </h1>
                        <p className="mt-1 text-[15px] text-ink-2">
                            {item.symptom} <span aria-hidden="true">·</span> {item.suspectMedicationName}
                        </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <Badge variant={STATUS_VARIANT[tab]}>{STATUS_LABELS[tab]}</Badge>
                        <CausalityPill band={item.causality} score={item.naranjoScore} />
                    </div>
                </header>
            </div>

            <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
                <div className="min-w-0 space-y-6">
                    <section aria-labelledby="adr-summary" className={cardClass}>
                        <h2 className={headingClass} id="adr-summary">
                            Summary
                        </h2>
                        <dl className="mt-4 grid gap-x-6 gap-y-4 sm:grid-cols-2">
                            <Fact label="Reported symptom">{item.symptom}</Fact>
                            <Fact label="Severity">
                                <span className="font-mono">
                                    {item.severity === null ? "Unknown / not provided" : `${item.severity}/10`}
                                </span>
                            </Fact>
                            <Fact label="Suspect medication">{item.suspectMedicationName}</Fact>
                            <Fact label="Onset">{item.onset || "Not recorded"}</Fact>
                            <Fact label="Captured">
                                <time dateTime={item.createdAt}>{formatReviewTimestamp(item.createdAt)}</time>
                            </Fact>
                            <Fact label="Association">Patient-reported; not a clinician decision</Fact>
                        </dl>
                    </section>

                    <section>
                        <h2 className="mb-3 text-sm font-semibold text-ink">
                            Naranjo evidence
                        </h2>
                        <EvidenceList glosses={glosses} item={item} />
                    </section>

                    {scoringItems.length > 0 ? (
                        <details className="ma-disclosure rounded-xl border border-line bg-surface">
                            <summary className="min-h-10 px-4 py-2 text-[13px] font-semibold text-ink">
                                Show scoring details
                            </summary>
                            <ul className="divide-y divide-line border-t border-line">
                                {scoringItems.map((scored) => (
                                    <li
                                        className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm"
                                        key={scored.question}
                                    >
                                        <span className="min-w-0 text-ink-2">
                                            {questionLabel(scored.question)}:{" "}
                                            <span className="capitalize">{scored.answer.replaceAll("_", " ")}</span>
                                        </span>
                                        <span className="shrink-0 font-mono text-ink">
                                            {scored.points > 0 ? `+${scored.points}` : scored.points}
                                        </span>
                                    </li>
                                ))}
                            </ul>
                        </details>
                    ) : null}

                    {missingQuestions.length > 0 ? (
                        <section className={cardClass}>
                            <h2 className={headingClass}>Missing information</h2>
                            <ul className="mt-3 space-y-2">
                                {missingQuestions.map((question) => (
                                    <li className="flex items-start gap-2.5 text-sm text-ink-2" key={question}>
                                        <span
                                            aria-hidden="true"
                                            className="mt-0.5 h-4 w-4 shrink-0 rounded border border-line-strong"
                                        />
                                        {questionLabel(question)}
                                    </li>
                                ))}
                            </ul>
                        </section>
                    ) : null}

                    {open && onRecordAnswers ? (
                        <ADRClinicianAnswers
                            answers={item.naranjoAnswers}
                            disabled={submitting || careTeam.missing}
                            onRecord={(answers) =>
                                careTeam.careTeamId
                                    ? onRecordAnswers(item.id, answers, careTeam.careTeamId)
                                    : onRecordAnswers(item.id, answers)
                            }
                        />
                    ) : null}

                    {item.lastReviewAction === "request_information" ? (
                        <section
                            className={`flex items-start gap-2.5 rounded-xl border px-4 py-3 ${
                                item.informationRequestStatus === "answered"
                                    ? "border-ok-line bg-ok-soft"
                                    : "border-primary-line bg-primary-tint"
                            }`}
                        >
                            <Icon
                                className={`mt-0.5 h-4 w-4 shrink-0 ${
                                    item.informationRequestStatus === "answered"
                                        ? "text-ok-ink"
                                        : "text-primary"
                                }`}
                                name="info"
                            />
                            <div className="min-w-0">
                                <h2 className="text-sm font-semibold text-ink">
                                    {item.informationRequestStatus === "answered"
                                        ? "Patient answered"
                                        : "Information requested"}
                                </h2>
                                {item.reviewNote ? (
                                    <p className="mt-1 text-sm text-ink-2">{item.reviewNote}</p>
                                ) : null}
                                {item.informationRequestStatus === "answered" ? (
                                    <div className="mt-3 space-y-2">
                                        {item.patientResponses.map((response) => (
                                            <div
                                                className="rounded-lg border border-ok-line bg-surface p-3"
                                                key={response.question}
                                            >
                                                <p className="text-sm font-medium text-ink">
                                                    {questionLabel(response.question)}:{" "}
                                                    {response.answer.replaceAll("_", " ")}
                                                </p>
                                                {response.evidence ? (
                                                    <p className="mt-1 text-sm text-ink-2">
                                                        <span className="block">“{response.evidence}”</span>
                                                        <EvidenceGlossLine gloss={glossFor(glosses, response.evidence)} />
                                                    </p>
                                                ) : null}
                                            </div>
                                        ))}
                                        <p className="text-xs text-ok-ink">
                                            The deterministic score above includes these confirmed
                                            answers. Clinician judgment is still required.
                                        </p>
                                    </div>
                                ) : null}
                            </div>
                        </section>
                    ) : null}
                </div>

                {/* Actions stay in view beside the evidence on wide screens and stack below it on narrow ones. */}
                <aside className="min-w-0 space-y-4 self-start lg:sticky lg:top-6">
                    <section className="rounded-xl border border-line bg-surface-2 p-4">
                        <p className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">
                            Naranjo score
                        </p>
                        <div className="mt-1.5 flex flex-wrap items-center gap-3">
                            <span className="font-mono text-3xl font-medium leading-none text-ink">
                                {item.naranjoScore}
                            </span>
                            <Badge variant="warning">{item.causality}</Badge>
                        </div>
                        <p className="mt-3 border-t border-line pt-3 text-xs leading-relaxed text-muted">
                            Naranjo scores support your review; they do not make a clinical decision.
                        </p>
                    </section>

                    <section aria-label="Case actions" className={`${cardClass} space-y-3`}>
                        {open ? (
                            <>
                                <CareTeamSelect onChange={careTeam.setValue} options={careTeam.options} required={careTeam.required} value={careTeam.value} />
                                <ADRReviewActions
                                    item={item}
                                    onSubmit={(input) => onReview(item.id, careTeam.careTeamId ? { ...input, careTeamId: careTeam.careTeamId } : input)}
                                    submitting={submitting || careTeam.missing}
                                />
                                <div className="border-t border-line pt-3">
                                    <MedWatchPreparationAction
                                        disabled={submitting || careTeam.missing}
                                        onPrepare={(rationale) => careTeam.careTeamId ? onPrepareDraft(item.id, rationale, careTeam.careTeamId) : onPrepareDraft(item.id, rationale)}
                                    />
                                </div>
                            </>
                        ) : (
                            <div className="space-y-3">
                                <p className="text-sm text-ink-2">
                                    {item.status === "dismissed"
                                        ? "This assessment was dismissed."
                                        : "This assessment has been reviewed."}
                                    {item.reviewedAt ? (
                                        <>
                                            {" "}
                                            <time className="font-mono text-xs text-muted" dateTime={item.reviewedAt}>
                                                {formatReviewTimestamp(item.reviewedAt)}
                                            </time>
                                        </>
                                    ) : null}
                                </p>
                                {item.status !== "draft" && item.reviewNote && item.lastReviewAction !== "request_information" ? (
                                    <p className="text-sm text-ink-2">Note: {item.reviewNote}</p>
                                ) : null}
                                {medwatchDraftId ? (
                                    <Link
                                        className="ma-press inline-flex min-h-[34px] w-full items-center justify-center gap-2 rounded-[9px] bg-primary px-4 py-1.5 text-[13px] font-semibold text-white hover:bg-primary-hover"
                                        href={`/medwatch/${medwatchDraftId}`}
                                    >
                                        Open MedWatch report →
                                    </Link>
                                ) : null}
                            </div>
                        )}
                    </section>
                </aside>
            </div>

            <footer className="flex flex-col justify-between gap-3 border-t border-line pt-4 md:flex-row md:items-center">
                <p className="max-w-[80ch] text-xs leading-relaxed text-muted">
                    Decision support only. Review the source evidence before making a clinical
                    determination or generating a MedWatch draft.
                </p>
                <Link
                    className="inline-flex shrink-0 items-center gap-1.5 rounded-md text-[13px] font-semibold text-primary hover:text-primary-hover"
                    href={`/patients/${item.patientId}`}
                >
                    Open patient record
                    <Icon className="h-4 w-4" name="external" />
                </Link>
            </footer>
        </article>
    );
}
