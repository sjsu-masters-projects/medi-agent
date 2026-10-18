"use client";

import { useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui";
import type {
    ADRReviewAction,
    ADRReviewDecisionInput,
    ADRReviewQueueItem,
} from "@/services/clinicians";

const ACTION_LABELS: Record<ADRReviewAction, string> = {
    dismiss: "Dismiss assessment",
    mark_reviewed: "Mark reviewed",
    request_information: "Request information",
};
const MAX_NOTE_LENGTH = 2000;

function humanizeQuestion(value: string) {
    return value.replaceAll("_", " ");
}

const PATIENT_ANSWERABLE_QUESTIONS = new Set([
    "reappeared_on_rechallenge",
    "dose_response",
    "similar_previous_reaction",
]);

export function ADRReviewActions({
    item,
    onSubmit,
    submitting,
}: {
    item: ADRReviewQueueItem;
    onSubmit: (input: ADRReviewDecisionInput) => Promise<void>;
    submitting: boolean;
}) {
    const missingQuestions = (item.naranjoAssessment.missing_questions ?? []).filter(
        (question) => PATIENT_ANSWERABLE_QUESTIONS.has(question),
    );
    const [action, setAction] = useState<ADRReviewAction | null>(null);
    const [note, setNote] = useState("");
    const [questions, setQuestions] = useState<string[]>([]);
    const pending = useRef(false);

    function begin(nextAction: ADRReviewAction) {
        setAction(nextAction);
        setNote("");
        setQuestions(
            nextAction === "request_information" ? missingQuestions : [],
        );
    }

    function toggleQuestion(question: string) {
        setQuestions((current) =>
            current.includes(question)
                ? current.filter((candidate) => candidate !== question)
                : [...current, question],
        );
    }

    async function submit(event: FormEvent) {
        event.preventDefault();
        if (
            !action ||
            submitting ||
            pending.current ||
            note.length > MAX_NOTE_LENGTH ||
            (action !== "mark_reviewed" && !note.trim())
        )
            return;
        pending.current = true;
        try {
            await onSubmit({
                action,
                note: note.trim() || undefined,
                requestedInformation:
                    action === "request_information" ? questions : [],
            });
            setAction(null);
            setNote("");
            setQuestions([]);
        } catch {
            // The page displays a safe error; keep the action and draft for retry.
        } finally {
            pending.current = false;
        }
    }

    if (!action) {
        return (
            <div className="flex flex-col gap-2" aria-label="ADR review actions" role="group">
                <Button
                    disabled={submitting}
                    fullWidth
                    onClick={() => begin("mark_reviewed")}
                >
                    Mark reviewed
                </Button>
                {missingQuestions.length > 0 ? (
                    <Button
                        disabled={submitting}
                        fullWidth
                        onClick={() => begin("request_information")}
                        variant="secondary"
                    >
                        Request information
                    </Button>
                ) : null}
                <Button
                    className="text-risk-ink hover:text-risk-ink"
                    disabled={submitting}
                    fullWidth
                    onClick={() => begin("dismiss")}
                    variant="ghost"
                >
                    Dismiss
                </Button>
            </div>
        );
    }

    const noteRequired = action !== "mark_reviewed";
    return (
        <form
            className="ma-enter space-y-4 rounded-xl border border-primary-line bg-primary-tint p-4"
            onSubmit={submit}
        >
            <h3 className="text-sm font-semibold text-ink">
                {ACTION_LABELS[action]}
            </h3>
            {action === "request_information" && missingQuestions.length > 0 ? (
                <fieldset>
                    <legend className="mb-1.5 text-[13px] font-medium text-ink-2">
                        Patient-answerable information needed
                    </legend>
                    <div className="flex flex-wrap gap-2">
                        {missingQuestions.map((question) => (
                            <label
                                className="inline-flex min-h-8 cursor-pointer items-center gap-2 rounded-lg border border-line-strong bg-surface px-2.5 text-[13px] text-ink-2 transition-colors duration-[160ms] hover:border-primary-line has-[:checked]:border-primary-line has-[:checked]:text-ink has-[:disabled]:cursor-not-allowed"
                                key={question}
                            >
                                <input
                                    className="h-4 w-4 accent-[var(--color-primary)]"
                                    disabled={submitting}
                                    checked={questions.includes(question)}
                                    onChange={() => toggleQuestion(question)}
                                    type="checkbox"
                                />
                                {humanizeQuestion(question)}
                            </label>
                        ))}
                    </div>
                </fieldset>
            ) : null}
            <label className="block text-[13px] font-medium text-ink-2">
                Review note{noteRequired ? " (required)" : " (optional)"}
                <textarea
                    disabled={submitting}
                    maxLength={MAX_NOTE_LENGTH}
                    className="mt-1.5 block min-h-24 w-full rounded-[10px] border border-line-strong bg-surface px-3.5 py-2.5 text-sm font-normal text-ink outline-none transition placeholder:text-[#94A3B8] focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)] disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-muted"
                    onChange={(event) => setNote(event.target.value)}
                    placeholder={
                        action === "request_information"
                            ? "Add patient-facing context. Do not instruct a medication change or restart."
                            : "Record the clinical basis for this action."
                    }
                    value={note}
                />
            </label>
            <div className="flex flex-wrap gap-2">
                <Button
                    disabled={
                        submitting ||
                        note.length > MAX_NOTE_LENGTH ||
                        (noteRequired && !note.trim())
                    }
                    type="submit"
                >
                    {ACTION_LABELS[action]}
                </Button>
                <Button
                    disabled={submitting}
                    onClick={() => setAction(null)}
                    variant="ghost"
                >
                    Cancel
                </Button>
            </div>
        </form>
    );
}
