"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "@/components/ui/icons";
import { TranslationInfo } from "@/components/ui/translation-note";
import { fetchEvidenceGlosses, type EvidenceGloss } from "@/services/clinicians";

/**
 * LOC-003 item 2: an English gloss beside Spanish source evidence.
 *
 * The excerpt itself never changes — it is the evidence, and a clinician comparing it with
 * the document needs the exact printed words. The gloss sits under it, labelled, so an
 * English-only reviewer can tell what the document actually says.
 *
 * The server addresses a gloss by the excerpt's own text, so the same printed sentence is
 * glossed once however many citations quote it, and asking twice costs no model call.
 */

/** Matches the server's normalisation: whitespace-collapsed text is the identity. */
export function normaliseExcerpt(excerpt: string): string {
    return excerpt.split(/\s+/).filter(Boolean).join(" ");
}

/**
 * Spanish function words. Testing in the browser keeps us from asking about English text,
 * which would spend a request to be told there is nothing to gloss. The server decides for
 * real; this only avoids the obvious no-ops.
 */
const SPANISH_HINT =
    /\b(el|la|los|las|un|una|de|del|con|sin|para|por|cada|tome|toma|tomar|dia|día|dias|días|veces|vaso|agua|comidas|antes|despues|después|no|dosis|tableta|tabletas|capsula|cápsula|manana|mañana|noche|semana|sangre|azucar|azúcar|presion|presión|peso|prueba|resultado|resultados|paciente|medicamento|alergia|sintoma|síntoma)\b/i;

/** Worth asking about: long enough to mean something, and it reads as Spanish. */
export function mayNeedGloss(excerpt: string | null | undefined): boolean {
    const text = normaliseExcerpt(excerpt ?? "");
    return text.length > 2 && SPANISH_HINT.test(text);
}

export type GlossMap = ReadonlyMap<string, EvidenceGloss>;

/**
 * Fetch glosses for the Spanish excerpts on screen, once per distinct excerpt.
 *
 * Reading never waits for this: the excerpts render immediately and a gloss appears when it
 * arrives. A failure leaves the original alone, which is the right fallback — no gloss is
 * safer than a gloss nobody checked.
 */
export function useEvidenceGlosses(
    patientId: string | undefined,
    excerpts: Array<string | null | undefined>,
): GlossMap {
    const [glosses, setGlosses] = useState<Map<string, EvidenceGloss>>(new Map());
    const asked = useRef(new Set<string>());

    const wanted = useMemo(() => {
        const unique = new Set<string>();
        for (const excerpt of excerpts) {
            if (mayNeedGloss(excerpt)) unique.add(normaliseExcerpt(excerpt as string));
        }
        return [...unique].sort();
    }, [excerpts]);

    // One dependency standing for the excerpt set, so a re-render with the same excerpts
    // in a new array does not re-run the effect.
    const key = wanted.join("|");
    useEffect(() => {
        if (!patientId) return;
        const pending = wanted.filter((excerpt) => !asked.current.has(excerpt));
        if (!pending.length) return;
        for (const excerpt of pending) asked.current.add(excerpt);
        let alive = true;
        void fetchEvidenceGlosses(patientId, pending)
            .then((result) => {
                if (!alive || !result.glosses.length) return;
                setGlosses((current) => {
                    const next = new Map(current);
                    for (const gloss of result.glosses) {
                        if (gloss.excerpt) next.set(gloss.excerpt, gloss);
                    }
                    return next;
                });
            })
            .catch(() => {
                // The original stays on screen; let a later render ask again.
                if (alive) for (const excerpt of pending) asked.current.delete(excerpt);
            });
        return () => {
            alive = false;
        };
        // `key` stands for `wanted`, which is derived from it.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [patientId, key]);

    return glosses;
}

/** Find an excerpt's gloss in the map the hook returns. */
export function glossFor(
    glosses: GlossMap,
    excerpt: string | null | undefined,
): EvidenceGloss | undefined {
    if (!excerpt) return undefined;
    return glosses.get(normaliseExcerpt(excerpt));
}

/** The gloss line that sits under an original excerpt. Renders nothing without one. */
export function EvidenceGlossLine({
    gloss,
    className = "",
}: {
    gloss?: EvidenceGloss;
    className?: string;
}) {
    if (!gloss?.gloss) return null;
    return (
        <span className={`mt-1 flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 text-xs text-ink-2 ${className}`}>
            <span className="inline-flex shrink-0 items-center gap-1 text-[11px] font-semibold text-muted">
                <Icon name="globe" aria-hidden="true" className="h-3 w-3" />
                In English
            </span>
            <span className="min-w-0 break-words" lang="en-US">
                {gloss.gloss}
            </span>
            <TranslationInfo
                detail={
                    <p>
                        The Spanish above is the source evidence and is never changed. This gloss
                        is only here to help you read it.
                    </p>
                }
                modelId={gloss.model_id}
            />
        </span>
    );
}
