import Link from "next/link";
import { Badge } from "@/components/ui";
import { AiChip } from "@/components/ui/ai-chip";
import { Icon } from "@/components/ui/icons";
import { ADRReviewActions } from "@/components/features/adr-review-actions";
import { MedWatchPreparationAction } from "@/components/features/medwatch-preparation-action";
import { formatReviewTimestamp } from "@/components/features/review-time";
import type {
    ADRReviewDecisionInput,
    ADRReviewEvidence,
    ADRReviewQueueItem,
} from "@/services/clinicians";

const QUESTION_LABELS: Record<string, string> = {
    alternative_causes: "Alternative causes",
    dose_response: "Dose-response relationship",
    event_after_drug: "Event followed medication",
    improved_on_dechallenge: "Improved after stopping",
    objective_evidence: "Objective evidence",
    previous_reports: "Previous conclusive reports",
    reappeared_on_rechallenge: "Reappeared after restarting",
    reappeared_with_placebo: "Reappeared with placebo",
    similar_previous_reaction: "Similar previous reaction",
    toxic_drug_concentration: "Toxic drug concentration",
};

function questionLabel(question: string) {
    return QUESTION_LABELS[question] ?? question.replaceAll("_", " ");
}

type EvidenceProvenance = "ai" | "patient" | "other";

/** Where an evidence entry came from, based only on what the stored entry records. */
function provenance(entry: ADRReviewEvidence): EvidenceProvenance {
    if (entry.source === "patient_follow_up") return "patient";
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

const panelClass = "rounded-xl border border-line bg-surface p-4";
const panelHeadingClass = "flex items-center gap-2 text-[13px] font-semibold text-ink";

function EvidenceList({ item }: { item: ADRReviewQueueItem }) {
    if (item.evidence.length === 0) {
        return (
            <p className="rounded-xl border border-dashed border-line-strong bg-surface-2 px-4 py-3 text-sm text-muted">
                No patient-grounded evidence was captured.
            </p>
        );
    }

    return (
        <ul className="divide-y divide-line rounded-xl border border-line">
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
                    {entry.evidence ? (
                        <blockquote className="max-w-[72ch] border-l-2 border-line-strong pl-3 text-sm leading-relaxed text-ink-2">
                            “{entry.evidence}”
                        </blockquote>
                    ) : null}
                </li>
            ))}
        </ul>
    );
}

export function ADRReviewCard({
    item,
    onReview,
    onPrepareDraft,
    submitting,
}: {
    item: ADRReviewQueueItem;
    onReview: (assessmentId: string, input: ADRReviewDecisionInput) => Promise<void>;
    onPrepareDraft: (assessmentId: string, rationale: string) => Promise<void>;
    submitting: boolean;
}) {
    const missingQuestions = item.naranjoAssessment.missing_questions ?? [];
    const patientName = `${item.patientFirstName} ${item.patientLastName}`.trim();

    return (
        <article className="ma-enter rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]">
            <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-6 py-4">
                <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-lg font-semibold tracking-[-0.01em] text-ink">
                            {patientName}
                        </h2>
                        <Badge variant="warning">Awaiting review</Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted">
                        Captured <span className="font-mono">{formatReviewTimestamp(item.createdAt)}</span>
                    </p>
                </div>
                <Badge className="font-mono" variant="neutral">
                    Naranjo {item.naranjoScore}
                </Badge>
            </header>

            <div className="grid gap-6 p-6 xl:grid-cols-[minmax(0,1fr)_360px]">
                {/* Left: what the patient reported and the evidence behind each answer */}
                <div className="min-w-0 space-y-6">
                    <section>
                        <div className={panelHeadingClass}>
                            <Icon className="h-4 w-4 text-primary" name="note" />
                            <h3 className="text-sm font-semibold">Reported symptom</h3>
                        </div>
                        <p className="mt-2.5 text-[15px] font-semibold text-ink">{item.symptom}</p>
                        <p className="mt-1 text-xs text-muted">
                            Severity <span className="font-mono">{item.severity === null ? "Unknown / not provided" : `${item.severity}/10`}</span>
                        </p>
                        {item.onset ? (
                            <p className="mt-2 max-w-[72ch] text-sm text-ink-2">Onset: {item.onset}</p>
                        ) : null}
                    </section>

                    <section>
                        <h3 className="mb-3 text-sm font-semibold text-ink">
                            Patient-grounded Naranjo evidence
                        </h3>
                        <EvidenceList item={item} />
                    </section>
                </div>

                {/* Right: the score and the review controls, kept in view on wide screens */}
                <aside className="min-w-0 space-y-4 self-start xl:sticky xl:top-0">
                    <section className={panelClass}>
                        <div className={panelHeadingClass}>
                            <Icon className="h-4 w-4 text-primary" name="pill" />
                            <h3 className="text-sm font-semibold">Suspect medication</h3>
                        </div>
                        <p className="mt-2.5 text-sm font-medium text-ink">
                            {item.suspectMedicationName}
                        </p>
                        <p className="mt-1 text-xs text-muted">
                            Patient-reported association; not a clinician decision
                        </p>
                    </section>

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

                    {missingQuestions.length > 0 ? (
                        <section>
                            <h3 className="text-[13px] font-semibold text-ink">Missing information</h3>
                            <div className="mt-2 flex flex-wrap gap-2">
                                {missingQuestions.map((question) => (
                                    <Badge key={question} variant="neutral">
                                        {questionLabel(question)}
                                    </Badge>
                                ))}
                            </div>
                        </section>
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
                                <h3 className="text-sm font-semibold text-ink">
                                    {item.informationRequestStatus === "answered"
                                        ? "Patient answered"
                                        : "Information requested"}
                                </h3>
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
                                                        “{response.evidence}”
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

                    <ADRReviewActions
                        item={item}
                        onSubmit={(input) => onReview(item.id, input)}
                        submitting={submitting}
                    />
                    <MedWatchPreparationAction
                        disabled={submitting}
                        onPrepare={(rationale) => onPrepareDraft(item.id, rationale)}
                    />
                </aside>
            </div>

            <footer className="flex flex-col justify-between gap-3 border-t border-line px-6 py-4 md:flex-row md:items-center">
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
