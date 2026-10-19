"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import Link from "next/link";
import { getSymptomIntakeCopy, intakeErrorCopy, intakeValueCopy } from "@/content/symptom-intake-copy";
import { useSymptomIntake } from "@/hooks/use-symptom-intake";
import type { PrivateReplyHandler } from "@/hooks/use-patient-chat-session";
import { IntakeAnswerForm } from "@/components/features/intake-answer-form";
import { ChatBubble } from "@/components/features/chat-bubble";
import { buildRecordsDocumentHref } from "@/components/features/chat-results-card";
import { Button } from "@/components/ui/button";
import type { Locale } from "@/types";

export type IntakeComposerState = { active: boolean; busy: boolean; revision: string; locale?: Locale; accepting?: boolean };
type Props = {
    locale: Locale; sourceMessageId?: string; sessionId?: string;
    registerReply?: (handler: PrivateReplyHandler | null) => void;
    onComposerState?: (state: IntakeComposerState) => void;
    onRestoreInput?: (text: string) => void;
    onReadAloud?: (text: string, locale: Locale) => void;
    handsFree?: boolean;
};

function recordValue(value: unknown): string {
    if (typeof value === "string" || typeof value === "number") return String(value);
    if (!value || typeof value !== "object") return "";
    return Object.entries(value).filter(([key, item]) => !/(?:^id$|_id$|source|patient)/i.test(key) && ["string", "number"].includes(typeof item))
        .map(([key, item]) => `${key.replaceAll("_", " ")}: ${item}`).join(" · ");
}

