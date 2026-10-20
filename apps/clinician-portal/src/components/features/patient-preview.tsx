"use client";

import { Icon } from "@/components/ui/icons";
import { TranslationBadge } from "@/components/ui/translation-note";
import type { CarePlanLocale, CarePlanWording } from "@/services/clinicians";

/**
 * LOC-003: a phone-shaped preview of the wording a patient will actually read.
 *
 * The clinician reviews English, but the patient reads their own language on a phone. A
 * side-by-side pair of text boxes does not show how long Spanish wrapping, a long medication
 * title or an empty frequency will land on the patient's Today. This frame does.
 *
 * Everything inside it comes from the item's stored wording. The only text this component
 * supplies is the patient-app chrome around it — the category chip and the completion button
 * — in the already-approved patient wording for that locale, so the frame reads like the
 * screen it stands for rather than like a mock with invented content.
 */

/** Chrome labels taken from the patient app's approved Today copy, not newly drafted. */
const CHROME: Record<CarePlanLocale, { done: string; today: string; category: string }> = {
    "en-US": { done: "Mark as Done", today: "Today", category: "Care" },
    "es-MX": { done: "Marcar como completada", today: "Hoy", category: "Atención" },
};

const LOCALE_NAME: Record<CarePlanLocale, string> = {
    "en-US": "English (US)",
    "es-MX": "Español (México)",
};

export function PatientPhonePreview({
    locale,
    wording,
    translated = false,
    modelId,
    className = "",
}: {
    /** The patient's own language: what this preview claims to show. */
    locale: CarePlanLocale;
    wording: Partial<CarePlanWording> | undefined;
    /** True when this language is a translation rather than the source wording. */
    translated?: boolean;
    modelId?: string | null;
    className?: string;
}) {
    const chrome = CHROME[locale];
    const title = (wording?.title ?? "").trim();
    const instructions = (wording?.instructions ?? "").trim();
    const frequency = (wording?.frequency ?? "").trim();

    if (!title && !instructions) {
        return (
            <p className={`rounded-xl border border-dashed border-line-strong bg-sunken px-3 py-4 text-center text-xs text-muted ${className}`}>
                Write the {LOCALE_NAME[locale]} wording to preview the patient&apos;s Today.
            </p>
        );
    }

    return (
        <figure className={`m-0 ${className}`}>
            <figcaption className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted">
                <span className="flex items-center gap-1 font-semibold text-ink-2">
                    <Icon name="phone" aria-hidden="true" className="h-3.5 w-3.5" />
                    What the patient sees
                </span>
                <span>· {LOCALE_NAME[locale]}</span>
                {translated ? <TranslationBadge from="English" modelId={modelId} /> : null}
            </figcaption>
            {/* A static frame: no motion, no 3D transform, and it never scales the text. */}
            <div className="mx-auto w-full max-w-[300px] rounded-[26px] border border-line-strong bg-[#17233a] p-[6px] shadow-[var(--shadow-page)]">
                <div className="overflow-hidden rounded-[21px] bg-[#faf7f2]">
                    {/* Patient-app status strip: a pill for the camera cutout and the screen name. */}
                    <div className="flex items-center justify-between px-4 pb-1.5 pt-2.5">
                        <span className="text-[13px] font-bold text-[#17233a]" lang={locale}>
                            {chrome.today}
                        </span>
                        <span aria-hidden="true" className="h-1.5 w-10 rounded-full bg-[#d9d2c7]" />
                    </div>
                    <div className="px-2.5 pb-3">
                        <div className="space-y-3 rounded-2xl border border-[#e7e0d4] bg-white p-3.5">
                            <div className="flex flex-wrap items-start justify-between gap-2">
                                <div className="min-w-0 flex-1 basis-32 space-y-1 break-words" lang={locale}>
                                    <p className="text-[15px] font-bold leading-snug text-[#17233a]">{title}</p>
                                    {instructions && instructions !== title ? (
                                        <p className="text-[13px] leading-6 text-[#5b6b83]">{instructions}</p>
                                    ) : null}
                                    {frequency ? <p className="text-xs text-[#5b6b83]">{frequency}</p> : null}
                                </div>
                                <span
                                    className="shrink-0 rounded-full bg-[#f4f0ea] px-2 py-0.5 text-[9px] font-black uppercase tracking-[0.16em] text-[#5b6b83]"
                                    lang={locale}
                                >
                                    {chrome.category}
                                </span>
                            </div>
                            {/* Inert on purpose: this is a preview, not a control. */}
                            <p
                                aria-hidden="true"
                                className="rounded-xl bg-[#0f766e] px-3 py-2 text-center text-[13px] font-semibold text-white"
                                lang={locale}
                            >
                                {chrome.done}
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </figure>
    );
}
