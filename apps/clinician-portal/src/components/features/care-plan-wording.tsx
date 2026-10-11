"use client";

import { Icon } from "@/components/ui/icons";
import type { CarePlanItem, CarePlanLocale, CarePlanWording, CarePlanWordingOrigin } from "@/services/clinicians";

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

interface BilingualWordingProps {
    item: CarePlanItem;
    patientLocale: string;
    fieldClass: string;
    busy: boolean;
    unsaved: boolean;
    onChange: (locale: CarePlanLocale, field: keyof CarePlanWording, value: string) => void;
    onTranslate: (fromLocale: CarePlanLocale) => void;
    onWriteManually: (sourceLocale: CarePlanLocale) => void;
}

/**
 * Side-by-side English and Spanish wording for one draft item. The source column is
 * the wording the evidence was written in; the other is an AI draft the clinician checks
 * or rewrites. The patient sees whichever language they choose, so both are reviewed.
 */
export function BilingualWording({ item, patientLocale, fieldClass, busy, unsaved, onChange, onTranslate, onWriteManually }: BilingualWordingProps) {
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
    const target = otherLocale(source);
    const columns: CarePlanLocale[] = [source, target];
    return <div className="grid gap-3 lg:grid-cols-2">
        {columns.map((locale) => {
            const text = item.wording?.[locale] ?? { title: "", instructions: "", frequency: "" };
            const isSource = locale === source;
            return <fieldset key={locale} className={`min-w-0 space-y-3 rounded-xl border p-3.5 ${isSource ? "border-line bg-surface-2/60" : "border-primary-line bg-ai-tint/30"}`}>
                <legend className="sr-only">{LOCALE_LABEL[locale]} wording</legend>
                <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="flex items-center gap-2 text-[13px] font-semibold text-ink">{LOCALE_LABEL[locale]}{locale === patientLocale ? <span className="rounded-md bg-ok-soft px-1.5 py-0.5 text-[11px] font-medium text-ok-ink">Patient&apos;s language</span> : null}</p>
                    <OriginBadge origin={item.wording_origin?.[locale] ?? (isSource ? "source" : undefined)} />
                </div>
                <label className="block text-xs font-semibold text-ink-2">Title<input className={fieldClass} lang={locale} value={text.title} onChange={(event) => onChange(locale, "title", event.target.value)} /></label>
                <label className="block text-xs font-semibold text-ink-2">Instructions<textarea rows={3} className={`${fieldClass} text-[15px] leading-relaxed`} lang={locale} value={text.instructions} onChange={(event) => onChange(locale, "instructions", event.target.value)} /></label>
                <label className="block text-xs font-semibold text-ink-2">Frequency<input className={fieldClass} lang={locale} value={text.frequency} onChange={(event) => onChange(locale, "frequency", event.target.value)} /></label>
                {!isSource ? <div className="flex flex-wrap items-center gap-2">
                    <button className="ma-press inline-flex h-8 items-center gap-1.5 rounded-lg border border-primary-line bg-surface px-2.5 text-[13px] font-semibold text-ai-ink hover:bg-ai-tint disabled:cursor-not-allowed disabled:opacity-50" disabled={busy || unsaved} onClick={() => onTranslate(source)} type="button"><Icon name="refresh" className="h-3.5 w-3.5" />Re-translate from {LOCALE_LABEL[source]}</button>
                    {unsaved ? <span className="text-xs text-muted">Save first to re-translate.</span> : null}
                </div> : null}
            </fieldset>;
        })}
    </div>;
}

/** Read-only approved wording in both languages, or the single stored language. */
export function ApprovedWording({ item }: { item: CarePlanItem }) {
    const locales = CARE_PLAN_LOCALES.filter((locale) => item.wording?.[locale]?.title);
    if (!locales.length) return <p className="rounded-xl border border-line bg-surface-2 p-3.5 text-[15px] leading-relaxed text-ink">{item.instructions} · {item.frequency}<span className="mt-1 block text-xs text-muted">Approved in one language before bilingual review.</span></p>;
    return <div className="grid gap-3 lg:grid-cols-2">{locales.map((locale) => <div key={locale} className="rounded-xl border border-line bg-surface-2 p-3.5" lang={locale}>
        <p className="text-[11px] font-mono uppercase tracking-[0.06em] text-muted">{LOCALE_LABEL[locale]}</p>
        <p className="mt-1 text-[15px] leading-relaxed text-ink">{item.wording?.[locale]?.instructions} · {item.wording?.[locale]?.frequency}</p>
    </div>)}</div>;
}