export function SymptomIntakePanel({ locale: appLocale, sourceMessageId, sessionId = "default",
    registerReply, onComposerState, onRestoreInput, onReadAloud, handsFree = false }: Props) {
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
    const [unsaved, setUnsaved] = useState<{ text: string; intakeId: string; questionId: string; revision: number } | null>(null);
    const reader = useRef(onReadAloud);
    useLayoutEffect(() => { reader.current = onReadAloud; }, [onReadAloud]);
    const lastSpoken = useRef("");
    const active = Boolean(draft && ["collecting", "ready_for_confirmation"].includes(draft.status));
    const question = editing ? draft?.questions?.find((q) => q.id === editing) : draft?.current_question;
    const disabled = intake.busy || intake.pending || !draft?.library_available;
    const consentKey = `${draft?.intake_id}:${draft?.revision}:${draft?.preview_hash}:${locale}`;
    const button = "ma-press min-h-11 rounded-xl border border-line-strong bg-surface px-3 py-2 text-sm font-medium text-ink hover:bg-surface-2 disabled:opacity-50";
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
            if (!active || !draft) return "unhandled";
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

    return <section className="space-y-3 break-words rounded-2xl border border-line bg-surface-2 p-4" aria-label={copy.title} lang={locale}>
        {intake.busy && <p role="status">{copy.loading}</p>}
        {intake.error && <div role="alert"><p>{intakeErrorCopy(String(intake.error), locale)}</p><button className={button} disabled={intake.busy} onClick={() => void intake.reload()}>{copy.reload}</button></div>}
        {intake.pending && <button className={button} disabled={intake.busy} onClick={intake.retry}>{copy.retry}</button>}
        {(!draft || !active) && !intake.busy && !intake.error && <button className={button} disabled={!sourceMessageId || intake.pending}
            onClick={() => sourceMessageId && void intake.start(sourceMessageId)}>{copy.start}</button>}
        {draft && <>
            <h2 className="text-base font-semibold text-ink">{draft.status === "confirmed" ? copy.saved : draft.status === "cancelled" ? copy.cancelled
                : draft.status === "interrupted_safety" ? copy.interrupted : copy.title}</h2>
            {active && <p className="text-sm text-ink-2">{copy.intro}</p>}
            {draft.existing_draft && active && <p role="status">{copy.existingDraft}</p>}
            {draft.review_requested && <p role="status" className="rounded-xl bg-note-tint p-3 text-note-ink">{copy.urgentReview}</p>}
            {draft.safety && <div role="alert" className="rounded-xl bg-danger-tint p-3 text-danger-ink"><p>{draft.safety.response_text}</p>
                {draft.persistence_status === "uncertain" && <p>{copy.pending}</p>}</div>}
            {active && !draft.library_available && <p role="status">{copy.unavailable}</p>}
            {active && question && <>
                {registerReply ? <>
                    <ChatBubble role="assistant" timestamp="" content={question.wording[locale]} locale={locale} language={locale}
                        onPlayAudio={onReadAloud ? () => onReadAloud(prompt, locale) : undefined} />
                    <p className="text-sm text-ink-2">{copy.answerPrompt}</p>
                    <div className="flex flex-wrap gap-2">
                        <button className={button} disabled={disabled} onClick={() => save("unknown", null)}>{copy.unknown}</button>
                        <button className={button} disabled={disabled} onClick={() => save("declined", null)}>{copy.declined}</button>
                    </div>
                    <details><summary className="min-h-11 cursor-pointer py-2 text-sm font-medium">{copy.detailEntry}</summary>
                        <IntakeAnswerForm key={`${draft.intake_id}:${draft.revision}:${question.id}`} question={question} locale={locale}
                            answer={draft.answers[question.id]} disabled={disabled} save={save} />
                    </details>
                </> : <IntakeAnswerForm key={`${draft.intake_id}:${draft.revision}:${question.id}`} question={question} locale={locale}
                    answer={draft.answers[question.id]} disabled={disabled} save={save} />}
                {suggestion !== undefined && !(question.id in draft.answers) && <div className="rounded-xl border border-line bg-surface p-3">
                    <p className="text-xs font-semibold text-muted">{copy.suggestion}</p><p className="whitespace-pre-wrap">{suggestion}</p>
                    <button className={button} disabled={disabled} onClick={() => save("answered", suggestion, String(suggestion))}>{copy.useSuggestion}</button>
                </div>}
            </>}
            {active && unsaved?.intakeId === draft.intake_id && unsaved.questionId === question?.id && unsaved.revision === draft.revision && <div className="rounded-xl border border-line p-3">
                <p className="text-xs text-muted">{copy.pendingAnswer}</p><p>{unsaved.text}</p>
                {intake.error && !intake.pending && <button className={button} onClick={() => onRestoreInput?.(unsaved.text)}>{copy.editReply}</button>}
            </div>}
            {active && <details><summary className="min-h-11 cursor-pointer py-2 font-medium">{copy.reported}</summary>
                <p className="text-xs text-muted">{copy.timezone}: {draft.timezone}{draft.timezone_fallback ? ` (${copy.fallback})` : ""}</p>
                <dl className="space-y-3">{Object.entries(draft.answers).map(([id, answer]) => <div key={id}>
                    <dt className="text-sm font-medium">{draft.questions?.find((q) => q.id === id)?.wording[locale] ?? copy.value}</dt>
                    <dd className="text-sm" lang={answer.locale}>{answer.state === "answered" ? intakeValueCopy(answer.value, locale) : copy.states[answer.state]}</dd>
                    <button className={button} disabled={disabled} onClick={() => { setEditing(id); setConsent(null); }}>{copy.edit}</button>
                </div>)}</dl></details>}
            {active && <div className="flex flex-wrap gap-2">
                <button className={button} disabled={disabled || Boolean(editing) || !draft.can_review} onClick={() => { setConsent(null); intake.mutate("preview", {}); }}>{copy.review}</button>
                <button className={button} disabled={intake.busy || intake.pending} onClick={() => intake.mutate("cancel", { mutation_id: crypto.randomUUID() })}>{copy.cancel}</button>
            </div>}
            {hint && <p role="status">{copy.reviewFirst}</p>}
            {active && draft.preview && <section className="space-y-3 rounded-xl border border-line bg-surface p-3">
                <h3 className="font-semibold">{copy.summary}</h3><p className="whitespace-pre-line" lang={draft.locale}>{draft.preview.summary}</p>
                {onReadAloud && <button className={button} onClick={() => onReadAloud(prompt, locale)}>{copy.listen}</button>}
                <p className="text-sm text-ink-2">{copy.productReported}</p>
                <h3 className="font-semibold">{copy.context}</h3>
                {!draft.preview.context.medications.length && !draft.preview.context.facts.length && <p>{copy.emptyContext}</p>}
                {draft.preview.context.medications.map((med, i) => <p key={i}>{String(med.name)} · {String(med.dose ?? "")} · {String(med.frequency ?? "")}</p>)}
                {draft.preview.context.facts.map((fact, i) => <p key={i}>{String(fact.fact_type).replaceAll("_", " ")}: {recordValue(fact.value)} <cite className="text-xs text-muted">({typeof fact.document_id === "string"
                    ? <Link className="underline" href={buildRecordsDocumentHref(fact.document_id)}>{copy.recordSource} {i + 1}</Link> : <>{copy.recordSource} {i + 1}</>})</cite></p>)}
                {draft.preview.context.excerpts.map((excerpt, i) => <blockquote className="border-l-2 border-brand pl-3" key={i}>{String(excerpt.text)} <cite className="text-xs text-muted">{typeof excerpt.document_id === "string"
                    ? <Link className="underline" href={buildRecordsDocumentHref(excerpt.document_id)}>{copy.excerptSource} {i + 1}</Link> : <>{copy.excerptSource} {i + 1}</>}</cite></blockquote>)}
                <label className="flex min-h-11 items-start gap-2"><input className="mt-1 h-5 w-5" type="checkbox" checked={consent === consentKey} disabled={disabled || Boolean(editing)}
                    onChange={(e) => setConsent(e.target.checked ? consentKey : null)} />{copy.consent}</label>
                <Button fullWidth disabled={disabled || Boolean(editing) || !draft.can_confirm || consent !== consentKey}
                    onClick={() => intake.mutate("confirm", { confirmation_id: crypto.randomUUID(), preview_hash: draft.preview_hash, consent: true })}>{copy.confirm}</Button>
            </section>}
        </>}
    </section>;
}
