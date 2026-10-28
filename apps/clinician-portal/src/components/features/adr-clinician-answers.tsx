"use client";

import { useRef, useState, type FormEvent } from "react";
import { Badge, Button } from "@/components/ui";
import {
    CLINICIAN_QUESTIONS,
    questionLabel,
    type ClinicianQuestion,
} from "@/components/features/adr-questions";
import type { ADRClinicianAnswerInput, ADRReviewEvidence } from "@/services/clinicians";

type Answer = ADRClinicianAnswerInput["answer"];
type Staged = Partial<Record<ClinicianQuestion, { answer: Answer; basis: string }>>;
type Changing = Partial<Record<ClinicianQuestion, true>>;

const MAX_BASIS_LENGTH = 500;
const ANSWER_LABELS: Record<Answer, string> = { yes: "Yes", no: "No", do_not_know: "Not known" };

function pointsLabel(points: number) {
    return points > 0 ? `+${points}` : String(points);
}

function without<T extends object>(record: T, key: keyof T): T {
    const copy = { ...record };
    delete copy[key];
    return copy;
}

/** The basis of the clinician's latest entry for a question, or null when there is none. */
function latestBasis(evidence: ADRReviewEvidence[], question: string): string | null {
    for (let index = evidence.length - 1; index >= 0; index -= 1) {
        const entry = evidence[index];
        if (entry.question === question && entry.source === "clinician_entry") {
            return entry.evidence ?? null;
        }
    }
    return null;
}

/**
 * PV-001-D: the Naranjo questions a patient is never asked, recorded by the clinician.
 * A recorded question shows its answer and basis and is changed on purpose; only questions
 * changed in this form are sent, and a Yes or No needs its basis. Saving recalculates the
 * score; it does not review or close the case.
 */
