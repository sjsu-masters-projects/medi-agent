import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DocumentUploadZone } from "@/components/features/document-upload-zone";

vi.mock("@/services/auth-session", () => ({
  readStoredSession: vi.fn(),
}));

describe("DocumentUploadZone", () => {
  it("rejects a plain-text file before it can be uploaded", () => {
    const { container } = render(<DocumentUploadZone patientId="patient-1" />);
    const input = container.querySelector<HTMLInputElement>(
      'input[type="file"]',
    );
    const textFile = new File(["synthetic QA"], "prescription.txt", {
      type: "text/plain",
    });

    fireEvent.change(input!, { target: { files: [textFile] } });

    expect(
      screen.getByText(
        "Choose a PDF, JPG, PNG, WebP, or TIFF file up to 20 MB.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /upload 1 file/i }),
    ).not.toBeInTheDocument();
  });

  it("queues a PDF and exposes only storage-supported file extensions", () => {
    const { container } = render(<DocumentUploadZone patientId="patient-1" />);
    const input = container.querySelector<HTMLInputElement>(
      'input[type="file"]',
    );
    const pdf = new File(["synthetic QA"], "prescription.pdf", {
      type: "application/pdf",
    });

    fireEvent.change(input!, { target: { files: [pdf] } });

    expect(input).toHaveAttribute(
      "accept",
      ".pdf,.jpg,.jpeg,.png,.webp,.tif,.tiff",
    );
    expect(screen.getByText("prescription.pdf")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /upload 1 file/i }),
    ).toBeInTheDocument();
  });
});
