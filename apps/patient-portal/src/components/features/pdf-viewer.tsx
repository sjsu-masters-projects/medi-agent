"use client";

import { useEffect, useRef } from "react";
import {
    PdfViewerComponent,
    Toolbar,
    Magnification,
    Navigation,
    LinkAnnotation,
    BookmarkView,
    ThumbnailView,
    Print,
    TextSelection,
    TextSearch,
    Inject,
} from "@syncfusion/ej2-react-pdfviewer";

interface PdfViewerProps {
    documentUrl: string;
    height?: string;
}

export function PdfViewer({ documentUrl, height = "500px" }: PdfViewerProps) {
    const viewerRef = useRef<PdfViewerComponent | null>(null);

    useEffect(() => {
        return () => {
            viewerRef.current = null;
        };
    }, []);

    return (
        <div className="overflow-hidden rounded-xl border border-gray-200">
            <PdfViewerComponent
                documentPath={documentUrl}
                enableNavigation
                enableToolbar
                height={height}
                id="pdf-viewer"
                ref={viewerRef}
                resourceUrl="/assets/ej2-pdfviewer-lib"
            >
                <Inject
                    services={[
                        Toolbar,
                        Magnification,
                        Navigation,
                        LinkAnnotation,
                        BookmarkView,
                        ThumbnailView,
                        Print,
                        TextSelection,
                        TextSearch,
                    ]}
                />
            </PdfViewerComponent>
        </div>
    );
}
