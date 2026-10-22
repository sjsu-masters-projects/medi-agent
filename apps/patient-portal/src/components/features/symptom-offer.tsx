"use client";

import { getSymptomIntakeCopy } from "@/content/symptom-intake-copy";
import type { Locale } from "@/types";

type Props = { locale: Locale; busy?: boolean; onYes: () => void; onNo: () => void };

/** A conversational question under Nora's reply. It asks; it never starts anything by itself. */
export function SymptomOffer({ locale, busy = false, onYes, onNo }: Props) {
    const copy = getSymptomIntakeCopy(locale);
    return <div role="group" aria-label={copy.offerPrompt} lang={locale} className="mt-2.5 space-y-2 border-t border-line pt-2.5">
        <p className="text-sm leading-[1.45] text-ink-2">{copy.offerPrompt}</p>
        <div className="flex flex-wrap gap-2">
            <button type="button" disabled={busy} onClick={onYes}
                className="ma-press min-h-11 rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-ink disabled:opacity-60">{copy.offerYes}</button>
            <button type="button" disabled={busy} onClick={onNo}
                className="ma-press min-h-11 rounded-full border border-line-strong bg-surface px-4 py-2 text-sm font-medium text-ink-2 hover:border-brand/40 hover:text-brand-ink disabled:opacity-60">{copy.offerNo}</button>
        </div>
    </div>;
}
