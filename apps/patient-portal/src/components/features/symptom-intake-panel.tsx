"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import Link from "next/link";
import { getSymptomIntakeCopy, intakeErrorCopy, intakeValueCopy, offerAnswer } from "@/content/symptom-intake-copy";
import { formatTimezoneLabel } from "@/content/timezone-label";
import { useSymptomIntake } from "@/hooks/use-symptom-intake";
import type { PrivateReplyHandler } from "@/hooks/use-patient-chat-session";
import { IntakeAnswerForm } from "@/components/features/intake-answer-form";
import { ChatBubble } from "@/components/features/chat-bubble";
import { buildRecordsDocumentHref } from "@/components/features/chat-results-card";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icons";
import type { Locale } from "@/types";

export type IntakeComposerState = { active: boolean; busy: boolean; revision: string; locale?: Locale; accepting?: boolean };
type Props = {
    locale: Locale; sourceMessageId?: string; sessionId?: string;
    registerReply?: (handler: PrivateReplyHandler | null) => void;
    onComposerState?: (state: IntakeComposerState) => void;
    onRestoreInput?: (text: string) => void;
    onReadAloud?: (text: string, locale: Locale) => void;
    handsFree?: boolean;
    /** The newest unanswered symptom-note offer: a typed or spoken yes/no answers it. */
    offerSourceId?: string;
    /** The patient answered (or started) this offer, so it is not asked again. */
    onOfferAnswered?: (sourceMessageId: string) => void;
    onFocusComposer?: () => void;
};

/** The record's printed values, without the internal field names (UX-007). */
function recordValue(value: unknown, labels: Record<string, string>, fallback: string): string {
    if (typeof value === "string" || typeof value === "number") return String(value);
    if (!value || typeof value !== "object") return "";
    const parts = Object.entries(value).filter(([key, item]) => !/(?:^id$|_id$|source|patient)/i.test(key) && ["string", "number"].includes(typeof item) && String(item).trim());
    // A single amount is already labelled by its fact type. Multiple values need
    // labels so a result cannot be confused with its range, dose or date.
    if (parts.length === 1) return String(parts[0][1]);
    return parts.map(([key, item]) => `${labels[key] ?? fallback}: ${item}`).join(" · ");
}

