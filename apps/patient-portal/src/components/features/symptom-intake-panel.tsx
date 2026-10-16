"use client";

import { useState } from "react";
import { getSymptomIntakeCopy, intakeErrorCopy, intakeValueCopy } from "@/content/symptom-intake-copy";
import { useSymptomIntake } from "@/hooks/use-symptom-intake";
import { IntakeAnswerForm } from "@/components/features/intake-answer-form";
import type { Locale } from "@/types";

export function SymptomIntakePanel({ locale, sourceMessageId, sessionId = "default" }: { locale: Locale; sourceMessageId?: string; sessionId?: string }) {
    const intake = useSymptomIntake(sessionId);
    const copy = getSymptomIntakeCopy(locale);
    const [editing, setEditing] = useState<string | null>(null);
    const [consent, setConsent] = useState<string | null>(null);
    const button = "min-h-11 rounded-lg border border-gray-300 px-3 py-2 text-sm disabled:opacity-50";
    const draft = intake.draft;
    const consentKey = `${draft?.intake_id}:${draft?.revision}:${draft?.preview_hash}:${locale}`;
    const active = draft && ["collecting", "ready_for_confirmation"].includes(draft.status);
    const question = editing ? draft?.questions?.find((q) => q.id === editing) : draft?.current_question;
    const disabled = intake.busy || intake.pending || !draft?.library_available;
    return <section className="space-y-3 break-words rounded-xl border border-gray-200 bg-white p-5 shadow-sm" aria-label={copy.title} lang={locale}>
        {intake.busy && <p role="status">{copy.loading}</p>}
        {intake.error && <div role="alert"><p>{intakeErrorCopy(String(intake.error), locale)}</p><button className={button} disabled={intake.busy} onClick={() => void intake.reload()}>{copy.reload}</button></div>}
        {intake.pending && <button className={button} disabled={intake.busy} onClick={intake.retry}>{copy.retry}</button>}
        {(!draft || !active) && !intake.busy && !intake.error && <button className={button} disabled={!sourceMessageId || intake.pending}
            onClick={() => sourceMessageId && void intake.start(sourceMessageId)}>{copy.start}</button>}
        {draft && <>
            <h2 className="text-lg font-semibold">{draft.status === "confirmed" ? copy.saved : draft.status === "cancelled" ? copy.cancelled
                : draft.status === "interrupted_safety" ? copy.interrupted : copy.title}</h2>
            {active && <p className="text-sm text-gray-500">{copy.intro}</p>}
            {draft.safety && <div role="alert" className="rounded-lg bg-red-100 p-3 text-red-800"><p>{draft.safety.response_text}</p>
                {draft.persistence_status === "uncertain" && <p>{copy.pending}</p>}</div>}
            {draft.confirmed_report_id && <p role="status">{copy.saved}: {draft.confirmed_report_id}</p>}
            <p className="text-xs text-gray-500">{copy.timezone}: {draft.timezone}{draft.timezone_fallback ? ` (${copy.fallback})` : ""}</p>
            {active && !draft.library_available && <p role="status">{copy.unavailable}</p>}
            {active && draft.progress && <p role="status">{copy.progress}: {draft.progress.resolved}/{draft.progress.budget}</p>}
            {active && question && <IntakeAnswerForm key={`${draft.intake_id}:${draft.revision}:${question.id}`} question={question} locale={locale}
                answer={draft.answers[question.id]} disabled={disabled} save={(state, value, wording) => {
                    intake.mutate("answers", { mutation_id: crypto.randomUUID(), question_id: question.id, state, value, wording, locale });
                    setEditing(null); setConsent(null);
                }} />}
            {active && <details><summary className="cursor-pointer font-medium">{copy.reported}</summary>
                <dl className="mt-3 space-y-3">{Object.entries(draft.answers).map(([id, answer]) => <div key={id}>
                    <dt className="text-sm font-medium">{draft.questions?.find((q) => q.id === id)?.wording[locale] ?? id}</dt>
                    <dd className="text-sm" lang={answer.locale}>{answer.state === "answered" ? intakeValueCopy(answer.value, locale) : copy.states[answer.state]}</dd>
                    <button className={button} disabled={disabled} onClick={() => { setEditing(id); setConsent(null); }}>{copy.edit}</button>
                </div>)}</dl></details>}
            {active && <div className="flex flex-wrap gap-2">
                <button className={button} disabled={disabled || !draft.can_review} onClick={() => { setConsent(null); intake.mutate("preview", {}); }}>{copy.review}</button>
                <button className={button} disabled={intake.busy || intake.pending} onClick={() => intake.mutate("cancel", { mutation_id: crypto.randomUUID() })}>{copy.cancel}</button>
            </div>}
            {active && draft.preview && <section className="space-y-3 rounded-lg border border-gray-200 p-3">
                <h3 className="font-semibold">{copy.reported}</h3>
                <dl>{Object.entries(draft.preview.answers).map(([id, answer]) => <div key={id} className="mb-2">
                    <dt>{draft.questions?.find((q) => q.id === id)?.wording[locale] ?? id}</dt>
                    <dd lang={answer.locale}>{answer.state === "answered" ? intakeValueCopy(answer.value, locale) : copy.states[answer.state]}</dd>
                </div>)}</dl>
                {Object.entries(draft.preview.selection ?? {}).map(([id, selection]) => <p key={id}>
                    {draft.questions?.find((q) => q.id === id)?.wording[locale] ?? id}: {copy.states[selection.state]}</p>)}
                <h3 className="font-semibold">{copy.context}</h3>
                {!draft.preview.context.medications.length && !draft.preview.context.facts.length && <p>{copy.emptyContext}</p>}
                {draft.preview.context.medications.map((med, i) => <p key={i}>{String(med.name)} · {String(med.dose ?? "")} · {String(med.frequency ?? "")} · {String(med.source_id)}</p>)}
                {draft.preview.context.facts.map((fact, i) => <p key={i}>{String(fact.fact_type)}: {JSON.stringify(fact.value)} · {String(fact.source_id)} · {String(fact.approval_state)}</p>)}
                {draft.preview.context.excerpts.map((excerpt, i) => <blockquote key={i}>{String(excerpt.text)} <cite>{String(excerpt.document_id ?? excerpt.source_reference)} · {JSON.stringify(excerpt.location)}</cite></blockquote>)}
                <h3 className="font-semibold">{copy.summary}</h3><p className="whitespace-pre-line" lang={draft.locale}>{draft.preview.summary}</p>
                <label className="flex items-start gap-2"><input type="checkbox" checked={consent === consentKey} disabled={disabled}
                    onChange={(e) => setConsent(e.target.checked ? consentKey : null)} />{copy.consent}</label>
                <button className={button + " bg-blue-600 text-white"} disabled={disabled || !draft.can_confirm || consent !== consentKey}
                    onClick={() => intake.mutate("confirm", { confirmation_id: crypto.randomUUID(), preview_hash: draft.preview_hash, consent: true })}>{copy.confirm}</button>
            </section>}
        </>}
    </section>;
}
