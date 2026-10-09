"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { HiOutlineClipboardDocumentCheck } from "react-icons/hi2";
import { useSelector } from "react-redux";
import { Button, Card } from "@/components/ui";
import {
    fetchADRInformationRequests,
    respondToADRInformationRequest,
    type ADRInformationAnswerInput,
    type ADRInformationRequest,
    type PatientADRAnswer,
    type PatientADRQuestion,
} from "@/services/adr-follow-up";
import type { RootState } from "@/store/store";

const QUESTION_COPY: Record<
    PatientADRQuestion,
    { label: string; prompt: string; evidencePrompt: string }
> = {
    reappeared_on_rechallenge: {
        label: "What happened after a past restart",
        prompt:
            "Before this request, did the same symptom return after you had already restarted this medicine? Do not restart it to answer.",
        evidencePrompt: "Describe what happened and when.",
    },
    dose_response: {
        label: "What happened after a past dose change",
        prompt:
            "Before this request, did the symptom change after a clinician-directed dose change? Do not change your dose to answer.",
        evidencePrompt: "Describe the dose change and what happened.",
    },
    similar_previous_reaction: {
        label: "A similar past reaction",
        prompt: "Have you had the same symptom with this medicine before?",
        evidencePrompt: "Describe the earlier reaction and when it happened.",
    },
};

const ANSWER_LABELS: Record<PatientADRAnswer, string> = {
    yes: "Yes",
    no: "No",
    do_not_know: "I’m not sure",
};

interface DraftAnswer {
    answer?: PatientADRAnswer;
    evidence: string;
}

function RequestCard({
    request,
    onAnswered,
}: {
    request: ADRInformationRequest;
    onAnswered: (requestId: string) => void;
}) {
    const accessToken = useSelector((state: RootState) => state.auth.accessToken);
    const [answers, setAnswers] = useState<Record<string, DraftAnswer>>({});
    const [reviewing, setReviewing] = useState(false);
    const [confirmed, setConfirmed] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const answerInputs = useMemo<ADRInformationAnswerInput[]>(
        () =>
            request.requestedInformation.flatMap((question) => {
                const draft = answers[question];
                if (!draft?.answer) return [];
                return [
                    {
                        question,
                        answer: draft.answer,
                        evidence:
                            draft.answer === "do_not_know"
                                ? undefined
                                : draft.evidence.trim() || undefined,
                    },
                ];
            }),
        [answers, request.requestedInformation],
    );

    const complete = request.requestedInformation.every((question) => {
        const draft = answers[question];
        return Boolean(
            draft?.answer
                && (draft.answer === "do_not_know" || draft.evidence.trim()),
        );
    });

    function setAnswer(question: PatientADRQuestion, answer: PatientADRAnswer) {
        setAnswers((current) => ({
            ...current,
            [question]: {
                answer,
                evidence: current[question]?.evidence ?? "",
            },
        }));
    }

    function setEvidence(question: PatientADRQuestion, evidence: string) {
        setAnswers((current) => ({
            ...current,
            [question]: {
                answer: current[question]?.answer,
                evidence,
            },
        }));
    }

    async function submit() {
        if (!accessToken || !confirmed || !complete) return;
        setSubmitting(true);
        setError(null);
        try {
            await respondToADRInformationRequest(accessToken, request.id, answerInputs);
            onAnswered(request.id);
        } catch (submissionError) {
            setError(
                submissionError instanceof Error
                    ? submissionError.message
                    : "We couldn’t save these answers. Nothing was sent.",
            );
        } finally {
            setSubmitting(false);
        }
    }

    return (
        <Card className="space-y-4 border-[#b6d9d2] bg-[#e6f4f1]" as="section">
            <div className="flex items-start gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-white text-[#147465]">
                    <HiOutlineClipboardDocumentCheck className="h-5 w-5" />
                </div>
                <div>
                    <p className="text-[11px] font-black uppercase tracking-[0.2em] text-[#147465]">
                        Care team follow-up
                    </p>
                    <h2 className="mt-1 text-lg font-black text-[#17233a]">
                        A few questions about {request.symptom}
                    </h2>
                    <p className="mt-1 text-sm leading-6 text-[#48627c]">
                        Reported with {request.suspectMedicationName}. {request.patientMessage}
                    </p>
                </div>
            </div>

            <div className="rounded-2xl border border-[#F0D7AA] bg-[#FFF7E8] px-4 py-3 text-sm leading-6 text-[#7A4C00]">
                Answer only from what has already happened. Do not restart, stop, or change a
                medicine just to answer these questions.
            </div>

            {!reviewing ? (
                <div className="space-y-5">
                    {request.requestedInformation.map((question) => {
                        const copy = QUESTION_COPY[question];
                        const draft = answers[question] ?? { evidence: "" };
                        return (
                            <fieldset className="space-y-3" key={question}>
                                <legend className="text-sm font-bold text-[#17233a]">
                                    {copy.prompt}
                                </legend>
                                <div className="grid grid-cols-3 gap-2">
                                    {(Object.keys(ANSWER_LABELS) as PatientADRAnswer[]).map(
                                        (answer) => (
                                            <label
                                                className={`flex min-h-12 cursor-pointer items-center justify-center rounded-2xl border px-2 text-center text-sm font-bold transition ${
                                                    draft.answer === answer
                                                        ? "border-[#147465] bg-[#147465] text-white"
                                                        : "border-[#d9cbc0] bg-white text-[#30415f]"
                                                }`}
                                                key={answer}
                                            >
                                                <input
                                                    checked={draft.answer === answer}
                                                    className="sr-only"
                                                    name={`${request.id}-${question}`}
                                                    onChange={() => setAnswer(question, answer)}
                                                    type="radio"
                                                    value={answer}
                                                />
                                                {ANSWER_LABELS[answer]}
                                            </label>
                                        ),
                                    )}
                                </div>
                                {draft.answer && draft.answer !== "do_not_know" ? (
                                    <label className="block text-sm font-bold text-[#30415f]">
                                        {copy.evidencePrompt}
                                        <textarea
                                            className="mt-2 min-h-24 w-full rounded-2xl border border-[#d9cbc0] bg-white px-4 py-3 text-base leading-6 text-[#17233a] outline-none focus:border-[#147465] focus:ring-4 focus:ring-[#147465]/15"
                                            maxLength={500}
                                            onChange={(event) =>
                                                setEvidence(question, event.target.value)
                                            }
                                            value={draft.evidence}
                                        />
                                    </label>
                                ) : null}
                            </fieldset>
                        );
                    })}
                    <Button
                        disabled={!complete}
                        fullWidth
                        onClick={() => setReviewing(true)}
                    >
                        Review answers
                    </Button>
                </div>
            ) : (
                <div className="space-y-4">
                    <div className="space-y-3 rounded-2xl bg-white p-4">
                        <h3 className="text-base font-black text-[#17233a]">Review before sending</h3>
                        {answerInputs.map((item) => (
                            <div className="border-t border-[#eadfd4] pt-3 first:border-0 first:pt-0" key={item.question}>
                                <p className="text-sm font-bold text-[#30415f]">
                                    {QUESTION_COPY[item.question].label}: {ANSWER_LABELS[item.answer]}
                                </p>
                                {item.evidence ? (
                                    <p className="mt-1 text-sm leading-6 text-[#5b6b83]">
                                        {item.evidence}
                                    </p>
                                ) : null}
                            </div>
                        ))}
                    </div>
                    <label className="flex items-start gap-3 text-sm leading-6 text-[#30415f]">
                        <input
                            checked={confirmed}
                            className="mt-1 h-4 w-4"
                            onChange={(event) => setConfirmed(event.target.checked)}
                            type="checkbox"
                        />
                        I confirm these answers describe what already happened. I was not asked
                        to change or restart a medicine.
                    </label>
                    {error ? (
                        <p className="rounded-2xl border border-[#efbeb5] bg-[#fff2ef] px-4 py-3 text-sm font-semibold text-[#b94032]" role="alert">
                            {error}
                        </p>
                    ) : null}
                    <div className="flex gap-2">
                        <Button
                            disabled={!confirmed || submitting}
                            fullWidth
                            onClick={() => void submit()}
                        >
                            {submitting ? "Sending…" : "Send to care team"}
                        </Button>
                        <Button
                            disabled={submitting}
                            onClick={() => setReviewing(false)}
                            variant="secondary"
                        >
                            Edit
                        </Button>
                    </div>
                </div>
            )}
        </Card>
    );
}

