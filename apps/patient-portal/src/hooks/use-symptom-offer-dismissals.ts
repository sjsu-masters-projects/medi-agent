"use client";

import { useCallback, useState } from "react";

const MAX_REMEMBERED = 200;

function storageKey(userId: string | undefined) {
    return `ma:symptom-offer-dismissed:${userId ?? "anonymous"}`;
}
function load(userId: string | undefined): string[] {
    try {
        const parsed: unknown = JSON.parse(window.localStorage.getItem(storageKey(userId)) ?? "[]");
        return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
    } catch {
        return [];
    }
}

/**
 * Which symptom-note offers the patient has answered, remembered per message so a reload
 * does not bring a dismissed offer back. Browser storage is only a convenience: when it
 * is unavailable the offer simply stays for the session.
 */
export function useSymptomOfferDismissals(userId: string | undefined) {
    const [state, setState] = useState<{ userId: string | undefined; ids: ReadonlySet<string> }>(() => ({ userId, ids: new Set(load(userId)) }));
    // A different signed-in patient never inherits another patient's answers.
    if (state.userId !== userId) setState({ userId, ids: new Set(load(userId)) });
    const dismiss = useCallback((messageId: string) => {
        setState((previous) => {
            if (previous.ids.has(messageId)) return previous;
            const next = [...previous.ids, messageId].slice(-MAX_REMEMBERED);
            try { window.localStorage.setItem(storageKey(previous.userId), JSON.stringify(next)); } catch { /* per-session only */ }
            return { ...previous, ids: new Set(next) };
        });
    }, []);
    return { dismissed: state.userId === userId ? state.ids : new Set<string>(), dismiss };
}