export function SymptomIntakePanel({ locale: appLocale, sessionId = "default",
    registerReply, onComposerState, onRestoreInput, onReadAloud, handsFree = false, offerSourceId, onOfferAnswered, onFocusComposer }: Props) {
    const intake = useSymptomIntake(sessionId);
    const draft = intake.draft;
    const locale = draft?.locale ?? appLocale;
    const copy = getSymptomIntakeCopy(locale);
    const [editSelection, setEditSelection] = useState<{ intakeId: string; questionId: string } | null>(null);
    const editing = editSelection && editSelection.intakeId === draft?.intake_id ? editSelection.questionId : null;
    function setEditing(questionId: string | null) {
        setEditSelection(questionId && draft ? { intakeId: draft.intake_id, questionId } : null);
    }
    const [consent, setConsent] = useState<string | null>(null);
    const [hint, setHint] = useState(false);
    const [starting, setStarting] = useState(false);
    const [reloading, setReloading] = useState(false);
    const [reportedOpen, setReportedOpen] = useState(false);
    const answered = useRef(onOfferAnswered);
    const focusComposer = useRef(onFocusComposer);
    useLayoutEffect(() => { answered.current = onOfferAnswered; focusComposer.current = onFocusComposer; }, [onOfferAnswered, onFocusComposer]);
    const startDraft = intake.start;
    const startLatest = useRef(startDraft);
    useLayoutEffect(() => { startLatest.current = startDraft; }, [startDraft]);
    function beginFrom(sourceId: string) {
        setStarting(true);
        void Promise.resolve(startLatest.current(sourceId)).then((result) => { if (result) answered.current?.(sourceId); })
            .finally(() => setStarting(false));
    }
    const beginRef = useRef(beginFrom);
    useLayoutEffect(() => { beginRef.current = beginFrom; });
    useEffect(() => {
        const onStart = (event: Event) => {
            const id = (event as CustomEvent<{ sourceMessageId?: string }>).detail?.sourceMessageId;
            if (id) beginRef.current(id);
        };
        window.addEventListener("symptom-intake-start", onStart);
        return () => window.removeEventListener("symptom-intake-start", onStart);
    }, []);
    const [unsaved, setUnsaved] = useState<{ text: string; intakeId: string; questionId: string; revision: number } | null>(null);
    const reader = useRef(onReadAloud);
    useLayoutEffect(() => { reader.current = onReadAloud; }, [onReadAloud]);
    const lastSpoken = useRef("");
    const active = Boolean(draft && ["collecting", "ready_for_confirmation"].includes(draft.status));
    const question = editing ? draft?.questions?.find((q) => q.id === editing) : draft?.current_question;
    const disabled = intake.busy || intake.pending || !draft?.library_available;
    const consentKey = `${draft?.intake_id}:${draft?.revision}:${draft?.preview_hash}:${locale}`;
    const button = "ma-press min-h-11 rounded-full border border-line-strong bg-surface px-4 py-2 text-sm font-medium text-ink-2 hover:border-brand/40 hover:text-brand-ink disabled:opacity-50";
    const suggestion = question && draft?.suggestions?.[question.id];
    const prompt = draft?.preview && !editing ? `${copy.summary}. ${draft.preview.summary}. ${copy.reviewFirst}`
        : question ? `${question.wording[locale]} ${suggestion !== undefined ? `${copy.suggestion}: ${suggestion}. ${copy.useSuggestion}. ` : ""}${copy.answerPrompt}` : copy.reviewFirst;

    function save(state: "answered" | "unknown" | "declined", value: unknown, wording = "", input_mode: "form" | "typed" | "voice" = "form") {
        if (!question) return;
        intake.mutate("answers", { mutation_id: crypto.randomUUID(), question_id: question.id, state, value, wording, locale, input_mode });
        setEditing(null); setConsent(null); setHint(false);
    }

    useLayoutEffect(() => {
        registerReply?.((text, mode, spokenLocale) => {
            if (!active || !draft) {
                const reply = offerSourceId ? offerAnswer(text) : null;
                if (!offerSourceId || !reply) return "unhandled";
                if (intake.busy || intake.pending || starting) return "blocked";
                if (reply === "yes") beginFrom(offerSourceId); else answered.current?.(offerSourceId);
                return "handled";
            }
            if (disabled) return "blocked";
            const command = text.trim().toLocaleLowerCase().replace(/[.!?]+$/, "");
            if (["cancel draft", "cancelar borrador"].includes(command)) {
                intake.mutate("cancel", { mutation_id: crypto.randomUUID() });
            } else if (["review", "review before sharing", "revisar", "revisar antes de compartir"].includes(command) && draft.can_review) {
                setConsent(null); intake.mutate("preview", {});
            } else if (question) {
                setUnsaved({ text, intakeId: draft.intake_id, questionId: question.id, revision: draft.revision });
                if (suggestion !== undefined && ["use this answer", "use that", "usar esta respuesta", "usa esa respuesta"].includes(command)) {
                    save("answered", suggestion, String(suggestion), mode);
                } else {
                    intake.mutate("reply", { mutation_id: crypto.randomUUID(), question_id: question.id,
                        text, input_mode: mode, locale: spokenLocale ?? locale });
                    setEditing(null); setConsent(null); setHint(false);
                }
            } else {
                setHint(true);
                reader.current?.(copy.reviewFirst, locale);
                return "blocked";
            }
            return "handled";
        });
        onComposerState?.({ active, locale, accepting: Boolean(active && question), busy: Boolean(active && disabled), revision: `${draft?.intake_id}:${draft?.revision}:${editing}` });
        return () => registerReply?.(null);
    });

    useEffect(() => {
        const identity = `${draft?.intake_id}:${draft?.revision}:${question?.id}:${draft?.preview_hash}:${locale}`;
        if (active && handsFree && !disabled && identity !== lastSpoken.current) {
            lastSpoken.current = identity;
            reader.current?.(prompt, locale);
        }
    }, [active, handsFree, disabled, draft?.intake_id, draft?.revision, draft?.preview_hash, question?.id, locale, prompt]);

    const questionKey = active ? `${draft?.intake_id}:${question?.id}:${draft?.preview_hash ?? ""}` : "";
    const previousKey = useRef("");
    useEffect(() => {
        if (questionKey && questionKey !== previousKey.current) focusComposer.current?.();
        previousKey.current = questionKey;
    }, [questionKey]);

    if (!draft && !intake.error && !intake.pending && !starting && !(reloading && intake.busy)) return null;
    const title = draft?.status === "confirmed" ? copy.saved : draft?.status === "cancelled" ? copy.cancelled
        : draft?.status === "interrupted_safety" ? copy.interrupted : copy.title;
    return <section className="flex min-w-0 max-w-full flex-col items-start gap-2.5 break-words" aria-label={title} lang={locale}>
        {intake.busy && (draft || starting || reloading) && <p role="status" className="text-sm text-muted">{copy.loading}</p>}
        {intake.error && <div role="alert"><p>{intakeErrorCopy(String(intake.error), locale)}</p><button className={button} disabled={intake.busy} onClick={() => { setReloading(true); void intake.reload(); }}>{copy.reload}</button></div>}
        {intake.pending && <button className={button} disabled={intake.busy} onClick={intake.retry}>{copy.retry}</button>}
        {draft && <>
            <div className="flex flex-wrap items-center gap-2">
                <h2 className="inline-flex items-center gap-1.5 rounded-full bg-brand-tint px-2.5 py-1 text-xs font-semibold text-brand-ink">
                    {active && <Icon name="lock" className="h-3.5 w-3.5" aria-hidden="true" />}{title}</h2>
                {active && <span className="text-xs text-muted">{copy.privateTag}</span>}
            </div>
            {active && <p className="text-xs text-muted">{copy.intro}</p>}
            {draft.existing_draft && active && <p role="status">{copy.existingDraft}</p>}
            {draft.review_requested && <p role="status" className="rounded-xl bg-note-tint p-3 text-note-ink">{copy.urgentReview}</p>}
            {draft.safety && <div role="alert" className="rounded-xl bg-danger-tint p-3 text-danger-ink"><p>{draft.safety.response_text}</p>
                {draft.persistence_status === "uncertain" && <p>{copy.pending}</p>}</div>}
            {active && !draft.library_available && <p role="status">{copy.unavailable}</p>}
            {active && question && <div className="flex min-w-0 max-w-full flex-col items-start gap-2.5" aria-live="polite">
                {registerReply ? <>
                    <ChatBubble role="assistant" timestamp="" content={question.wording[locale]} locale={locale} language={locale}
                        onPlayAudio={onReadAloud ? () => onReadAloud(prompt, locale) : undefined} />
                    <p className="px-1 text-xs text-muted">{copy.answerPrompt}</p>
                    <div className="flex flex-wrap gap-2">
                        <button className={button} disabled={disabled} onClick={() => save("unknown", null)}>{copy.unknown}</button>
                        <button className={button} disabled={disabled} onClick={() => save("declined", null)}>{copy.declined}</button>
                    </div>
                    <details className="px-1"><summary className="min-h-11 cursor-pointer py-2 text-sm font-medium text-ink-2">{copy.detailEntry}</summary>
                        <IntakeAnswerForm key={`${draft.intake_id}:${draft.revision}:${question.id}`} question={question} locale={locale}
                            answer={draft.answers[question.id]} disabled={disabled} save={save} />
                    </details>
                </> : <IntakeAnswerForm key={`${draft.intake_id}:${draft.revision}:${question.id}`} question={question} locale={locale}
                    answer={draft.answers[question.id]} disabled={disabled} save={save} />}
                {suggestion !== undefined && !(question.id in draft.answers) && <div className="rounded-2xl border border-line bg-surface p-3">
                    <p className="text-xs font-semibold text-muted">{copy.suggestion}</p><p className="whitespace-pre-wrap">{suggestion}</p>
                    <button className={button} disabled={disabled} onClick={() => save("answered", suggestion, String(suggestion))}>{copy.useSuggestion}</button>
                </div>}
            </div>}
            {active && unsaved?.intakeId === draft.intake_id && unsaved.questionId === question?.id && unsaved.revision === draft.revision && <div className="rounded-2xl bg-brand-tint/60 p-3">
                <p className="text-xs text-muted">{copy.pendingAnswer}</p><p>{unsaved.text}</p>
                {intake.error && !intake.pending && <button className={button} onClick={() => onRestoreInput?.(unsaved.text)}>{copy.editReply}</button>}
            </div>}
            {active && <details className="w-full px-1" open={reportedOpen} onToggle={(event) => setReportedOpen(event.currentTarget.open)}><summary className="min-h-11 cursor-pointer py-2 text-sm font-medium text-ink-2">{copy.reported}</summary>
                <p className="text-xs text-muted">{draft.timezone_fallback ? copy.fallback : `${copy.timezone} ${formatTimezoneLabel(draft.timezone, locale)}`}</p>
                <dl className="space-y-3">{Object.entries(draft.answers).map(([id, answer]) => <div key={id}>
                    <dt className="text-sm font-medium">{draft.questions?.find((q) => q.id === id)?.wording[locale] ?? copy.value}</dt>
                    <dd className="text-sm" lang={answer.locale}>{answer.state === "answered" ? intakeValueCopy(answer.value, locale) : copy.states[answer.state]}</dd>
                    <button className={button} disabled={disabled} onClick={() => { setEditing(id); setConsent(null); }}>{copy.edit}</button>
                </div>)}</dl></details>}
            {active && !draft.preview && <div className="flex flex-wrap gap-2">
                <button className={button} disabled={disabled || Boolean(editing) || !draft.can_review} onClick={() => { setConsent(null); intake.mutate("preview", {}); }}>{copy.review}</button>
                <button className={button} disabled={intake.busy || intake.pending} onClick={() => intake.mutate("cancel", { mutation_id: crypto.randomUUID() })}>{copy.cancel}</button>
            </div>}
            {hint && <p role="status">{copy.reviewFirst}</p>}
            {active && draft.preview && <section className="w-full max-w-[92%] space-y-3 rounded-[20px_20px_20px_6px] bg-surface p-4 shadow-[0_1px_0_rgba(16,32,43,.04)]" aria-live="polite">
                <h3 className="font-semibold">{copy.summary}</h3><p className="whitespace-pre-line" lang={draft.locale}>{draft.preview.summary}</p>
                {onReadAloud && <button className={button} onClick={() => onReadAloud(prompt, locale)}>{copy.listen}</button>}
                <p className="text-sm text-ink-2">{copy.productReported}</p>
                <h3 className="font-semibold">{copy.context}</h3>
                {!draft.preview.context.medications.length && !draft.preview.context.facts.length && <p>{copy.emptyContext}</p>}
                {draft.preview.context.medications.map((med, i) => <p key={i}>{[med.name, med.dose, med.frequency].filter((part) => typeof part === "string" || typeof part === "number").map(String).filter((part) => part.trim()).join(" · ")}</p>)}
                {draft.preview.context.facts.map((fact, i) => <p key={i}>{copy.factLabels[String(fact.fact_type)] ?? copy.recordDetail}: {recordValue(fact.value, copy.factFieldLabels, copy.recordDetail)} <cite className="text-xs text-muted">({typeof fact.document_id === "string"
                    ? <Link className="underline" href={buildRecordsDocumentHref(fact.document_id)}>{copy.recordSource} {i + 1}</Link> : <>{copy.recordSource} {i + 1}</>})</cite></p>)}
                {draft.preview.context.excerpts.map((excerpt, i) => <blockquote className="border-l-2 border-brand pl-3" key={i}>{String(excerpt.text)} <cite className="text-xs text-muted">{typeof excerpt.document_id === "string"
                    ? <Link className="underline" href={buildRecordsDocumentHref(excerpt.document_id)}>{copy.excerptSource} {i + 1}</Link> : <>{copy.excerptSource} {i + 1}</>}</cite></blockquote>)}
                <label className="flex min-h-11 items-start gap-2"><input className="mt-1 h-5 w-5" type="checkbox" checked={consent === consentKey} disabled={disabled || Boolean(editing)}
                    onChange={(e) => setConsent(e.target.checked ? consentKey : null)} />{copy.consent}</label>
                <Button fullWidth disabled={disabled || Boolean(editing) || !draft.can_confirm || consent !== consentKey}
                    onClick={() => intake.mutate("confirm", { confirmation_id: crypto.randomUUID(), preview_hash: draft.preview_hash, consent: true })}>{copy.confirm}</Button>
                <div className="flex flex-wrap gap-2">
                    <button className={button} type="button" disabled={disabled} onClick={() => { setReportedOpen(true); setConsent(null); }}>{copy.edit}</button>
                    <button className={button} type="button" disabled={intake.busy || intake.pending} onClick={() => intake.mutate("cancel", { mutation_id: crypto.randomUUID() })}>{copy.cancel}</button>
                </div>
            </section>}
        </>}
    </section>;
}
