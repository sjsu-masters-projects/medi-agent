"use client";

import { useState } from "react";
import { Icon } from "@/components/ui/icons";
import { Modal } from "@/components/ui/modal";

/**
 * LOC-003 item 5, patient side: what a patient is told about a machine translation.
 *
 * A patient reading their clinician's reply in Spanish is reading a translation. They are
 * entitled to know that a computer made it, that it may be wrong, which model made it, and
 * that their care team works from the original — so a translation is never mistaken for
 * what their clinician actually wrote.
 *
 * It opens as a bottom sheet rather than a hover tooltip: help has to work on tap, and the
 * trigger keeps a 44px touch area even though the icon is small.
 */

interface TranslationNoteCopy {
    aboutTranslation: string;
    aboutTranslationTitle: string;
    translationMayErr: string;
    translationModel: (model: string) => string;
    translationModelUnknown: string;
    translationOriginalIsRecord: string;
    translationGuards: string;
    translationAsk: string;
    close: string;
}

export function TranslationNote({
    copy,
    modelId,
}: {
    copy: TranslationNoteCopy;
    modelId?: string | null;
}) {
    const [open, setOpen] = useState(false);
    const model = (modelId ?? "").trim();
    return (
        <>
            <button
                aria-haspopup="dialog"
                aria-label={copy.aboutTranslation}
                className="relative inline-flex h-5 w-5 items-center justify-center rounded-full align-middle text-muted hover:text-ink after:absolute after:left-1/2 after:top-1/2 after:h-11 after:w-11 after:-translate-x-1/2 after:-translate-y-1/2 after:content-['']"
                onClick={() => setOpen(true)}
                type="button"
            >
                <Icon aria-hidden="true" className="h-3.5 w-3.5" name="info" />
            </button>
            <Modal
                closeLabel={copy.close}
                onClose={() => setOpen(false)}
                open={open}
                title={copy.aboutTranslationTitle}
            >
                <div className="space-y-3 text-[15px] leading-[1.5] text-ink">
                    <p>{copy.translationMayErr}</p>
                    <p>{model ? copy.translationModel(model) : copy.translationModelUnknown}</p>
                    <p>{copy.translationOriginalIsRecord}</p>
                    <p>{copy.translationGuards}</p>
                    <p>{copy.translationAsk}</p>
                </div>
            </Modal>
        </>
    );
}
