"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Icon } from "@/components/ui/icons";
import type { CarePlanItem, CarePlanLocale, CarePlanWording, CarePlanWordingOrigin } from "@/services/clinicians";
import { fetchBackTranslation, type BackTranslationResult } from "@/services/clinicians";

export const CARE_PLAN_LOCALES: CarePlanLocale[] = ["en-US", "es-MX"];
export const LOCALE_LABEL: Record<CarePlanLocale, string> = { "en-US": "English (US)", "es-MX": "Español (México)" };
const FIELDS = ["title", "instructions", "frequency"] as const;

export function otherLocale(locale: CarePlanLocale): CarePlanLocale {
    return locale === "en-US" ? "es-MX" : "en-US";
}

/** Both languages present, and the source copy matches the fields reconciliation compares. */
export function wordingComplete(item: CarePlanItem): boolean {
    const source = item.source_locale;
    if (!source) return false;
    const wording = item.wording ?? {};
    return CARE_PLAN_LOCALES.every((locale) => FIELDS.every((field) => (wording[locale]?.[field] ?? "").trim())) &&
        FIELDS.every((field) => (wording[source]?.[field] ?? "").trim() === item[field].trim());
}

function OriginBadge({ origin }: { origin?: CarePlanWordingOrigin }) {
    if (origin === "ai_draft") return <span className="inline-flex items-center gap-1 rounded-md bg-ai-tint px-1.5 py-0.5 text-[11px] font-medium text-ai-ink"><Icon name="spark" className="h-3 w-3" />AI translation · check it</span>;
    if (origin === "clinician_edited") return <span className="rounded-md bg-primary-tint px-1.5 py-0.5 text-[11px] font-medium text-primary">Edited by clinician</span>;
    if (origin === "source") return <span className="inline-flex items-center gap-1 rounded-md bg-sunken px-1.5 py-0.5 text-[11px] font-medium text-ink-2"><Icon name="file" className="h-3 w-3" />From source</span>;
    return <span className="rounded-md bg-warn-tint px-1.5 py-0.5 text-[11px] font-medium text-warn-ink">Not written yet</span>;
}

/* ── LOC-003: Language flow strip ─────────────────────────────────────────── */

/** Compact strip showing: Source language → You review → Patient sees. */
function LanguageFlowStrip({ sourceLocale, patientLocale }: { sourceLocale: CarePlanLocale; patientLocale: string }) {
    const sourceLabel = sourceLocale === "es-MX" ? "Spanish document" : "English document";
    const patientLabel = patientLocale === "es-MX" ? "Español (México)" : "English (US)";
    return (
        <div className="flex flex-wrap items-center gap-1.5 rounded-lg bg-sunken px-3 py-2 text-xs text-ink-2">
            <span className="font-medium">Source:</span>
            <span>{sourceLabel}</span>
            <Icon name="arrow" className="h-3 w-3 text-muted" />
            <span className="font-medium">You review:</span>
            <span>English</span>
            <Icon name="arrow" className="h-3 w-3 text-muted" />
            <span className="font-medium">Patient sees:</span>
            <span className="font-semibold text-ink">{patientLabel}</span>
        </div>
    );
}

/** Label shown on each language card: "Shown in patient's Today" or "Stored for language switch". */
function PatientVisibilityLabel({ locale, patientLocale }: { locale: CarePlanLocale; patientLocale: string }) {
    const isPatientLanguage = locale === patientLocale;
    if (isPatientLanguage) {
        return <span className="inline-flex items-center gap-1 rounded-md bg-ok-soft px-1.5 py-0.5 text-[11px] font-medium text-ok-ink"><Icon name="check" className="h-3 w-3" />Shown in patient&apos;s Today</span>;
    }
    return <span className="rounded-md bg-sunken px-1.5 py-0.5 text-[11px] font-medium text-muted">Stored in case patient changes language</span>;
}

/* ── LOC-003: Back-translation panel ──────────────────────────────────────── */

type SpanishWording = { title: string; instructions: string; frequency: string };

/** A stable key for the Spanish wording, so a check is tied to the exact text it covered. */
export function spanishKey(wording?: Partial<SpanishWording> | null): string {
    return JSON.stringify(FIELDS.map((field) => (wording?.[field] ?? "").trim()));
}

