import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RecordsPage from "@/app/(app)/records/page";
import { DocumentParseStatus, DocumentType } from "@/types";

const { deleteRequest, get, post, push, uploadDocumentToStorage } = vi.hoisted(() => ({
    deleteRequest: vi.fn(),
    get: vi.fn(),
    post: vi.fn(),
    push: vi.fn(),
    uploadDocumentToStorage: vi.fn(),
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
    api: { delete: deleteRequest, get, post },
}));

vi.mock("@/services/storage", () => ({
    uploadDocumentToStorage,
}));

describe("RecordsPage", () => {
    beforeEach(() => {
        deleteRequest.mockReset();
        get.mockReset();
        post.mockReset();
        push.mockReset();
        uploadDocumentToStorage.mockReset();
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

    it("deletes a selected document after confirmation", async () => {
        get.mockResolvedValue([
            {
                ai_summary: "Discharge instructions are ready.",
                created_at: "2026-04-20T12:00:00Z",
                document_type: DocumentType.DISCHARGE_SUMMARY,
                file_name: "Discharge Summary.txt",
                file_size_bytes: 1200,
                file_url: "https://example.test/discharge.txt",
                id: "doc-delete",
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
        deleteRequest.mockResolvedValue(undefined);

        render(<RecordsPage />);

        expect(await screen.findByText(/Discharge Summary\.txt/i)).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: /Discharge Summary\.txt/i }));
        fireEvent.click(screen.getByRole("button", { name: /delete document/i }));
        fireEvent.click(screen.getByRole("button", { name: /delete permanently/i }));

        await waitFor(() => {
            expect(deleteRequest).toHaveBeenCalledWith("/api/v1/documents/doc-delete", {
                token: "access-token",
            });
        });
        await waitFor(() => {
            expect(screen.queryByText(/Discharge Summary\.txt/i)).not.toBeInTheDocument();
        });
        expect(screen.getByText(/No records yet/i)).toBeInTheDocument();
    });

    it("infers a discharge summary type from uploaded PDF filenames", async () => {
        get.mockResolvedValue([]);
        uploadDocumentToStorage.mockResolvedValue("patient-1/vatsal-discharge-summary.pdf");
        post.mockResolvedValue({
            ai_summary: null,
            created_at: "2026-04-20T12:00:00Z",
            document_type: DocumentType.DISCHARGE_SUMMARY,
            file_name: "vatsal-discharge-summary.pdf",
            file_size_bytes: 1400,
            file_url: "https://example.test/discharge.pdf",
            id: "doc-upload",
            mime_type: "application/pdf",
            parse_status: DocumentParseStatus.PENDING,
            parsed: false,
            patient_id: "patient-1",
            source_clinic: null,
            uploaded_by: "patient-1",
            uploaded_by_role: "patient",
            visibility: "shared",
        });

        const { container } = render(<RecordsPage />);
        const input = container.querySelector<HTMLInputElement>('input[type="file"]');
        const file = new File(["test"], "vatsal-discharge-summary.pdf", {
            type: "application/pdf",
        });

        fireEvent.change(input!, { target: { files: [file] } });

        await waitFor(() => {
            expect(post).toHaveBeenCalledWith(
                "/api/v1/documents/",
                expect.objectContaining({
                    document_type: DocumentType.DISCHARGE_SUMMARY,
                    file_name: "vatsal-discharge-summary.pdf",
                }),
                { token: "access-token" },
            );
        });
    });
});
