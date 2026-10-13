import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Form3500DownloadDialog } from "@/components/features/form-3500-download-dialog";
import { MedWatchRequestError } from "@/services/clinicians";

const template = { revision: "09/2025", expires: "2027-09-30", maySuperseded: false };

describe("Form3500DownloadDialog", () => {
    let createObjectURL: ReturnType<typeof vi.fn>;
    let revokeObjectURL: ReturnType<typeof vi.fn>;
    let clicked: { href: string; download: string }[];

    beforeEach(() => {
        createObjectURL = vi.fn(() => "blob:synthetic");
        revokeObjectURL = vi.fn();
        Object.assign(URL, { createObjectURL, revokeObjectURL });
        clicked = [];
        vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
            clicked.push({ href: this.href, download: this.download });
        });
    });

    afterEach(() => vi.restoreAllMocks());

    it("states that MediAgent did not submit the report, then saves under the server filename", async () => {
        const blob = new Blob(["%PDF-1.7"], { type: "application/pdf" });
        const download = vi.fn().mockResolvedValue({ blob, filename: "fda-3500-11111111-not-submitted.pdf" });
        const onClose = vi.fn();
        const onDownloaded = vi.fn();
        render(
            <Form3500DownloadDialog
                download={download}
                draftId="draft-1"
                onClose={onClose}
                onDownloaded={onDownloaded}
                open
                template={template}
            />,
        );
        const dialog = screen.getByRole("dialog", { name: "Download Form 3500 (PDF)" });
        expect(within(dialog).getByText("MediAgent did not submit this report. You submit it to FDA.")).toBeInTheDocument();
        expect(download).not.toHaveBeenCalled();
        fireEvent.click(within(dialog).getByRole("button", { name: "Download PDF" }));
        await waitFor(() => expect(onClose).toHaveBeenCalled());
        expect(download).toHaveBeenCalledWith("draft-1");
        expect(createObjectURL).toHaveBeenCalledWith(blob);
        expect(clicked).toEqual([{ href: "blob:synthetic", download: "fda-3500-11111111-not-submitted.pdf" }]);
        expect(revokeObjectURL).toHaveBeenCalledWith("blob:synthetic");
        expect(onDownloaded).toHaveBeenCalledWith("fda-3500-11111111-not-submitted.pdf");
    });

    it("shows a failed download inline by error code and saves nothing", async () => {
        const download = vi.fn().mockRejectedValue(new MedWatchRequestError("FORM_3500_TEMPLATE_MISMATCH", 503));
        const onClose = vi.fn();
        render(<Form3500DownloadDialog download={download} draftId="draft-1" onClose={onClose} open template={template} />);
        fireEvent.click(screen.getByRole("button", { name: "Download PDF" }));
        expect(await screen.findByRole("alert")).toHaveTextContent(/failed its integrity check/);
        expect(clicked).toEqual([]);
        expect(onClose).not.toHaveBeenCalled();
    });

    it("warns when the vendored revision may be superseded", () => {
        render(
            <Form3500DownloadDialog
                download={vi.fn()}
                draftId="draft-1"
                onClose={vi.fn()}
                open
                template={{ ...template, maySuperseded: true }}
            />,
        );
        expect(screen.getByRole("note")).toHaveTextContent(/passed its expiry date/);
    });

    it("cancels without downloading", () => {
        const download = vi.fn();
        const onClose = vi.fn();
        render(<Form3500DownloadDialog download={download} draftId="draft-1" onClose={onClose} open template={template} />);
        fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
        expect(onClose).toHaveBeenCalled();
        expect(download).not.toHaveBeenCalled();
    });
});
