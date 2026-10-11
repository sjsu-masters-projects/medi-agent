import Link from "next/link";
import {
    HiOutlineArrowTopRightOnSquare,
    HiOutlineBeaker,
    HiOutlineClipboardDocumentCheck,
} from "react-icons/hi2";
import { Badge, Card } from "@/components/ui";
import { ADRReviewActions } from "@/components/features/adr-review-actions";
import type { ADRReviewDecisionInput, ADRReviewQueueItem } from "@/services/clinicians";

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

function formatTimestamp(value: string) {
    return new Intl.DateTimeFormat("en-US", {
        dateStyle: "medium",
        timeStyle: "short",
    }).format(new Date(value));
}

function EvidenceList({ item }: { item: ADRReviewQueueItem }) {
    if (item.evidence.length === 0) {
        return <p className="text-sm text-muted">No patient-grounded evidence was captured.</p>;
    }

    return (
        <ul className="space-y-3">
            {item.evidence.map((entry) => (
                <li
                    className="rounded-lg border border-line bg-surface-2 p-3"
                    key={entry.question}
                >
                    <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-medium text-ink">
                            {questionLabel(entry.question)}
                        </p>
                        <Badge variant={entry.answer === "yes" ? "success" : "neutral"}>
                            {entry.answer.replaceAll("_", " ")}
                        </Badge>
                    </div>
                    {entry.evidence ? (
                        <blockquote className="mt-2 border-l-2 border-primary-line pl-3 text-sm text-ink-2">
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
    submitting,
}: {
    item: ADRReviewQueueItem;
    onReview: (assessmentId: string, input: ADRReviewDecisionInput) => Promise<void>;
    submitting: boolean;
}) {
    const missingQuestions = item.naranjoAssessment.missing_questions ?? [];
    const patientName = `${item.patientFirstName} ${item.patientLastName}`.trim();

    return (
        <Card className="space-y-5" padding="lg">
            <div className="flex flex-col justify-between gap-3 md:flex-row md:items-start">
                <div>
                    <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-lg font-semibold text-ink">{patientName}</h2>
                        <Badge variant="warning">Awaiting review</Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted">
                        Captured {formatTimestamp(item.createdAt)}
                    </p>
                </div>
                <div className="flex flex-wrap gap-2">
                    <Badge variant="info">Naranjo {item.naranjoScore}</Badge>
                    <Badge variant="warning">{item.causality}</Badge>
                </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
                <section className="rounded-lg border border-line p-4">
                    <div className="flex items-center gap-2 text-ink">
                        <HiOutlineClipboardDocumentCheck className="h-5 w-5 text-primary" />
                        <h3 className="text-sm font-semibold">Reported symptom</h3>
                    </div>
                    <p className="mt-3 text-sm font-medium text-ink">{item.symptom}</p>
                    <p className="mt-1 text-xs text-muted">Severity {item.severity}/10</p>
                    {item.onset ? (
                        <p className="mt-2 text-sm text-ink-2">Onset: {item.onset}</p>
                    ) : null}
                </section>
                <section className="rounded-lg border border-line p-4">
                    <div className="flex items-center gap-2 text-ink">
                        <HiOutlineBeaker className="h-5 w-5 text-primary" />
                        <h3 className="text-sm font-semibold">Suspect medication</h3>
                    </div>
                    <p className="mt-3 text-sm font-medium text-ink">
                        {item.suspectMedicationName}
                    </p>
                    <p className="mt-1 text-xs text-muted">
                        Patient-reported association; not a clinician decision
                    </p>
                </section>
            </div>

            <section>
                <h3 className="mb-3 text-sm font-semibold text-ink">
                    Patient-grounded Naranjo evidence
                </h3>
                <EvidenceList item={item} />
            </section>

            {missingQuestions.length > 0 ? (
                <section>
                    <h3 className="text-sm font-semibold text-ink">Missing information</h3>
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
                <section className="rounded-lg border border-primary-line bg-primary-tint p-4">
                    <h3 className="text-sm font-semibold text-ai-ink">Information requested</h3>
                    {item.reviewNote ? (
                        <p className="mt-1 text-sm text-ai-ink">{item.reviewNote}</p>
                    ) : null}
                </section>
            ) : null}

            <ADRReviewActions
                item={item}
                onSubmit={(input) => onReview(item.id, input)}
                submitting={submitting}
            />

            <div className="flex flex-col justify-between gap-3 border-t border-line pt-4 md:flex-row md:items-center">
                <p className="max-w-3xl text-xs text-muted">
                    Decision support only. Review the source evidence before making a clinical
                    determination or generating a MedWatch draft.
                </p>
                <Link
                    className="inline-flex items-center gap-2 text-sm font-medium text-primary hover:text-primary"
                    href={`/patients/${item.patientId}`}
                >
                    Open patient record
                    <HiOutlineArrowTopRightOnSquare className="h-4 w-4" />
                </Link>
            </div>
        </Card>
    );
}