/** What the attestation needs to know about the back-translation of an item's SAVED Spanish. */
export interface BackCheck {
    state: "loading" | "error" | "ready";
    /** Numbers and medication names guards both passed. Meaningful only when state is "ready". */
    guardsOk: boolean;
    /** The Spanish wording (see spanishKey) the check covers. */
    key: string;
}

/**
 * Why the "I verified ..." box cannot be ticked yet, or null when it can. The back-translation
 * must be of the SAVED Spanish wording, loaded, with both guards passed, and nothing unsaved.
 */
export function verificationBlocker(item: CarePlanItem, check: BackCheck | undefined, unsaved: boolean): string | null {
    if (!wordingComplete(item)) return "Complete both languages first.";
    if (unsaved) return "Save your changes first";
    if (!check || check.key !== spanishKey(item.wording?.["es-MX"]) || check.state === "loading") return "Back-translation is loading";
    if (check.state === "error") return "Back-translation unavailable — retry";
    if (!check.guardsOk) return "Numbers or medication names differ — fix the Spanish";
    return null;
}

/**
 * Shows an English back-translation of the SAVED Spanish wording plus guard results. The server
 * back-translates what is stored, so this fetches on mount and after a save, never per keystroke;
 * "Check again" repeats it on demand. A slower, older response is ignored.
 */
export function BackTranslationPanel({ patientId, planId, itemId, spanishWording, unsaved = false, onCheck }: {
    patientId?: string; planId?: string; itemId: string;
    spanishWording: SpanishWording; unsaved?: boolean;
    onCheck?: (itemId: string, check: BackCheck) => void;
}) {
    const currentKey = spanishKey(spanishWording);
    // The version the server holds: it follows the visible text only while nothing is unsaved.
    const [savedKey, setSavedKey] = useState(currentKey);
    useEffect(() => { if (!unsaved) setSavedKey(currentKey); }, [unsaved, currentKey]);

    const [result, setResult] = useState<{ key: string; data: BackTranslationResult } | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(false);
    const latest = useRef(0);
    const hasWording = Boolean(spanishWording.title.trim());

    const load = useCallback(async (key: string) => {
        if (!patientId || !planId || !hasWording) return;
        const request = ++latest.current;
        setResult(null);
        setError(false);
        setLoading(true);
        try {
            const data = await fetchBackTranslation(patientId, planId, itemId);
            if (!data?.guards || !data.back_translation) throw new Error("Unexpected back-translation response");
            if (request === latest.current) setResult({ key, data });
        } catch {
            if (request === latest.current) setError(true);
        } finally {
            if (request === latest.current) setLoading(false);
        }
    }, [patientId, planId, itemId, hasWording]);

    useEffect(() => {
        void load(savedKey);
        return () => { latest.current += 1; };
    }, [load, savedKey]);

    const state: BackCheck["state"] = error ? "error" : result && result.key === savedKey ? "ready" : "loading";
    const guardsOk = Boolean(result?.data.guards.numbers_match && result.data.guards.medication_names_match);
    useEffect(() => {
        if (hasWording) onCheck?.(itemId, { state, guardsOk, key: savedKey });
    }, [hasWording, itemId, state, guardsOk, savedKey, onCheck]);

    if (!hasWording) return null;
    const data = result?.data;
    return (
        <div className="mt-3 space-y-2 rounded-lg border border-line bg-surface p-3">
            <div className="flex items-center justify-between gap-2">
                <p className="flex items-center gap-1.5 text-xs font-semibold text-ink-2">
                    <Icon name="spark" className="h-3 w-3 text-ai-ink" />
                    English back-translation
                </p>
                <button className="ma-press h-7 rounded-md px-2 text-[11px] font-semibold text-primary hover:bg-primary-tint disabled:cursor-not-allowed disabled:opacity-50" disabled={loading} onClick={() => void load(savedKey)} type="button">Check again</button>
            </div>
            <div aria-live="polite" role="status" className="space-y-2">
                {loading ? <p className="text-xs text-muted">Loading back-translation…</p> : null}
                {error ? <p className="flex flex-wrap items-center gap-2 text-xs text-warn-ink">Back-translation unavailable right now.
                    <button className="font-semibold underline underline-offset-2" onClick={() => void load(savedKey)} type="button">Retry</button></p> : null}
                {data ? <>
                    <p className="flex flex-wrap items-center gap-x-3 text-[11px]">
                        {data.guards.numbers_match ? <span className="text-ok-ink">✓ Numbers match</span> : <span className="text-risk-ink">✗ Numbers differ</span>}
                        {data.guards.medication_names_match ? <span className="text-ok-ink">✓ Med names match</span> : <span className="text-risk-ink">✗ Med names differ</span>}
                    </p>
                    <div className="space-y-1 text-sm text-ink-2" lang="en-US">
                        <p><span className="text-xs font-medium text-muted">Title:</span> {data.back_translation.title}</p>
                        <p><span className="text-xs font-medium text-muted">Instructions:</span> {data.back_translation.instructions}</p>
                        <p><span className="text-xs font-medium text-muted">Frequency:</span> {data.back_translation.frequency}</p>
                    </div>
                </> : null}
                {unsaved ? <p className="text-[11px] font-medium text-warn-ink">Translation shown is for the saved version. Save your changes to check the new Spanish.</p> : null}
            </div>
            <p className="text-[11px] text-muted">Compare this with the English wording above. If they match, the Spanish is faithful.</p>
        </div>
    );
}

