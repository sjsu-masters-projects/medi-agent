import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReplySources } from "@/components/features/reply-sources";

const { fetchReplyEvidence } = vi.hoisted(() => ({ fetchReplyEvidence: vi.fn() }));
vi.mock("@/services/chat-api", () => ({ fetchReplyEvidence }));

const props = { patientId: "p1", messageId: "m1", accessToken: "t" } as const;
afterEach(() => { cleanup(); fetchReplyEvidence.mockReset(); });

describe("ReplySources", () => {
    it("loads nothing until opened, then lists titles, pages and the record (en-US)", async () => {
        fetchReplyEvidence.mockResolvedValue({ message_id: "m1", evidence: { tools: ["get_patient_context"], sources: [
            { kind: "document", file_name: "labs.pdf", title: { "en-US": "Lab results", "es-MX": "Resultados" }, pages: [2, 3] },
        ] } });
        render(<ReplySources {...props} locale="en-US" />);
        expect(fetchReplyEvidence).not.toHaveBeenCalled();
        fireEvent.click(screen.getByText("Sources"));
        expect(await screen.findByText("Lab results (pages 2, 3)")).toBeTruthy();
        expect(screen.getByText("Your health record in this app")).toBeTruthy();
        expect(fetchReplyEvidence).toHaveBeenCalledWith("p1", "m1", "t");
    });

    it("uses the Spanish title and wording (es-MX)", async () => {
        fetchReplyEvidence.mockResolvedValue({ message_id: "m1", evidence: { sources: [
            { kind: "document", file_name: "labs.pdf", title: { "en-US": "Lab results", "es-MX": "Resultados de laboratorio" }, pages: [1] },
        ] } });
        render(<ReplySources {...props} locale="es-MX" />);
        fireEvent.click(screen.getByText("Fuentes"));
        expect(await screen.findByText("Resultados de laboratorio (página 1)")).toBeTruthy();
    });

    it("shows nothing once a reply is known to have no evidence", async () => {
        fetchReplyEvidence.mockResolvedValue(null);
        const { container } = render(<ReplySources {...props} locale="en-US" />);
        fireEvent.click(screen.getByText("Sources"));
        await waitFor(() => expect(container.innerHTML).toBe(""));
    });

    it("says it failed and retries on the next open", async () => {
        fetchReplyEvidence.mockRejectedValueOnce(new Error("boom")).mockResolvedValue({ message_id: "m1", evidence: { sources: [{ kind: "reference", source: "MedlinePlus", title: "Metformin" }] } });
        render(<ReplySources {...props} locale="en-US" />);
        const details = document.querySelector("details")!;
        details.open = true; fireEvent(details, new Event("toggle"));
        expect(await screen.findByText(/could not be loaded/)).toBeTruthy();
        details.open = false; fireEvent(details, new Event("toggle"));
        details.open = true; fireEvent(details, new Event("toggle"));
        expect(await screen.findByText("Metformin")).toBeTruthy();
    });
});
