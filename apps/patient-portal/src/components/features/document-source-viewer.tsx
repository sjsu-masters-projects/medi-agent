"use client";

import { useEffect, useRef, useState } from "react";
import { recordsCopy } from "./records-copy";
import type { Locale } from "@/types";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";

interface DocumentSourceViewerProps {
  locale?: Locale;
  fileName: string;
  previewMimeType?: string | null;
  previewStatus?: string | null;
  previewUrl?: string | null;
  sourceMimeType?: string | null;
  sourceUrl?: string | null;
}

function PdfCanvasViewer({
  documentUrl,
  fileName,
  locale,
}: {
  documentUrl: string;
  fileName: string;
  locale: Locale;
}) {
  const copy = (text: string) => recordsCopy(locale, text);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pageNumber, setPageNumber] = useState(1);

  useEffect(() => {
    let disposed = false;
    let loadedDocument: PDFDocumentProxy | null = null;

    async function loadDocument() {
      setDocument(null);
      setError(null);
      setPageNumber(1);
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = new URL(
          "pdfjs-dist/build/pdf.worker.min.mjs",
          import.meta.url,
        ).toString();
        const loadingTask = pdfjs.getDocument({ url: documentUrl });
        loadedDocument = await loadingTask.promise;
        if (!disposed) {
          setDocument(loadedDocument);
        }
      } catch {
        if (!disposed) {
          setError("load");
        }
      }
    }

    void loadDocument();
    return () => {
      disposed = true;
      void loadedDocument?.cleanup();
    };
  }, [documentUrl]);

  useEffect(() => {
    if (!document || !canvasRef.current) {
      return;
    }

    const activeDocument = document;
    let cancelled = false;
    let renderTask: RenderTask | null = null;

    async function renderPage() {
      try {
        const page = await activeDocument.getPage(pageNumber);
        const viewport = page.getViewport({ scale: 1.25 });
        const canvas = canvasRef.current;
        const context = canvas?.getContext("2d");
        if (!canvas || !context || cancelled) {
          return;
        }
        canvas.width = Math.ceil(viewport.width);
        canvas.height = Math.ceil(viewport.height);
        renderTask = page.render({ canvas, canvasContext: context, viewport });
        await renderTask.promise;
      } catch {
        if (!cancelled) {
          setError("render");
        }
      }
    }

    void renderPage();
    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [document, pageNumber]);

  if (error) {
    return (
      <p className="text-sm leading-6 text-danger-ink">
        {copy(
          error === "load"
            ? "This PDF could not be displayed in the browser. You can still download the original."
            : "This page could not be rendered. You can still download the original.",
        )}
      </p>
    );
  }

  if (!document) {
    return (
      <p className="text-sm text-ink-2">
        {copy("Loading source document…")}
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="overflow-auto rounded-2xl border border-line-strong bg-surface-2 p-3">
        <canvas
          aria-label={
            locale === "es-MX"
              ? `${fileName}, página ${pageNumber}`
              : `${fileName}, page ${pageNumber}`
          }
          className="mx-auto max-w-full bg-surface shadow-sm"
          ref={canvasRef}
          role="img"
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-ink-2">
        <span>
          {locale === "es-MX"
            ? `Página ${pageNumber} de ${document.numPages}`
            : `Page ${pageNumber} of ${document.numPages}`}
        </span>
        <div className="flex gap-2">
          <button
            className="min-h-11 rounded-xl border border-line-strong bg-surface px-3 py-2 font-semibold text-ink-2 disabled:cursor-not-allowed disabled:opacity-45"
            disabled={pageNumber <= 1}
            onClick={() => setPageNumber((current) => Math.max(1, current - 1))}
            type="button"
          >
            {copy("Previous")}
          </button>
          <button
            className="min-h-11 rounded-xl border border-line-strong bg-surface px-3 py-2 font-semibold text-ink-2 disabled:cursor-not-allowed disabled:opacity-45"
            disabled={pageNumber >= document.numPages}
            onClick={() =>
              setPageNumber((current) =>
                Math.min(document.numPages, current + 1),
              )
            }
            type="button"
          >
            {copy("Next")}
          </button>
        </div>
      </div>
    </div>
  );
}

/** Render the original clinical source (or its server-generated TIFF preview). */
export function DocumentSourceViewer({
  fileName,
  locale = "en-US",
  previewMimeType,
  previewStatus,
  previewUrl,
  sourceMimeType,
  sourceUrl,
}: DocumentSourceViewerProps) {
  const copy = (text: string) => recordsCopy(locale, text);
  const usesPreview = previewStatus === "ready" && Boolean(previewUrl);
  const viewUrl = usesPreview ? previewUrl : sourceUrl;
  const viewMimeType = usesPreview ? previewMimeType : sourceMimeType;
  const canRenderNativeImage =
    Boolean(viewMimeType?.startsWith("image/")) &&
    viewMimeType !== "image/tiff";

  return (
    <section
      aria-label={copy("Source document")}
      className="space-y-3 rounded-2xl border border-line-strong bg-surface p-4"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-ink-2">
            {copy("Source document")}
          </p>
          <p className="mt-1 text-sm font-semibold text-ink-2">
            {usesPreview
              ? copy("Preview generated from the original TIFF")
              : copy("Original uploaded file")}
          </p>
        </div>
        {sourceUrl ? (
          <a
            className="inline-flex min-h-11 items-center rounded-xl border border-line-strong bg-surface px-3 py-2 text-sm font-semibold text-ink-2"
            href={sourceUrl}
            rel="noreferrer"
            target="_blank"
          >
            {copy("Download original")}
          </a>
        ) : null}
      </div>

      {viewMimeType === "application/pdf" && viewUrl ? (
        <PdfCanvasViewer
          documentUrl={viewUrl}
          fileName={fileName}
          locale={locale}
        />
      ) : null}
      {canRenderNativeImage && viewUrl ? (
        // The source URL is signed by the API and this is intentionally a native browser image.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          alt={`${copy("Source document")}: ${fileName}`}
          className="max-h-[560px] w-full rounded-xl object-contain"
          src={viewUrl}
        />
      ) : null}
      {previewStatus === "pending" ? (
        <p className="text-sm leading-6 text-ink-2">
          {copy(
            "A browser preview is being prepared for this TIFF. The original is available to download now.",
          )}
        </p>
      ) : null}
      {previewStatus === "failed" ? (
        <p className="text-sm leading-6 text-danger-ink">
          {copy(
            "A browser preview could not be prepared. Download the original or ask your care team for help reviewing it.",
          )}
        </p>
      ) : null}
      {!viewUrl && previewStatus !== "pending" && previewStatus !== "failed" ? (
        <p className="text-sm leading-6 text-danger-ink">
          {copy(
            "This source is temporarily unavailable. Please refresh and try again.",
          )}
        </p>
      ) : null}
    </section>
  );
}
