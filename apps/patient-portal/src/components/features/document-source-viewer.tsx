"use client";

import { useEffect, useRef, useState } from "react";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";

interface DocumentSourceViewerProps {
  fileName: string;
  previewMimeType?: string | null;
  previewStatus?: string | null;
  previewUrl?: string | null;
  sourceMimeType?: string | null;
  sourceUrl?: string | null;
}

function PdfCanvasViewer({ documentUrl, fileName }: { documentUrl: string; fileName: string }) {
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
          setError("This PDF could not be displayed in the browser. You can still download the original.");
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
          setError("This page could not be rendered. You can still download the original.");
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
    return <p className="text-sm leading-6 text-[#7f2c23]">{error}</p>;
  }

  if (!document) {
    return <p className="text-sm text-[#5b6b83]">Loading source document…</p>;
  }

  return (
    <div className="space-y-3">
      <div className="overflow-auto rounded-2xl border border-[#eaded3] bg-[#f7f4ef] p-3">
        <canvas
          aria-label={`${fileName}, page ${pageNumber}`}
          className="mx-auto max-w-full bg-white shadow-sm"
          ref={canvasRef}
          role="img"
        />
      </div>
      <div className="flex items-center justify-between gap-3 text-sm text-[#5b6b83]">
        <span>
          Page {pageNumber} of {document.numPages}
        </span>
        <div className="flex gap-2">
          <button
            className="rounded-xl border border-[#b9ded6] bg-white px-3 py-2 font-semibold text-[#147465] disabled:cursor-not-allowed disabled:opacity-45"
            disabled={pageNumber <= 1}
            onClick={() => setPageNumber((current) => Math.max(1, current - 1))}
            type="button"
          >
            Previous
          </button>
          <button
            className="rounded-xl border border-[#b9ded6] bg-white px-3 py-2 font-semibold text-[#147465] disabled:cursor-not-allowed disabled:opacity-45"
            disabled={pageNumber >= document.numPages}
            onClick={() => setPageNumber((current) => Math.min(document.numPages, current + 1))}
            type="button"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

/** Render the original clinical source (or its server-generated TIFF preview). */
export function DocumentSourceViewer({
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
    <section aria-label="Source document" className="space-y-3 rounded-2xl border border-[#eaded3] bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-[#7b8798]">Source document</p>
          <p className="mt-1 text-sm font-semibold text-[#30415f]">{usesPreview ? "Preview generated from the original TIFF" : "Original uploaded file"}</p>
        </div>
        {sourceUrl ? (
          <a
            className="rounded-xl border border-[#b9ded6] bg-white px-3 py-2 text-sm font-semibold text-[#147465]"
            href={sourceUrl}
            rel="noreferrer"
            target="_blank"
          >
            Download original
          </a>
        ) : null}
      </div>

      {viewMimeType === "application/pdf" && viewUrl ? (
        <PdfCanvasViewer documentUrl={viewUrl} fileName={fileName} />
      ) : null}
      {canRenderNativeImage && viewUrl ? (
        // The source URL is signed by the API and this is intentionally a native browser image.
        // eslint-disable-next-line @next/next/no-img-element
        <img alt={`Source document: ${fileName}`} className="max-h-[560px] w-full rounded-xl object-contain" src={viewUrl} />
      ) : null}
      {previewStatus === "pending" ? (
        <p className="text-sm leading-6 text-[#5b6b83]">A browser preview is being prepared for this TIFF. The original is available to download now.</p>
      ) : null}
      {previewStatus === "failed" ? (
        <p className="text-sm leading-6 text-[#7f2c23]">A browser preview could not be prepared. Download the original or ask your care team for help reviewing it.</p>
      ) : null}
      {!viewUrl && previewStatus !== "pending" && previewStatus !== "failed" ? (
        <p className="text-sm leading-6 text-[#7f2c23]">This source is temporarily unavailable. Please refresh and try again.</p>
      ) : null}
    </section>
  );
}