/* ── Wording components ───────────────────────────────────────────────────── */

interface BilingualWordingProps {
    item: CarePlanItem;
    patientLocale: string;
    fieldClass: string;
    busy: boolean;
    unsaved: boolean;
    patientId?: string;
    planId?: string;
    onBackCheck?: (itemId: string, check: BackCheck) => void;
    onChange: (locale: CarePlanLocale, field: keyof CarePlanWording, value: string) => void;
    onTranslate: (fromLocale: CarePlanLocale) => void;
    onWriteManually: (sourceLocale: CarePlanLocale) => void;
}

/**
 * Side-by-side English and Spanish wording for one draft item. The source column is
 * the wording the evidence was written in; the other is an AI draft the clinician checks
 * or rewrites. The patient sees whichever language they choose, so both are reviewed.
 */
export function BilingualWording({ item, patientLocale, fieldClass, busy, unsaved, patientId, planId, onBackCheck, onChange, onTranslate, onWriteManually }: BilingualWordingProps) {
    const source = item.source_locale ?? null;
    if (!source) {
        return <div className="space-y-3 rounded-xl border border-warn-line bg-warn-soft/60 p-3.5">
            <p className="flex items-start gap-2 text-sm text-warn-ink"><Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />This item has wording in one language only. Patients can switch language at any time, so it needs both before approval.</p>
            <div className="grid gap-3 md:grid-cols-2">
                <label className="text-xs font-semibold text-ink-2 md:col-span-2">Title<input className={fieldClass} value={item.title} onChange={(event) => onChange("en-US", "title", event.target.value)} /></label>
                <label className="text-xs font-semibold text-ink-2 md:col-span-2">Instructions<textarea rows={3} className={`${fieldClass} text-[15px] leading-relaxed`} value={item.instructions} onChange={(event) => onChange("en-US", "instructions", event.target.value)} /></label>
                <label className="text-xs font-semibold text-ink-2">Frequency<input className={fieldClass} value={item.frequency} onChange={(event) => onChange("en-US", "frequency", event.target.value)} /></label>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-[13px]">
                <span className="text-ink-2">This wording is in</span>
                {CARE_PLAN_LOCALES.map((locale) => <button key={locale} className="ma-press inline-flex h-8 items-center gap-1.5 rounded-lg border border-primary-line bg-surface px-2.5 font-semibold text-primary hover:bg-primary-tint disabled:cursor-not-allowed disabled:opacity-50" disabled={busy || unsaved} onClick={() => onTranslate(locale)} type="button"><Icon name="spark" className="h-3.5 w-3.5" />{LOCALE_LABEL[locale]} · draft {LOCALE_LABEL[otherLocale(locale)]}</button>)}
                <button className="ma-press h-8 rounded-lg px-2 font-medium text-ink-2 underline-offset-2 hover:underline disabled:opacity-50" disabled={busy} onClick={() => onWriteManually(patientLocale === "es-MX" ? "es-MX" : "en-US")} type="button">Write both myself</button>
            </div>
            {unsaved ? <p className="text-xs text-muted">Save your edits first; the translation is drafted from the saved wording.</p> : null}
        </div>;
    }
    /* LOC-003: always show English first so the clinician reads their language first. */
    const columns: CarePlanLocale[] = ["en-US", "es-MX"];
    return <div className="space-y-3">
        {/* LOC-003: Language flow strip */}
        <LanguageFlowStrip sourceLocale={source} patientLocale={patientLocale} />
        <div className="@container"><div className="grid gap-3 @xl:grid-cols-2">
            {columns.map((locale) => {
                const text = item.wording?.[locale] ?? { title: "", instructions: "", frequency: "" };
                const isSource = locale === source;
                const isSpanish = locale === "es-MX";
                return <fieldset key={locale} className={`min-w-0 space-y-3 rounded-xl border p-3.5 ${isSource ? "border-line bg-surface-2/60" : "border-primary-line bg-ai-tint/30"}`}>
                    <legend className="sr-only">{LOCALE_LABEL[locale]} wording</legend>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="flex items-center gap-2 text-[13px] font-semibold text-ink">
                            {LOCALE_LABEL[locale]}
                            <PatientVisibilityLabel locale={locale} patientLocale={patientLocale} />
                        </p>
                        <OriginBadge origin={item.wording_origin?.[locale] ?? (isSource ? "source" : undefined)} />
                    </div>
                    <label className="block text-xs font-semibold text-ink-2">Title<input className={fieldClass} lang={locale} value={text.title} onChange={(event) => onChange(locale, "title", event.target.value)} /></label>
                    <label className="block text-xs font-semibold text-ink-2">Instructions<textarea rows={3} className={`${fieldClass} text-[15px] leading-relaxed`} lang={locale} value={text.instructions} onChange={(event) => onChange(locale, "instructions", event.target.value)} /></label>
                    <label className="block text-xs font-semibold text-ink-2">Frequency<input className={fieldClass} lang={locale} value={text.frequency} onChange={(event) => onChange(locale, "frequency", event.target.value)} /></label>
                    {!isSource ? <div className="flex flex-wrap items-center gap-2">
                        <button className="ma-press inline-flex h-8 items-center gap-1.5 rounded-lg border border-primary-line bg-surface px-2.5 text-[13px] font-semibold text-ai-ink hover:bg-ai-tint disabled:cursor-not-allowed disabled:opacity-50" disabled={busy || unsaved} onClick={() => onTranslate(source)} type="button"><Icon name="refresh" className="h-3.5 w-3.5" />Re-translate from {LOCALE_LABEL[source]}</button>
                        {unsaved ? <span className="text-xs text-muted">Save first to re-translate.</span> : null}
                    </div> : null}
                    {/* LOC-003: Back-translation panel on the Spanish card */}
                    {isSpanish && text.title.trim() ? <BackTranslationPanel patientId={patientId} planId={planId} itemId={item.id} spanishWording={text} unsaved={unsaved} onCheck={onBackCheck} /> : null}
                </fieldset>;
            })}
        </div></div>
    </div>;
}