export function ADRClinicianAnswers({
    answers,
    evidence = [],
    disabled,
    onRecord,
}: {
    /** The assessment's stored Naranjo answers, by question. */
    answers: Record<string, string>;
    /** The assessment's evidence, oldest first; the latest clinician entry supplies the basis. */
    evidence?: ADRReviewEvidence[];
    disabled: boolean;
    onRecord: (answers: ADRClinicianAnswerInput[]) => Promise<void>;
}) {
    const [staged, setStaged] = useState<Staged>({});
    const [changing, setChanging] = useState<Changing>({});
    const pending = useRef(false);

    const entries = Object.entries(staged) as Array<[ClinicianQuestion, { answer: Answer; basis: string }]>;
    const incomplete = entries.some(
        ([, value]) =>
            value.answer !== "do_not_know" &&
            (!value.basis.trim() || value.basis.length > MAX_BASIS_LENGTH),
    );
    const editing = entries.length > 0 || Object.keys(changing).length > 0;

    function choose(question: ClinicianQuestion, answer: Answer) {
        setStaged((current) => ({
            ...current,
            [question]: { answer, basis: current[question]?.basis ?? "" },
        }));
    }

    function setBasis(question: ClinicianQuestion, basis: string) {
        setStaged((current) => {
            const value = current[question];
            return value ? { ...current, [question]: { ...value, basis } } : current;
        });
    }

    function startChange(question: ClinicianQuestion) {
        setChanging((current) => ({ ...current, [question]: true }));
    }

    function cancelChange(question: ClinicianQuestion) {
        setChanging((current) => without(current, question));
        setStaged((current) => without(current, question));
    }

    function clearAll() {
        setStaged({});
        setChanging({});
    }

    async function submit(event: FormEvent) {
        event.preventDefault();
        if (disabled || pending.current || entries.length === 0 || incomplete) return;
        pending.current = true;
        try {
            await onRecord(
                entries.map(([question, value]) => ({
                    question,
                    answer: value.answer,
                    ...(value.answer !== "do_not_know" ? { basis: value.basis.trim() } : {}),
                })),
            );
            clearAll();
        } catch {
            // The page shows the failure; the staged answers stay for a retry.
        } finally {
            pending.current = false;
        }
    }

    return (
        <section aria-labelledby="adr-clinician-answers" className="rounded-xl border border-line bg-surface p-5">
            <h2 className="text-sm font-semibold text-ink" id="adr-clinician-answers">
                Clinician answers
            </h2>
            <p className="mt-1 max-w-[72ch] text-[13px] leading-relaxed text-muted">
                These questions need clinical judgment, the literature or a test result, so the
                patient is never asked them. A recorded answer is shown below; use Change answer to
                record a different one, and the earlier answer stays in the evidence history. Saving
                recalculates the score and is audited; it does not review or close the case. The score
                supports your review; it is not a verdict.
            </p>
            <form className="mt-4 space-y-4" onSubmit={submit}>
                {CLINICIAN_QUESTIONS.map(({ question, prompt, points }) => {
                    const current = answers[question] as Answer | undefined;
                    const value = staged[question];
                    const basisId = `adr-basis-${question}`;
                    const showChoices = !current || Boolean(value) || Boolean(changing[question]);
                    const recordedBasis = current ? latestBasis(evidence, question) : null;
                    const recordedPoints = current
                        ? current === "yes"
                            ? points.yes
                            : current === "no"
                              ? points.no
                              : 0
                        : 0;
                    return (
                        <fieldset className="min-w-0 space-y-2 border-t border-line pt-3 first:border-t-0 first:pt-0" key={question}>
                            <legend className="text-sm font-medium text-ink">{questionLabel(question)}</legend>
                            <p className="text-[13px] text-ink-2">{prompt}</p>
                            {showChoices ? (
                                <>
                                    <p className="text-xs text-muted">
                                        {current ? "Recording a different answer" : "Not recorded yet"}
                                        <span aria-hidden="true"> · </span>
                                        Yes {pointsLabel(points.yes)}, No {pointsLabel(points.no)}, Not known 0
                                    </p>
                                    <div className="flex flex-wrap items-center gap-2" role="radiogroup" aria-label={questionLabel(question)}>
                                        {(Object.keys(ANSWER_LABELS) as Answer[]).map((answer) => (
                                            <label
                                                className="inline-flex min-h-8 cursor-pointer items-center gap-2 rounded-lg border border-line-strong bg-surface px-2.5 text-[13px] text-ink-2 hover:border-primary"
                                                key={answer}
                                            >
                                                <input
                                                    checked={value?.answer === answer}
                                                    className="h-4 w-4 accent-[var(--color-primary)]"
                                                    disabled={disabled}
                                                    name={`adr-answer-${question}`}
                                                    onChange={() => choose(question, answer)}
                                                    type="radio"
                                                />
                                                {ANSWER_LABELS[answer]}
                                            </label>
                                        ))}
                                        {current ? (
                                            <Button disabled={disabled} onClick={() => cancelChange(question)} variant="ghost">
                                                Keep recorded answer
                                            </Button>
                                        ) : null}
                                    </div>
                                    {value && value.answer !== "do_not_know" ? (
                                        <label className="block text-[13px] font-medium text-ink-2" htmlFor={basisId}>
                                            Basis for {questionLabel(question).toLowerCase()} (required)
                                            <textarea
                                                className="mt-1.5 block min-h-16 w-full rounded-[10px] border border-line-strong bg-surface px-3.5 py-2.5 text-sm font-normal text-ink outline-none transition focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)] disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-muted"
                                                disabled={disabled}
                                                id={basisId}
                                                maxLength={MAX_BASIS_LENGTH}
                                                onChange={(event) => setBasis(question, event.target.value)}
                                                placeholder="For example the label section, the test and its result, or the other cause considered."
                                                value={value.basis}
                                            />
                                            <span className="mt-1 block text-right font-mono text-[11px] font-normal text-muted">
                                                {value.basis.length} of {MAX_BASIS_LENGTH} characters
                                            </span>
                                        </label>
                                    ) : null}
                                </>
                            ) : (
                                <>
                                    <div className="flex flex-wrap items-center gap-2">
                                        <Badge variant={current === "yes" ? "success" : "neutral"}>
                                            {ANSWER_LABELS[current as Answer] ?? current}
                                        </Badge>
                                        <span className="text-xs text-muted">
                                            Recorded <span aria-hidden="true">· </span>
                                            {pointsLabel(recordedPoints)} toward the score
                                        </span>
                                        <Button disabled={disabled} onClick={() => startChange(question)} variant="ghost">
                                            Change answer
                                        </Button>
                                    </div>
                                    {recordedBasis ? (
                                        <blockquote className="max-w-[72ch] border-l-2 border-line-strong pl-3 text-sm leading-relaxed text-ink-2">
                                            “{recordedBasis}”
                                        </blockquote>
                                    ) : null}
                                </>
                            )}
                        </fieldset>
                    );
                })}
                <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
                    <Button disabled={disabled || entries.length === 0 || incomplete} type="submit">
                        Save clinician answers
                    </Button>
                    {editing ? (
                        <Button disabled={disabled} onClick={clearAll} variant="ghost">
                            Clear changes
                        </Button>
                    ) : null}
                    {incomplete ? (
                        <p className="text-[13px] text-warn-ink" role="status">
                            Add the basis for each Yes or No answer.
                        </p>
                    ) : null}
                </div>
            </form>
        </section>
    );
}
