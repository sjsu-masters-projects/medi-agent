"use client";

import { useId, useState } from "react";
import { useSelector } from "react-redux";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icons";
import { IconTile } from "@/components/ui/list";
import {
  describeMedicine,
  getMedicationConfirmationCopy,
  type MedicationConfirmationCopy,
} from "@/content/medication-confirmation-copy";
import { useMedicationQuestions } from "@/hooks/use-medication-questions";
import {
  answerMedicationQuestion,
  classifyMedicationAnswerError,
  type MedicationAnswer,
  type MedicationAnswerErrorClass,
  type MedicationQuestion,
} from "@/services/medication-confirmations";
import type { RootState } from "@/store/store";
import type { Locale } from "@/types";

const NOTE_MAX = 500;
const ORDER: MedicationAnswer[] = ["yes", "stopped", "changed", "unsure"];
// Global CSS removes the outline from focused inputs, so the label carries the ring.
const focusRing = "has-[:focus-visible]:ring-4 has-[:focus-visible]:ring-brand/25";

function QuestionCard({
  question,
  copy,
  locale,
  onSent,
}: {
  question: MedicationQuestion;
  copy: MedicationConfirmationCopy;
  locale: Locale;
  onSent: (sent: MedicationQuestion) => void;
}) {
  const accessToken = useSelector((state: RootState) => state.auth.accessToken);
  const baseId = useId();
  const [choice, setChoice] = useState<MedicationAnswer | null>(null);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errorClass, setErrorClass] = useState<MedicationAnswerErrorClass | null>(null);
  const medicine = describeMedicine(question, locale);
  const ready = choice !== null && (choice !== "changed" || note.trim().length > 0);
  // A closed or missing question cannot be retried.
  const terminal = errorClass === "answered" || errorClass === "expired" || errorClass === "notFound";

  async function submit() {
    if (!accessToken || !choice || !ready || submitting || terminal) return;
    setSubmitting(true);
    setErrorClass(null);
    try {
      const saved = await answerMedicationQuestion(
        accessToken,
        question.id,
        choice,
        choice === "changed" ? note : undefined,
      );
      onSent(saved);
    } catch (error) {
      setErrorClass(classifyMedicationAnswerError(error));
    } finally {
      setSubmitting(false);
    }
  }

  const noteId = `${baseId}-note`;
  const countId = `${baseId}-count`;
  return (
    <article
      aria-label={copy.eyebrow}
      className="rounded-[22px] bg-surface p-5 shadow-[var(--shadow-raised)]"
      lang={locale}
    >
      <div className="flex items-start gap-3">
        <IconTile icon="note" tone="med" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-[0.06em] text-muted">{copy.eyebrow}</p>
          {question.clinicianName ? (
            <p className="mt-0.5 break-words text-[13px] text-muted [overflow-wrap:anywhere]">
              {copy.from(question.clinicianName, question.specialty)}
            </p>
          ) : null}
        </div>
      </div>
      <fieldset className="mt-4 min-w-0" disabled={submitting}>
        <legend className="float-left mb-3 w-full break-words text-[19px] font-semibold leading-snug text-ink [overflow-wrap:anywhere]">
          {copy.question(medicine)}
        </legend>
        <div aria-label={copy.group(medicine)} className="clear-left grid grid-cols-2 gap-2" role="radiogroup">
          {ORDER.map((answer) => {
            const selected = choice === answer;
            return (
              <label
                className={`ma-press flex min-h-12 cursor-pointer items-center justify-center gap-1.5 rounded-2xl border px-2 py-2 text-center text-[15px] font-semibold break-words ${focusRing} ${
                  selected
                    ? "border-brand bg-brand text-white"
                    : "border-line-strong bg-surface text-ink-2 hover:border-brand/40"
                }`}
                key={answer}
              >
                <input
                  checked={selected}
                  className="sr-only"
                  name={`${baseId}-answer`}
                  onChange={() => {
                    setChoice(answer);
                    setErrorClass(null);
                  }}
                  type="radio"
                  value={answer}
                />
                {selected ? <Icon className="h-4 w-4 shrink-0" name="check" /> : null}
                <span className="min-w-0">{copy.answers[answer]}</span>
              </label>
            );
          })}
        </div>
        {choice === "changed" ? (
          <div className="mt-3 space-y-2">
            <label className="block break-words text-sm font-semibold text-ink-2" htmlFor={noteId}>
              {copy.changedLabel}
            </label>
            <textarea
              aria-describedby={countId}
              aria-required="true"
              className="min-h-24 w-full rounded-2xl border border-line-strong bg-surface px-4 py-3 text-base text-ink outline-none transition placeholder:text-muted focus:border-brand focus:ring-4 focus:ring-brand/15"
              id={noteId}
              maxLength={NOTE_MAX}
              onChange={(event) => setNote(event.target.value)}
              placeholder={copy.changedHint}
              rows={3}
              value={note}
            />
            <p className="text-right font-mono text-xs text-muted" id={countId}>
              {copy.characters(note.length, NOTE_MAX)}
            </p>
          </div>
        ) : null}
      </fieldset>
      {errorClass ? (
        <p className="mt-3 rounded-2xl bg-danger-tint p-3 text-sm text-danger-ink" role="alert">
          {copy.errors[errorClass]}
        </p>
      ) : null}
      <p className="mt-3 text-[13px] leading-snug text-muted">{copy.privacy}</p>
      <div className="mt-4">
        <Button disabled={!ready || submitting || terminal} fullWidth onClick={() => void submit()}>
          {submitting ? copy.sending : copy.send}
        </Button>
      </div>
    </article>
  );
}

/**
 * Open medication questions from the patient's care team, answered in place.
 *
 * An answer is the patient's own statement: it goes to the care team as evidence and changes
 * nothing about their medicines or reminders. Renders nothing while there is nothing to ask.
 */
export function MedicationQuestionCards({ locale }: { locale: Locale }) {
  const { items, refresh } = useMedicationQuestions();
  const [sent, setSent] = useState<Record<string, MedicationQuestion>>({});
  const copy = getMedicationConfirmationCopy(locale);
  const open = items.filter((item) => item.status === "open" && !sent[item.id]);
  const thanks = Object.values(sent);
  if (open.length === 0 && thanks.length === 0) return null;
  return (
    <section aria-label={copy.eyebrow} className="space-y-3 px-4">
      {open.map((question) => (
        <QuestionCard
          copy={copy}
          key={question.id}
          locale={locale}
          onSent={(saved) => {
            setSent((current) => ({ ...current, [question.id]: saved }));
            refresh();
          }}
          question={question}
        />
      ))}
      {thanks.map((question) => (
        <div
          className="flex items-start gap-3 rounded-[22px] bg-surface p-5"
          key={question.id}
          lang={locale}
          role="status"
        >
          <IconTile icon="check" tone="brand" />
          <div className="min-w-0">
            <p className="text-[15px] font-semibold text-ink">{copy.thanks}</p>
            <p className="break-words text-[13px] leading-snug text-muted [overflow-wrap:anywhere]">
              {copy.thanksDetail}
            </p>
          </div>
        </div>
      ))}
    </section>
  );
}