export function ADRFollowUpPanel() {
    const accessToken = useSelector((state: RootState) => state.auth.accessToken);
    const [requests, setRequests] = useState<ADRInformationRequest[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [notice, setNotice] = useState<string | null>(null);

    const load = useCallback(async () => {
        if (!accessToken) return;
        setLoading(true);
        setError(null);
        try {
            setRequests(await fetchADRInformationRequests(accessToken));
        } catch (loadError) {
            setError(
                loadError instanceof Error
                    ? loadError.message
                    : "We couldn’t load care-team follow-up questions.",
            );
        } finally {
            setLoading(false);
        }
    }, [accessToken]);

    useEffect(() => {
        void load();
    }, [load]);

    if (!accessToken || (!loading && !error && requests.length === 0 && !notice)) {
        return null;
    }

    return (
        <div className="space-y-3" aria-label="Care team ADR follow-up">
            {loading && requests.length === 0 ? (
                <Card className="text-sm font-semibold text-[#64748b]">
                    Checking for care-team follow-up…
                </Card>
            ) : null}
            {error ? (
                <Card className="space-y-3 border-[#efbeb5] bg-[#fff2ef]">
                    <p className="text-sm font-semibold text-[#b94032]" role="alert">{error}</p>
                    <Button onClick={() => void load()} size="sm" variant="secondary">
                        Try again
                    </Button>
                </Card>
            ) : null}
            {notice ? (
                <Card className="border-[#b6d9d2] bg-[#e6f4f1] text-sm font-bold text-[#147465]" as="section">
                    {notice}
                </Card>
            ) : null}
            {requests.map((request) => (
                <RequestCard
                    key={request.id}
                    onAnswered={(requestId) => {
                        setRequests((current) =>
                            current.filter((item) => item.id !== requestId),
                        );
                        setNotice("Your answers were sent to your care team.");
                    }}
                    request={request}
                />
            ))}
        </div>
    );
}
