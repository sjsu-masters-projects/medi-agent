"use client";

import { useState } from "react";
import { getReplySourcesCopy } from "@/content/reply-sources-copy";
import { fetchReplyEvidence, type ReplySourceApi } from "@/services/chat-api";
import type { Locale } from "@/types";
import { cleanRecordTitle } from "./record-row";

interface ReplySourcesProps {
    patientId: string;
    messageId: string;
    accessToken: string;
    locale: Locale;
}

type State = { phase: "closed" } | { phase: "loading" } | { phase: "failed" } | { phase: "none" } | { phase: "ready"; lines: string[] };

const RECORD_TOOL = "get_patient_context";

function titleOf(source: ReplySourceApi, locale: Locale, fallback: string): string {
    const title = source.title;
    const picked = typeof title === "string" ? title : title?.[locale] ?? Object.values(title ?? {})[0];
    // A cleaned file name, or a reference's publisher; never another internal source key.
    const publisher = source.kind === "reference" && typeof source.source === "string" ? source.source : "";
    return picked || (source.file_name ? cleanRecordTitle(source.file_name) : "") || publisher || fallback;
}

/**
 * A compact, collapsed "Sources" line under a Nora reply. The saved evidence is read only when
 * the patient opens it; a reply with none saved shows nothing at all once that is known.
 */
export function ReplySources({ patientId, messageId, accessToken, locale }: ReplySourcesProps) {
    const copy = getReplySourcesCopy(locale);
    const [state, setState] = useState<State>({ phase: "closed" });
    const [loaded, setLoaded] = useState(false);

    async function load() {
        setState({ phase: "loading" });
        try {
            const row = await fetchReplyEvidence(patientId, messageId, accessToken);
            const lines = (row?.evidence.sources ?? []).map((source) => {
                const pages = (source.pages ?? []).filter((page) => Number.isInteger(page));
                const name = titleOf(source, locale, copy.untitled);
                return pages.length ? `${name} (${copy.page(pages)})` : name;
            });
            if (row?.evidence.tools?.includes(RECORD_TOOL)) lines.push(copy.record);
            setLoaded(true);
            setState(lines.length ? { phase: "ready", lines } : { phase: "none" });
        } catch {
            setState({ phase: "failed" });
        }
    }

    if (state.phase === "none") return null;
    return <details className="mt-2 text-xs text-muted" onToggle={(event) => {
        if (event.currentTarget.open) { if (!loaded) void load(); }
    }}>
        <summary className="inline-flex min-h-11 cursor-pointer items-center font-medium text-ink-2 hover:text-brand-ink">{copy.summary}</summary>
        {state.phase === "loading" && <p role="status">{copy.loading}</p>}
        {state.phase === "failed" && <p role="status">{copy.failed}</p>}
        {state.phase === "ready" && <ul className="list-disc space-y-0.5 pl-4">{state.lines.map((line, index) => <li key={`${line}-${index}`} className="break-words [overflow-wrap:anywhere]">{line}</li>)}</ul>}
    </details>;
}
