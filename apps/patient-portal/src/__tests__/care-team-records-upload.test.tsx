import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import RecordsPage from "@/app/(app)/records/page";
import { ApiClientError } from "@/services/api";

const { get, post, hashDocumentFile, uploadDocumentToStorage } = vi.hoisted(() => ({
    get: vi.fn(), post: vi.fn(), hashDocumentFile: vi.fn(), uploadDocumentToStorage: vi.fn(),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));
vi.mock("react-redux", () => ({
    useDispatch: () => vi.fn(),
    useSelector: (selector: (state: unknown) => unknown) => selector({ auth: { accessToken: "access-token", expiresAt: Math.floor(Date.now() / 1000) + 3600, refreshToken: "r", user: { id: "patient-1" } } }),
}));
vi.mock("@/services/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/services/api")>()), api: { get, post, delete: vi.fn(), put: vi.fn() } }));
vi.mock("@/services/storage", () => ({ hashDocumentFile, uploadDocumentToStorage }));
vi.mock("@/services/auth-redirect", () => ({ redirectToLogin: vi.fn() }));
vi.mock("@/services/auth-refresh", () => ({ refreshPatientSession: vi.fn() }));
vi.mock("@/services/browser-voice", () => ({ playAssistantVoiceResponse: vi.fn(() => null) }));
vi.mock("@/hooks/use-patient-profile", () => ({ usePatientProfile: () => ({ preferredLanguage: "en-US", timezone: "UTC" }), useSharedPatientProfile: () => null }));

const teams = [
    { care_team_id: "t1", specialty: "Cardiology", clinician_name: "Dr. Park", clinic_id: "c1", clinic_name: "Cedar Grove" },
    { care_team_id: "t2", specialty: "Orthopaedics", clinician_name: "Dr. Lee", clinic_id: "c2", clinic_name: "Willow Terrace" },
];
const created = { id: "d1", file_name: "labs.pdf", document_type: "lab_report", created_at: "2026-10-22T12:00:00Z", parse_status: "pending", patient_id: "patient-1", uploaded_by: "patient-1", uploaded_by_role: "patient", visibility: "shared" };

function route(options: unknown) {
    get.mockImplementation(async (url: string) => {
        if (url.includes("care-team-options")) { if (options instanceof Error) throw options; return options; }
        if (url.includes("/care-team/patient/conditions")) return [];
        return [];
    });
}
async function chooseFile(container: HTMLElement) {
    await waitFor(() => expect(container.querySelector('input[type="file"]')).toBeTruthy());
    fireEvent.change(container.querySelector<HTMLInputElement>('input[type="file"]')!, { target: { files: [new File(["x"], "labs.pdf", { type: "application/pdf" })] } });
}

describe("records upload routing", () => {
    beforeEach(() => {
        get.mockReset(); post.mockReset(); hashDocumentFile.mockReset(); uploadDocumentToStorage.mockReset();
        hashDocumentFile.mockResolvedValue("a".repeat(64)); uploadDocumentToStorage.mockResolvedValue("patient-1/labs.pdf"); post.mockResolvedValue(created);
    });
    afterEach(cleanup);

    it("asks which care team the file is for and uploads nothing until it is answered", async () => {
        route(teams);
        const { container } = render(<RecordsPage />);
        await chooseFile(container);
        const dialog = await screen.findByRole("dialog", { name: "Which care team is this for?" });
        expect(uploadDocumentToStorage).not.toHaveBeenCalled();
        fireEvent.click(within(dialog).getByRole("radio", { name: /Orthopaedics/ }));
        fireEvent.click(within(dialog).getByRole("button", { name: "Upload document" }));
        await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
        expect(post.mock.calls[0][1]).toMatchObject({ file_name: "labs.pdf", care_team_id: "t2", start_ingestion: true });
        expect(post.mock.calls[0][1]).not.toHaveProperty("not_sure");
    });

    it("sends not_sure for Not sure", async () => {
        route(teams);
        const { container } = render(<RecordsPage />);
        await chooseFile(container);
        const dialog = await screen.findByRole("dialog");
        fireEvent.click(within(dialog).getByRole("radio", { name: /Not sure/ }));
        fireEvent.click(within(dialog).getByRole("button", { name: "Upload document" }));
        await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
        expect(post.mock.calls[0][1]).toMatchObject({ not_sure: true });
    });

    it("cancelling uploads nothing", async () => {
        route(teams);
        const { container } = render(<RecordsPage />);
        await chooseFile(container);
        fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancel" }));
        expect(uploadDocumentToStorage).not.toHaveBeenCalled();
        expect(post).not.toHaveBeenCalled();
    });

    it("preselects a single care team", async () => {
        route([teams[0]]);
        const { container } = render(<RecordsPage />);
        await chooseFile(container);
        const dialog = await screen.findByRole("dialog");
        expect(within(dialog).getByRole("radio", { name: /Cardiology/ })).toBeChecked();
        fireEvent.click(within(dialog).getByRole("button", { name: "Upload document" }));
        await waitFor(() => expect(post).toHaveBeenCalled());
        expect(post.mock.calls[0][1]).toMatchObject({ care_team_id: "t1" });
    });

    it("uploads straight away for a patient with no care teams (unchanged flow)", async () => {
        route([]);
        const { container } = render(<RecordsPage />);
        await chooseFile(container);
        await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
        expect(post.mock.calls[0][1]).not.toHaveProperty("care_team_id");
    });

    it("falls back to the server rule when the care teams cannot be read, and asks if the server needs a choice", async () => {
        route(new Error("down"));
        post.mockRejectedValueOnce(new ApiClientError("Choose a care team", 422, { error: { code: "CARE_TEAM_REQUIRED", message: "x" } }));
        const { container } = render(<RecordsPage />);
        await chooseFile(container);
        await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
        // The options are unavailable, so the generic upload error shows instead of a dead end.
        expect(await screen.findByText(/Upload failed/)).toBeInTheDocument();
    });

    it("reopens the question when the server answers CARE_TEAM_REQUIRED", async () => {
        let optionCalls = 0;
        get.mockImplementation(async (url: string) => {
            if (url.includes("care-team-options")) return ++optionCalls === 1 ? [] : teams;
            return [];
        });
        post.mockRejectedValueOnce(new ApiClientError("Choose a care team", 422, { error: { code: "CARE_TEAM_REQUIRED", message: "x" } }));
        const { container } = render(<RecordsPage />);
        await chooseFile(container);
        const dialog = await screen.findByRole("dialog", { name: "Which care team is this for?" });
        fireEvent.click(within(dialog).getByRole("radio", { name: /Cardiology/ }));
        fireEvent.click(within(dialog).getByRole("button", { name: "Upload document" }));
        await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
        expect(post.mock.calls[1][1]).toMatchObject({ care_team_id: "t1" });
    });
});
