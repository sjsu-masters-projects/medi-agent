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

export function ADRReviewActions({
    item,
    onSubmit,
    submitting,
}: {
    item: ADRReviewQueueItem;
    onSubmit: (input: ADRReviewDecisionInput) => Promise<void>;
    submitting: boolean;
}) {
    const missingQuestions = item.naranjoAssessment.missing_questions ?? [];
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
            <div
                className="flex flex-wrap gap-2"
                aria-label="ADR review actions"
            >
                <Button
                    disabled={submitting}
                    onClick={() => begin("request_information")}
                    size="sm"
                    variant="secondary"
                >
                    Request information
                </Button>
                <Button
                    disabled={submitting}
                    onClick={() => begin("dismiss")}
                    size="sm"
                    variant="danger"
                >
                    Dismiss
                </Button>
                <Button
                    disabled={submitting}
                    onClick={() => begin("mark_reviewed")}
                    size="sm"
                >
                    Mark reviewed
                </Button>
            </div>
        );
    }

    const noteRequired = action !== "mark_reviewed";
    return (
        <form
            className="space-y-3 rounded-lg border border-blue-200 bg-blue-50 p-4"
            onSubmit={submit}
        >
            <h3 className="text-sm font-semibold text-gray-900">
                {ACTION_LABELS[action]}
            </h3>
            {action === "request_information" && missingQuestions.length > 0 ? (
                <fieldset>
                    <legend className="text-xs font-medium text-gray-700">
                        Information needed
                    </legend>
                    <div className="mt-2 flex flex-wrap gap-3">
                        {missingQuestions.map((question) => (
                            <label
                                className="flex items-center gap-2 text-sm text-gray-700"
                                key={question}
                            >
                                <input
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
            <label className="block text-sm font-medium text-gray-700">
                Review note{noteRequired ? " (required)" : " (optional)"}
                <textarea
                    disabled={submitting}
                    maxLength={MAX_NOTE_LENGTH}
                    className="mt-1 min-h-24 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500"
                    onChange={(event) => setNote(event.target.value)}
                    placeholder={
                        action === "request_information"
                            ? "Describe what the patient or care team should clarify."
                            : "Record the clinical basis for this action."
                    }
                    value={note}
                />
            </label>
            <div className="flex gap-2">
                <Button
                    disabled={
                        submitting ||
                        note.length > MAX_NOTE_LENGTH ||
                        (noteRequired && !note.trim())
                    }
                    size="sm"
                    type="submit"
                >
                    {ACTION_LABELS[action]}
                </Button>
                <Button
                    disabled={submitting}
                    onClick={() => setAction(null)}
                    size="sm"
                    variant="ghost"
                >
                    Cancel
                </Button>
            </div>
        </form>
    );
}
