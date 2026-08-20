import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RecordsPage from "@/app/(app)/records/page";
import { DocumentParseStatus, DocumentType } from "@/types";

const {
    authState,
    deleteRequest,
    dispatch,
    get,
    playAssistantVoiceResponse,
    post,
    push,
    redirectToLogin,
    refreshPatientSession,
    uploadDocumentToStorage,
    writeStoredSession,
} =
    vi.hoisted(() => ({
        authState: {
            value: {
                accessToken: "access-token",
                expiresAt: Math.floor(Date.now() / 1000) + 3600,
                refreshToken: "refresh-token",
                user: { id: "patient-1" },
            },
        },
        deleteRequest: vi.fn(),
        dispatch: vi.fn(() => ({ unwrap: vi.fn().mockResolvedValue(undefined) })),
        get: vi.fn(),
        playAssistantVoiceResponse: vi.fn(() => null),
        post: vi.fn(),
        push: vi.fn(),
        redirectToLogin: vi.fn(),
        refreshPatientSession: vi.fn(),
        uploadDocumentToStorage: vi.fn(),
        writeStoredSession: vi.fn(),
    }));

vi.mock("next/navigation", () => ({
    useRouter: () => ({ push }),
}));

vi.mock("react-redux", () => ({
    useDispatch: () => dispatch,
    useSelector: (selector: (state: unknown) => unknown) =>
        selector({
            auth: authState.value,
        }),
}));

vi.mock("@/services/api", () => ({
    api: { delete: deleteRequest, get, post },
}));

vi.mock("@/services/storage", () => ({
    uploadDocumentToStorage,
}));

vi.mock("@/services/auth-redirect", () => ({
    redirectToLogin,
}));

vi.mock("@/services/auth-refresh", () => ({
    refreshPatientSession,
}));

vi.mock("@/services/auth-session", () => ({
    writeStoredSession,
}));

vi.mock("@/services/browser-voice", () => ({
    playAssistantVoiceResponse,
}));

describe("RecordsPage", () => {
    beforeEach(() => {
        authState.value = {
            accessToken: "access-token",
            expiresAt: Math.floor(Date.now() / 1000) + 3600,
            refreshToken: "refresh-token",
            user: { id: "patient-1" },
        };
        deleteRequest.mockReset();
        dispatch.mockReset();
        dispatch.mockReturnValue({ unwrap: vi.fn().mockResolvedValue(undefined) });
        get.mockReset();
        playAssistantVoiceResponse.mockReset();
        playAssistantVoiceResponse.mockReturnValue(null);
        post.mockReset();
        push.mockReset();
        redirectToLogin.mockReset();
        refreshPatientSession.mockReset();
        uploadDocumentToStorage.mockReset();
        writeStoredSession.mockReset();
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

    it("uploads the file before starting its extraction import", async () => {
        get.mockResolvedValue([]);
        uploadDocumentToStorage.mockResolvedValue("patient-1/lab-results.pdf");
        let resolveCreate: ((document: Record<string, unknown>) => void) | undefined;
        const createdDocument = {
            ai_summary: null,
            created_at: "2026-04-20T12:00:00Z",
            document_type: DocumentType.LAB_REPORT,
            file_name: "lab-results.pdf",
            file_size_bytes: 1400,
            file_url: "https://example.test/lab-results.pdf",
            id: "doc-upload-order",
            mime_type: "application/pdf",
            parse_status: DocumentParseStatus.PENDING,
            parsed: false,
            patient_id: "patient-1",
            source_clinic: null,
            uploaded_by: "patient-1",
            uploaded_by_role: "patient",
            visibility: "shared",
        };
        post.mockImplementationOnce(
            () => new Promise((resolve) => {
                resolveCreate = resolve;
            }),
        );
        post.mockResolvedValueOnce({});

        const { container } = render(<RecordsPage />);
        const input = container.querySelector<HTMLInputElement>('input[type="file"]');
        fireEvent.change(input!, {
            target: {
                files: [new File(["test"], "lab-results.pdf", { type: "application/pdf" })],
            },
        });

        await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
        expect(post).toHaveBeenLastCalledWith(
            "/api/v1/documents/",
            expect.objectContaining({
                file_path: "patient-1/lab-results.pdf",
                start_ingestion: false,
            }),
            { token: "access-token" },
        );

        resolveCreate!(createdDocument);

        await waitFor(() => {
            expect(post).toHaveBeenLastCalledWith(
                "/api/v1/documents/extractions/import",
                { document_id: "doc-upload-order" },
                { token: "access-token" },
            );
        });
    });

    it("fails visibly and safely when an upload session cannot be refreshed", async () => {
        authState.value = {
            accessToken: "expired-access-token",
            expiresAt: Math.floor(Date.now() / 1000) - 60,
            refreshToken: "refresh-token",
            user: { id: "patient-1" },
        };
        get.mockResolvedValue([]);
        refreshPatientSession.mockRejectedValue(new Error("Refresh failed"));

        const { container } = render(<RecordsPage />);
        const input = container.querySelector<HTMLInputElement>('input[type="file"]');
        fireEvent.change(input!, {
            target: {
                files: [new File(["test"], "lab-results.pdf", { type: "application/pdf" })],
            },
        });

        expect(await screen.findByText(/your session expired. please sign in again before uploading/i)).toBeInTheDocument();
        expect(refreshPatientSession).toHaveBeenCalledWith("refresh-token");
        expect(redirectToLogin).toHaveBeenCalledWith({ reason: "session_expired" });
        expect(uploadDocumentToStorage).not.toHaveBeenCalled();
        expect(post).not.toHaveBeenCalled();
    });

    it("reads the visible document summary aloud", async () => {
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

        fireEvent.click(await screen.findByRole("button", { name: /April Lab Report\.txt/i }));
        fireEvent.click(screen.getByRole("button", { name: /read summary aloud/i }));

        expect(playAssistantVoiceResponse).toHaveBeenCalledWith(
            expect.objectContaining({
                language: "en-US",
                text: "Your lab values are stable and no urgent action is needed.",
            }),
        );
    });
});
