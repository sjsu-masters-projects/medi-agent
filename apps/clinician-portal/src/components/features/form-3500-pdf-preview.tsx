"use client";

import { useCallback, useEffect, useState } from "react";
import { Button, Skeleton } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { fetchForm3500PreviewPdf, MedWatchRequestError, medWatchErrorMessage } from "@/services/clinicians";

type PreviewState =
    | { kind: "loading" }
    | { kind: "ready"; url: string }
    | { kind: "error"; message: string };

/**
 * The filled Form FDA 3500 with a "DRAFT - not for submission" watermark. The PDF needs the
 * bearer token, so it is fetched, shown from a blob URL and revoked when it is replaced or
 * the step unmounts. Nothing is recorded: it is a preview, not an export.
 */
export function Form3500PdfPreview({
    draftId,
    revision,
    fetchPdf = fetchForm3500PreviewPdf,
}: {
    draftId: string;
    /** A changed revision remounts the preview, so it follows saved edits. */
    revision: number;
    fetchPdf?: (draftId: string) => Promise<Blob>;
}) {
    return <PreviewBody draftId={draftId} fetchPdf={fetchPdf} key={revision} />;
}

function PreviewBody({
    draftId,
    fetchPdf,
}: {
    draftId: string;
    fetchPdf: (draftId: string) => Promise<Blob>;
}) {
    const [state, setState] = useState<PreviewState>({ kind: "loading" });
    const [attempt, setAttempt] = useState(0);

    useEffect(() => {
        let cancelled = false;
        let objectUrl: string | null = null;
        fetchPdf(draftId).then(
            (blob) => {
                if (cancelled) return;
                objectUrl = URL.createObjectURL(new Blob([blob], { type: "application/pdf" }));
                setState({ kind: "ready", url: objectUrl });
            },
            (failure: unknown) => {
                if (cancelled) return;
                setState({
                    kind: "error",
                    message:
                        failure instanceof MedWatchRequestError
                            ? medWatchErrorMessage(failure.code, failure.status)
                            : "The preview could not be produced. Try again.",
                });
            },
        );
        return () => {
            cancelled = true;
            if (objectUrl) URL.revokeObjectURL(objectUrl);
        };
    }, [draftId, attempt, fetchPdf]);

    const retry = useCallback(() => {
        setState({ kind: "loading" });
        setAttempt((current) => current + 1);
    }, []);

    return (
        <section aria-label="Form 3500 PDF preview" className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-surface-2 px-4 py-2.5">
                <p className="flex items-center gap-2 text-[13px] text-ink-2">
                    <Icon aria-hidden="true" className="h-4 w-4 text-muted" name="eye" />
                    Draft preview — watermarked, not for submission
                </p>
                {state.kind === "ready" ? (
                    <a
                        className="inline-flex items-center gap-1.5 rounded-md text-[13px] font-semibold text-primary hover:text-primary-hover"
                        href={state.url}
                        rel="noreferrer"
                        target="_blank"
                    >
                        Open in new tab
                        <Icon aria-hidden="true" className="h-3.5 w-3.5" name="external" />
                    </a>
                ) : null}
            </div>
            {state.kind === "loading" ? (
                <div aria-label="Loading Form 3500 preview" className="space-y-3" role="status">
                    <Skeleton className="h-[70vh] min-h-[420px] w-full" />
                </div>
            ) : null}
            {state.kind === "error" ? (
                <div
                    className="flex min-h-[240px] flex-col items-center justify-center gap-3 rounded-xl border border-risk-line bg-risk-soft px-6 py-10 text-center"
                    role="alert"
                >
                    <p className="max-w-[48ch] text-sm text-risk-ink">{state.message}</p>
                    <Button onClick={retry} variant="secondary">
                        Try again
                    </Button>
                </div>
            ) : null}
            {state.kind === "ready" ? (
                <iframe
                    className="h-[70vh] min-h-[480px] w-full rounded-xl border border-line bg-surface"
                    src={state.url}
                    title="Form FDA 3500 draft preview"
                />
            ) : null}
        </section>
    );
}