/** Read-only approved wording in both languages, or the single stored language. */
export function ApprovedWording({ item, patientLocale }: { item: CarePlanItem; patientLocale?: string }) {
    const locales = CARE_PLAN_LOCALES.filter((locale) => item.wording?.[locale]?.title);
    if (!locales.length) return <p className="rounded-xl border border-line bg-surface-2 p-3.5 text-[15px] leading-relaxed text-ink">{item.instructions} · {item.frequency}<span className="mt-1 block text-xs text-muted">Approved in one language before bilingual review.</span></p>;
    return <div className="space-y-3">
        {/* LOC-003: Show the language flow strip on approved items too */}
        {item.source_locale && patientLocale ? <LanguageFlowStrip sourceLocale={item.source_locale} patientLocale={patientLocale} /> : null}
        <div className="@container"><div className="grid gap-3 @xl:grid-cols-2">{locales.map((locale) => <div key={locale} className="rounded-xl border border-line bg-surface-2 p-3.5" lang={locale}>
            <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[11px] font-mono uppercase tracking-[.06em] text-muted">{LOCALE_LABEL[locale]}</p>
                {patientLocale ? <PatientVisibilityLabel locale={locale} patientLocale={patientLocale} /> : null}
            </div>
            <p className="mt-1 text-[15px] leading-relaxed text-ink">{item.wording?.[locale]?.instructions} · {item.wording?.[locale]?.frequency}</p>
        </div>)}</div></div>
    </div>;
}
