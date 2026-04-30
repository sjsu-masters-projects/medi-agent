import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RecordsPage from "@/app/(app)/records/page";
import { DocumentParseStatus, DocumentType } from "@/types";

const { get, post, push } = vi.hoisted(() => ({
    get: vi.fn(),
    post: vi.fn(),
    push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
    useRouter: () => ({ push }),
}));

vi.mock("react-redux", () => ({
    useSelector: (selector: (state: unknown) => unknown) =>
        selector({
            auth: {
                accessToken: "access-token",
                user: { id: "patient-1" },
            },
        }),
}));

vi.mock("@/services/api", () => ({
    api: { get, post },
}));

vi.mock("@/services/storage", () => ({
    uploadDocumentToStorage: vi.fn(),
}));

describe("RecordsPage", () => {
    beforeEach(() => {
        get.mockReset();
        post.mockReset();
        push.mockReset();
        window.sessionStorage.clear();
    });

    it("shows document summary details and keeps the ask-about-document path available", async () => {
        get.mockResolvedValue([
            {
                ai_summary: "Your lab values are stable and no urgent action is needed.",
                created_at: "2026-04-20T12:00:00Z",
                document_type: DocumentType.LAB_REPORT,
                file_name: "April Lab Report.txt",
                file_size_bytes: 1200,
                file_url: "https://example.test/lab.txt",
                id: "doc-1",
                mime_type: "text/plain",
                parse_status: DocumentParseStatus.COMPLETED,
                parsed: true,
                patient_id: "patient-1",
                source_clinic: "City Health",
                uploaded_by: "patient-1",
                uploaded_by_role: "patient",
                visibility: "shared",
            },
        ]);

        render(<RecordsPage />);

        expect(await screen.findByText(/April Lab Report\.txt/i)).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: /April Lab Report\.txt/i }));

        expect(await screen.findAllByText(/City Health/i)).toHaveLength(2);
        expect(screen.getByText(/Your lab values are stable/i)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /ask about this document/i })).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: /ask about this document/i }));

        await waitFor(() => {
            expect(push).toHaveBeenCalledWith("/chat?document=doc-1");
        });
    });
});
