import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DocumentSourceViewer } from "@/components/features/document-source-viewer";

const { getDocument, getPage } = vi.hoisted(() => ({ getDocument: vi.fn(), getPage: vi.fn() }));
vi.mock("pdfjs-dist", () => ({ getDocument, GlobalWorkerOptions: {} }));
describe("protected PDF source preview", () => {
    beforeEach(() => {
        vi.resetAllMocks();
        vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({} as CanvasRenderingContext2D);
        getPage.mockResolvedValue({ getViewport: () => ({ width: 100, height: 100 }), render: () => ({ promise: Promise.resolve(), cancel: vi.fn() }) });
        getDocument.mockReturnValue({ promise: Promise.resolve({ numPages: 3, getPage, cleanup: vi.fn() }) });
    });
    it("opens the cited page and supports page navigation", async () => {
        render(<DocumentSourceViewer fileName="source.pdf" sourceMimeType="application/pdf" sourceUrl="https://synthetic.test/source" initialPage={2} />);
        expect(await screen.findByText("Page 2 of 3")).toBeInTheDocument();
        await waitFor(() => expect(getPage).toHaveBeenCalledWith(2));
        fireEvent.click(screen.getByRole("button", { name: "Next" }));
        expect(await screen.findByText("Page 3 of 3")).toBeInTheDocument();
    });
    it("clamps an unavailable citation page to the document", async () => {
        render(<DocumentSourceViewer fileName="source.pdf" sourceMimeType="application/pdf" sourceUrl="https://synthetic.test/source" initialPage={99} />);
        expect(await screen.findByText("Page 3 of 3")).toBeInTheDocument();
    });
    it("recovers from a PDF transport failure through an explicit retry", async () => {
        getDocument.mockReturnValueOnce({ promise: Promise.reject(new Error("offline")) });
        render(<DocumentSourceViewer fileName="source.pdf" sourceMimeType="application/pdf" sourceUrl="https://synthetic.test/source" initialPage={2} />);
        fireEvent.click(await screen.findByRole("button", { name: "Retry PDF preview" }));
        expect(await screen.findByText("Page 2 of 3")).toBeInTheDocument();
        expect(getDocument).toHaveBeenCalledTimes(2);
    });
});
