"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useSelector } from "react-redux";
import { Button } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { IconTile } from "@/components/ui/list";
import { ProcessingDots } from "@/components/ui/motion";
import type { ADRFollowUpCopy } from "@/content/adr-follow-up-copy";
import {
  classifyADRFollowUpError,
  respondToADRInformationRequest,
  type ADRFollowUpErrorClass,
  type ADRFollowUpRequest,
  type ADRInformationAnswerInput,
  type PatientADRAnswer,
  type PatientADRQuestion,
} from "@/services/adr-follow-up";
import type { RootState } from "@/store/store";
import type { Locale } from "@/types";

const EVIDENCE_MAX = 500;
const ANSWER_ORDER: PatientADRAnswer[] = ["yes", "no", "do_not_know"];

// The radios and the checkbox are visually hidden or small, and global CSS
// removes the outline from focused inputs, so the label carries the ring.
const focusRing =
  "has-[:focus-visible]:ring-4 has-[:focus-visible]:ring-brand/25";

interface DraftAnswer {
  answer?: PatientADRAnswer;
  evidence: string;
}

interface ADRFollowUpFormProps {
  request: ADRFollowUpRequest;
  copy: ADRFollowUpCopy;
  locale: Locale;
  /** Called after the answers are saved. The host shows the confirmation. */
  onSent: (requestId: string) => void;
  /** Called when the request is no longer answerable. The host refetches. */
  onClosed: () => void;
}

/**
 * Answer form for one pending care-team information request. Draft answers
 * live only in component state; nothing is written to browser storage.
 */
