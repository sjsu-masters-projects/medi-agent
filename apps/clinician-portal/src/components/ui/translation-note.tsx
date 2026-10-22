"use client";

import { useId, useState, type ReactNode } from "react";
import { Icon } from "./icons";
import { Popover } from "./popover";

/**
 * LOC-003: how the clinician portal marks machine-translated text.
 *
 * Three rules this file exists to keep in one place:
 *
 * 1. Translated text always says so, and always offers the model's own caveat. The sparkle
 *    chip means "AI produced this" and is never the approval seal.
 * 2. The original is always reachable. A translation is a reading aid; the Spanish a patient
 *    was shown, or a document printed, is the record.
 * 3. Text that was NOT translated says that too, rather than quietly appearing in Spanish
 *    where the clinician expects English.
 */

const CHIP =
    "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium align-middle";

/** Human-readable model name. The stored id is shown as-is: it is the audit value. */
function modelLabel(modelId?: string | null): string {
    const id = (modelId ?? "").trim();
    if (!id) return "The model that produced it was not recorded.";
    if (id === "offline-translation-stub") {
        return "Produced by the offline translation stub, not a model. Test environments only — never approve this as patient-facing wording.";
    }
    return `Produced by ${id}.`;
}

/**
 * "Translated from <language>" with an info button carrying the model and its caveat.
 *
 * `direction` names what was translated into what, in the clinician's own terms: a fact or
 * message that arrived in Spanish is "Translated from Spanish"; wording a patient will
 * receive in Spanish is "Translated from English".
 */
export function TranslationBadge({
    from = "Spanish",
    modelId,
    detail,
    className = "",
}: {
    from?: "Spanish" | "English";
    modelId?: string | null;
    detail?: ReactNode;
    className?: string;
}) {
    return (
        <span className={`inline-flex items-center gap-1 align-middle ${className}`}>
            <span className={`${CHIP} bg-ai-tint text-ai-ink`}>
                <Icon name="spark" aria-hidden="true" className="h-3 w-3" />
                Translated from {from}
            </span>
            <TranslationInfo modelId={modelId} detail={detail} />
        </span>
    );
}

/** The "may contain errors" affordance. Opens on tap or keyboard, never hover alone. */
export function TranslationInfo({
    modelId,
    detail,
}: {
    modelId?: string | null;
    detail?: ReactNode;
}) {
    return (
        <Popover
            align="end"
            className="inline-flex"
            label="About this translation"
            trigger={(props) => (
                <button
                    {...props}
                    className="ma-press inline-flex h-5 w-5 items-center justify-center rounded-full text-muted hover:bg-sunken hover:text-ink-2"
                    type="button"
                >
                    <Icon name="info" aria-hidden="true" className="h-3.5 w-3.5" />
                    <span className="sr-only">About this translation — it may contain errors</span>
                </button>
            )}
        >
            <p className="font-semibold text-ink">This translation is automatic and may contain errors.</p>
            <p className="mt-1.5">{modelLabel(modelId)}</p>
            <p className="mt-1.5">
                Numbers, doses and medication names are checked against the original and must
                match, but meaning is not guaranteed. The original text is the record, and
                safety checks never read a translation.
            </p>
            {detail ? <div className="mt-1.5">{detail}</div> : null}
        </Popover>
    );
}

/** Says a Spanish item was deliberately left in Spanish, and why (LOC-003 item 6). */
export function UntranslatedBadge({
    reason = "The automatic translation did not pass its safety check, so the original Spanish is shown.",
    className = "",
}: {
    reason?: string;
    className?: string;
}) {
    return (
        <span className={`inline-flex items-center gap-1 align-middle ${className}`}>
            <span className={`${CHIP} border border-warn-line bg-warn-soft text-warn-ink`}>
                <Icon name="alert" aria-hidden="true" className="h-3 w-3" />
                Not translated
            </span>
            <Popover
                align="end"
                className="inline-flex"
                label="Why this was not translated"
                trigger={(props) => (
                    <button
                        {...props}
                        className="ma-press inline-flex h-5 w-5 items-center justify-center rounded-full text-muted hover:bg-sunken hover:text-ink-2"
                        type="button"
                    >
                        <Icon name="info" aria-hidden="true" className="h-3.5 w-3.5" />
                        <span className="sr-only">Why this was not translated</span>
                    </button>
                )}
            >
                <p className="font-semibold text-ink">Shown in the original Spanish.</p>
                <p className="mt-1.5">{reason}</p>
                <p className="mt-1.5">
                    Read it with the source document, or ask a bilingual colleague, before you
                    approve anything that depends on it.
                </p>
            </Popover>
        </span>
    );
}

/**
 * "Show original" / "Hide original": the original one tap away, under the English.
 *
 * `lang` is set on the original so a screen reader pronounces Spanish as Spanish.
 */
export function OriginalText({
    children,
    label = "original Spanish",
    lang = "es-MX",
    className = "",
}: {
    children: ReactNode;
    label?: string;
    lang?: string;
    className?: string;
}) {
    const [open, setOpen] = useState(false);
    const regionId = useId();
    return (
        <span className={`block ${className}`}>
            <button
                aria-controls={regionId}
                aria-expanded={open}
                className="ma-press inline-flex min-h-6 items-center gap-1 rounded-md text-[11px] font-semibold text-primary underline-offset-2 hover:underline"
                onClick={() => setOpen((value) => !value)}
                type="button"
            >
                <Icon name="eye" aria-hidden="true" className="h-3 w-3" />
                {open ? `Hide ${label}` : `Show ${label}`}
            </button>
            <span
                className="mt-1 block border-l-2 border-line-strong pl-2.5 text-[13px] leading-relaxed text-ink-2"
                hidden={!open}
                id={regionId}
                lang={lang}
            >
                {children}
            </span>
        </span>
    );
}
