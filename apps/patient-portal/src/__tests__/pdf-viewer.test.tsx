import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PdfViewer } from "@/components/features/pdf-viewer";

// Mock the Syncfusion component to avoid loading the heavy WASM/canvas library during tests
vi.mock("@syncfusion/ej2-react-pdfviewer", () => ({
    PdfViewerComponent: ({ documentPath, height, children }: { documentPath: string; height: string; children?: React.ReactNode }) => (
        <div data-testid="mock-syncfusion-pdf" data-url={documentPath} style={{ height }}>
            Mocked Syncfusion PDF Viewer
            {children}
        </div>
    ),
    Toolbar: vi.fn(),
    Magnification: vi.fn(),
    Navigation: vi.fn(),
    LinkAnnotation: vi.fn(),
    BookmarkView: vi.fn(),
    ThumbnailView: vi.fn(),
    Print: vi.fn(),
    TextSelection: vi.fn(),
    TextSearch: vi.fn(),
    Inject: () => <div data-testid="mock-syncfusion-inject" />,
}));

describe("PdfViewer Component", () => {
    it("renders the mocked Syncfusion viewer with the correct document URL", () => {
        const testUrl = "https://example.com/test-document.pdf";
        render(<PdfViewer documentUrl={testUrl} height="600px" />);

        const viewer = screen.getByTestId("mock-syncfusion-pdf");
        expect(viewer).toBeInTheDocument();
        expect(viewer.getAttribute("data-url")).toBe(testUrl);
        expect(viewer.style.height).toBe("600px");
        
        expect(screen.getByTestId("mock-syncfusion-inject")).toBeInTheDocument();
    });

    it("uses the default height if none is provided", () => {
        render(<PdfViewer documentUrl="test.pdf" />);
        const viewer = screen.getByTestId("mock-syncfusion-pdf");
        expect(viewer.style.height).toBe("500px");
    });
});
