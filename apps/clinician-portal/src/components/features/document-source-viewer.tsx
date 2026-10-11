"use client";

import { useEffect, useRef, useState } from "react";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";
import { Icon } from "@/components/ui/icons";
import { ProcessingDots } from "@/components/ui/motion";

const pageButton =
    "ma-press inline-flex h-8 items-center justify-center gap-1.5 rounded-lg border border-line-strong bg-surface px-3 text-[13px] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-[#94A3B8]";

interface DocumentSourceViewerProps {
    initialPage?: number;
    fileName: string;
    previewMimeType?: string | null;
    previewStatus?: string | null;
    previewUrl?: string | null;
    sourceMimeType?: string | null;
    sourceUrl?: string | null;
}

function PdfCanvasViewer({ documentUrl, fileName, initialPage = 1 }: { documentUrl: string; fileName: string; initialPage?: number }) {
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const [document, setDocument] = useState<PDFDocumentProxy | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [pageNumber, setPageNumber] = useState(1);
    const [retryCount, setRetryCount] = useState(0);

    useEffect(() => {
        let disposed = false;
        let loadedDocument: PDFDocumentProxy | null = null;

        async function loadDocument() {
            setDocument(null);
            setError(null);
            try {
                const pdfjs = await import("pdfjs-dist");
                pdfjs.GlobalWorkerOptions.workerSrc = new URL(
                    "pdfjs-dist/build/pdf.worker.min.mjs",
                    import.meta.url,
                ).toString();
                const loadingTask = pdfjs.getDocument({ url: documentUrl });
                loadedDocument = await loadingTask.promise;
                if (!disposed) {
                    setPageNumber(Math.min(loadedDocument.numPages, Math.max(1, initialPage)));
                    setDocument(loadedDocument);
                }
            } catch {
                if (!disposed) {
                    setError("This PDF could not be displayed in the browser. You can still download the original.");
                }
            }
        }

        void loadDocument();
        return () => {
            disposed = true;
            void loadedDocument?.cleanup();
        };
    }, [documentUrl, initialPage, retryCount]);

    useEffect(() => {
        if (!document || !canvasRef.current) return;
        const activeDocument = document;
        let cancelled = false;
        let renderTask: RenderTask | null = null;

        async function renderPage() {
            try {
                const page = await activeDocument.getPage(pageNumber);
                const viewport = page.getViewport({ scale: 1.25 });
                const canvas = canvasRef.current;
                const context = canvas?.getContext("2d");
                if (!canvas || !context || cancelled) return;
                canvas.width = Math.ceil(viewport.width);
                canvas.height = Math.ceil(viewport.height);
                renderTask = page.render({ canvas, canvasContext: context, viewport });
                await renderTask.promise;
            } catch {
                if (!cancelled) setError("This page could not be rendered. You can still download the original.");
            }
        }

        void renderPage();
        return () => {
            cancelled = true;
            renderTask?.cancel();
        };
    }, [document, pageNumber]);

    if (error) return (
        <div className="flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink" role="alert">
            <Icon name="alert" aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
                <p>{error}</p>
                <button className={`${pageButton} mt-2`} onClick={() => setRetryCount((current) => current + 1)} type="button">
                    <Icon name="refresh" aria-hidden="true" className="h-3.5 w-3.5" />
                    Retry PDF preview
                </button>
            </div>
        </div>
    );
    if (!document) return (
        <div className="flex min-h-40 items-center justify-center rounded-xl bg-sunken">
            <p role="status" className="flex items-center gap-2 text-sm text-muted">Loading source document…<ProcessingDots /></p>
        </div>
    );

    return (
        <div className="space-y-3">
            <div className="max-h-[560px] overflow-auto rounded-xl bg-sunken p-5">
                <canvas
                    aria-label={`${fileName}, page ${pageNumber}`}
                    className="mx-auto block max-w-full rounded-[10px] bg-surface shadow-[var(--shadow-page)]"
                    ref={canvasRef}
                    role="img"
                />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3">
                <span className="font-mono text-xs text-muted">Page {pageNumber} of {document.numPages}</span>
                <div className="flex gap-2">
                    <button
                        className={pageButton}
                        disabled={pageNumber <= 1}
                        onClick={() => setPageNumber((current) => Math.max(1, current - 1))}
                        type="button"
                    >
                        <Icon name="back" aria-hidden="true" className="h-3.5 w-3.5" />
                        Previous
                    </button>
                    <button
                        className={pageButton}
                        disabled={pageNumber >= document.numPages}
                        onClick={() => setPageNumber((current) => Math.min(document.numPages, current + 1))}
                        type="button"
                    >
                        Next
                        <Icon name="chevron" aria-hidden="true" className="h-3.5 w-3.5" />
                    </button>
                </div>
            </div>
        </div>
    );
}

/** Render a patient source artifact without giving the browser a permanent storage URL. */
export function DocumentSourceViewer({
    initialPage,
    fileName,
    previewMimeType,
    previewStatus,
    previewUrl,
    sourceMimeType,
    sourceUrl,
}: DocumentSourceViewerProps) {
    const usesPreview = previewStatus === "ready" && Boolean(previewUrl);
    const viewUrl = usesPreview ? previewUrl : sourceUrl;
    const viewMimeType = usesPreview ? previewMimeType : sourceMimeType;
    const canRenderNativeImage = Boolean(viewMimeType?.startsWith("image/")) && viewMimeType !== "image/tiff";

    return (
        <section aria-label="Source document" className="space-y-3 rounded-2xl border border-line bg-surface p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                    <p className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">Source document</p>
                    <p className="mt-1 text-sm font-semibold text-ink">
                        {usesPreview ? "Preview generated from the original TIFF" : "Original uploaded file"}
                    </p>
                </div>
                {sourceUrl ? (
                    <a
                        className={pageButton}
                        href={sourceUrl}
                        rel="noreferrer"
                        target="_blank"
                    >
                        <Icon name="download" aria-hidden="true" className="h-3.5 w-3.5" />
                        Download original
                    </a>
                ) : null}
            </div>
            {viewMimeType === "application/pdf" && viewUrl ? <PdfCanvasViewer documentUrl={viewUrl} fileName={fileName} initialPage={initialPage} /> : null}
            {canRenderNativeImage && viewUrl ? (
                <div className="max-h-[560px] overflow-auto rounded-xl bg-sunken p-5">
                    {/* The source URL is a short-lived API-signed URL and this is intentionally a native image. */}
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img alt={`Source document: ${fileName}`} className="mx-auto block max-h-[520px] max-w-full rounded-[10px] bg-surface object-contain shadow-[var(--shadow-page)]" src={viewUrl} />
                </div>
            ) : null}
            {previewStatus === "pending" ? (
                <p className="flex items-start gap-2.5 rounded-xl border border-line bg-surface-2 px-4 py-3 text-sm text-ink-2">
                    <Icon name="clock" aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-muted" />
                    <span>A browser preview is being prepared for this TIFF. The original is available to download now.</span>
                </p>
            ) : null}
            {previewStatus === "failed" ? (
                <p className="flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink">
                    <Icon name="alert" aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>A browser preview could not be prepared. Download the original or use your established review workflow.</span>
                </p>
            ) : null}
            {!viewUrl && previewStatus !== "pending" && previewStatus !== "failed" ? (
                <p className="flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink">
                    <Icon name="alert" aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>This source is temporarily unavailable. Refresh and try again.</span>
                </p>
            ) : null}
        </section>
    );
}