export function ADRFollowUpForm({
  request,
  copy,
  locale,
  onSent,
  onClosed,
}: ADRFollowUpFormProps) {
  const accessToken = useSelector((state: RootState) => state.auth.accessToken);
  const baseId = useId();
  const titleId = `${baseId}-title`;
  const [answers, setAnswers] = useState<Record<string, DraftAnswer>>({});
  const [reviewing, setReviewing] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorClass, setErrorClass] = useState<ADRFollowUpErrorClass | null>(
    null,
  );
  const reviewHeadingRef = useRef<HTMLHeadingElement>(null);
  // The shared Button does not forward refs, so focus it through its wrapper.
  const reviewActionRef = useRef<HTMLDivElement>(null);
  const stepChanged = useRef(false);

  // A closed or missing request cannot be retried; the host refetches instead.
  const terminal = errorClass === "closed" || errorClass === "notFound";

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
      draft?.answer &&
        (draft.answer === "do_not_know" || draft.evidence.trim()),
    );
  });

  // Move focus to the start of the new step after Review or Edit, not on mount.
  useEffect(() => {
    if (!stepChanged.current) return;
    if (reviewing) reviewHeadingRef.current?.focus();
    else reviewActionRef.current?.querySelector("button")?.focus();
  }, [reviewing]);

  function changeStep(next: boolean) {
    stepChanged.current = true;
    setErrorClass(null);
    setReviewing(next);
  }

  function setAnswer(question: PatientADRQuestion, answer: PatientADRAnswer) {
    setAnswers((current) => ({
      ...current,
      [question]: { answer, evidence: current[question]?.evidence ?? "" },
    }));
  }

  function setEvidence(question: PatientADRQuestion, evidence: string) {
    setAnswers((current) => ({
      ...current,
      [question]: { answer: current[question]?.answer, evidence },
    }));
  }

  async function submit() {
    if (!accessToken || !confirmed || !complete || submitting || terminal) {
      return;
    }
    setSubmitting(true);
    setErrorClass(null);
    try {
      await respondToADRInformationRequest(
        accessToken,
        request.id,
        answerInputs,
      );
      onSent(request.id);
    } catch (submissionError) {
      // Never render the server message; show the localized class copy.
      const classified = classifyADRFollowUpError(submissionError);
      setErrorClass(classified);
      if (classified === "closed" || classified === "notFound") onClosed();
    } finally {
      setSubmitting(false);
    }
  }

  const message = request.patientMessage.trim();

  return (
    <section
      aria-labelledby={titleId}
      className="overflow-hidden rounded-[22px] bg-surface"
      lang={locale}
    >
      <header className="border-b border-line px-[14px] py-[13px]">
        <div className="flex items-start gap-3">
          <IconTile icon="note" size="sm" tone="note" />
          <div className="min-w-0 flex-1">
            <p className="font-mono text-xs uppercase tracking-[0.08em] text-muted">
              {copy.eyebrow}
            </p>
            <h2
              className="mt-1 break-words text-[17px] font-semibold leading-snug text-ink [overflow-wrap:anywhere]"
              id={titleId}
            >
              {copy.heading(request.symptom)}
            </h2>
            <p className="mt-1 break-words text-sm text-muted [overflow-wrap:anywhere]">
              {copy.reportedWith(request.suspectMedicationName)}
            </p>
          </div>
        </div>
        {message ? (
          <div className="mt-3 rounded-xl bg-surface-2 p-3 text-sm text-ink-2">
            <p className="font-semibold">{copy.careTeamMessage}</p>
            <p className="mt-1 whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
              {request.patientMessage}
            </p>
          </div>
        ) : null}
        <p className="mt-3 flex items-start gap-2 rounded-2xl bg-note-tint px-3.5 py-2.5 text-[13px] leading-snug text-note-ink">
          <Icon className="mt-px h-4 w-4 shrink-0" name="info" />
          <span className="min-w-0 break-words">{copy.caution}</span>
        </p>
      </header>

      {!reviewing ? (
        <div className="ma-enter" key="answer">
          {request.requestedInformation.map((question) => {
            const questionCopy = copy.questions[question];
            const draft = answers[question] ?? { evidence: "" };
            const needsEvidence =
              draft.answer !== undefined && draft.answer !== "do_not_know";
            const evidenceId = `${baseId}-${question}-evidence`;
            const counterId = `${evidenceId}-count`;
            return (
              <fieldset
                className="min-w-0 border-b border-line px-[14px] py-[13px]"
                key={question}
              >
                <legend className="float-left mb-3 w-full break-words text-[15px] font-semibold leading-snug text-ink">
                  {questionCopy.prompt}
                </legend>
                <div className="clear-left grid grid-cols-3 gap-2">
                  {ANSWER_ORDER.map((answer) => {
                    const selected = draft.answer === answer;
                    return (
                      <label
                        className={`ma-press flex min-h-11 cursor-pointer items-center justify-center gap-1.5 rounded-2xl border px-2 py-2 text-center text-sm font-semibold break-words ${focusRing} ${
                          selected
                            ? "border-brand bg-brand text-white"
                            : "border-line-strong bg-surface text-ink-2 hover:border-brand/40"
                        }`}
                        key={answer}
                      >
                        <input
                          checked={selected}
                          className="sr-only"
                          name={`${baseId}-${question}`}
                          onChange={() => setAnswer(question, answer)}
                          type="radio"
                          value={answer}
                        />
                        {selected ? (
                          <Icon className="h-4 w-4 shrink-0" name="check" />
                        ) : null}
                        <span className="min-w-0">{copy.answers[answer]}</span>
                      </label>
                    );
                  })}
                </div>
                {needsEvidence ? (
                  <div className="mt-3 space-y-2">
                    <label
                      className="block break-words text-sm font-semibold text-ink-2"
                      htmlFor={evidenceId}
                    >
                      {questionCopy.evidencePrompt}
                    </label>
                    <textarea
                      aria-describedby={counterId}
                      aria-required="true"
                      className="min-h-24 w-full rounded-2xl border border-line-strong bg-surface px-4 py-3 text-base text-ink outline-none transition placeholder:text-muted focus:border-brand focus:ring-4 focus:ring-brand/15"
                      id={evidenceId}
                      maxLength={EVIDENCE_MAX}
                      onChange={(event) =>
                        setEvidence(question, event.target.value)
                      }
                      rows={3}
                      value={draft.evidence}
                    />
                    <p
                      className="text-right font-mono text-xs text-muted"
                      id={counterId}
                    >
                      {copy.characters(draft.evidence.length, EVIDENCE_MAX)}
                    </p>
                  </div>
                ) : null}
              </fieldset>
            );
          })}
          <div className="px-[14px] py-[13px]" ref={reviewActionRef}>
            <Button
              disabled={!complete}
              fullWidth
              onClick={() => changeStep(true)}
            >
              {copy.reviewAnswers}
            </Button>
          </div>
        </div>
      ) : (
        <div className="ma-enter" key="review">
          <div className="border-b border-line px-[14px] py-[13px]">
            <h3
              className="text-[15px] font-semibold text-ink outline-none"
              ref={reviewHeadingRef}
              tabIndex={-1}
            >
              {copy.reviewHeading}
            </h3>
            <dl className="mt-2 divide-y divide-line">
              {answerInputs.map((item) => (
                <div className="py-2.5" key={item.question}>
                  <dt className="break-words text-[13px] text-muted">
                    {copy.questions[item.question].label}
                  </dt>
                  <dd className="mt-0.5 text-sm font-semibold text-ink">
                    {copy.answers[item.answer]}
                  </dd>
                  {item.evidence ? (
                    <dd className="mt-1 whitespace-pre-wrap break-words text-sm text-ink-2 [overflow-wrap:anywhere]">
                      {item.evidence}
                    </dd>
                  ) : null}
                </div>
              ))}
            </dl>
          </div>
          <div className="space-y-3 px-[14px] py-[13px]">
            <label
              className={`flex min-h-11 w-full cursor-pointer items-start gap-3 rounded-2xl py-2 text-sm leading-6 text-ink-2 ${focusRing}`}
            >
              <input
                checked={confirmed}
                className="mt-0.5 h-5 w-5 shrink-0 accent-brand"
                disabled={submitting || terminal}
                onChange={(event) => setConfirmed(event.target.checked)}
                type="checkbox"
              />
              <span className="min-w-0 break-words">{copy.confirm}</span>
            </label>
            {errorClass ? (
              <p
                className="rounded-2xl bg-danger-tint p-3.5 text-sm text-danger-ink"
                role="alert"
              >
                {copy.errors[errorClass]}
              </p>
            ) : null}
            <p className="text-[13px] text-muted">{copy.unsentNote}</p>
            <div className="flex flex-wrap gap-2 [&_button]:min-h-11">
              <Button
                aria-busy={submitting}
                className="flex-1"
                disabled={!confirmed || submitting || terminal}
                onClick={() => void submit()}
              >
                {submitting ? (
                  <>
                    <ProcessingDots className="bg-current" />
                    {copy.sending}
                  </>
                ) : (
                  copy.send
                )}
              </Button>
              <Button
                disabled={submitting || terminal}
                onClick={() => changeStep(false)}
                variant="ghost"
              >
                {copy.edit}
              </Button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
