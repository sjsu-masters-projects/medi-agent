import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DocumentSourceViewer } from "@/components/features/document-source-viewer";

describe("DocumentSourceViewer", () => {
  it("renders a browser-safe image from the authorized source URL", () => {
    render(
      <DocumentSourceViewer
        fileName="lab-result.png"
        sourceMimeType="image/png"
        sourceUrl="https://example.test/signed-lab-result.png"
      />,
    );

    const image = screen.getByRole("img", { name: "Source document: lab-result.png" });
    expect(image).toHaveAttribute("src", "https://example.test/signed-lab-result.png");
    expect(screen.getByRole("link", { name: "Download original" })).toHaveAttribute(
      "href",
      "https://example.test/signed-lab-result.png",
    );
  });

  it("does not inline a TIFF while its derived PDF preview is pending", () => {
    render(
      <DocumentSourceViewer
        fileName="scan.tiff"
        previewStatus="pending"
        sourceMimeType="image/tiff"
        sourceUrl="https://example.test/signed-scan.tiff"
      />,
    );

    expect(screen.getByText(/preview is being prepared/i)).toBeInTheDocument();
    expect(screen.queryByRole("img")).toBeNull();
  });
});
