import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HandoffSummaryList } from "@/components/features/handoff-summary-list";
import { HandoffSummaryReview } from "@/components/features/handoff-summary-review";
import { ApiClientError } from "@/services/api";
import { fetchCareTeamOptions } from "@/services/care-team-plans";
import {
    approveHandoffSummary,
    createHandoffSummary,
    exportHandoffSummary,
    fetchHandoffSummary,
    listHandoffSummaries,
    saveHandoffSummary,
    type HandoffDetail,
} from "@/services/handoff-summaries";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/services/care-team-plans", () => ({
    fetchCareTeamOptions: vi.fn(),
    errorCode: (error: unknown) => (error as { code?: string } | null)?.code ?? null,
}));
vi.mock("@/services/handoff-summaries", () => ({
    listHandoffSummaries: vi.fn(),
    createHandoffSummary: vi.fn(),
    fetchHandoffSummary: vi.fn(),
    saveHandoffSummary: vi.fn(),
    approveHandoffSummary: vi.fn(),
    exportHandoffSummary: vi.fn(),
}));

const detail = (over: Partial<HandoffDetail> = {}): HandoffDetail => ({
    id: "s1", patient_id: "p1", care_team_id: "t1", author_id: "c1", title: "Handoff summary for a colleague",
    purpose: "colleague", recipient_label: "Dr. Rivera", status: "draft", current_version: 2,
    approved_version: null, approved_by: null, approved_at: null,
    created_at: "2026-10-21T10:00:00Z", updated_at: "2026-10-21T10:00:00Z", patient_name: "Lucia Synthetic",
    version: {
        version: 2, narrative: "Stable.", notes: null, built_at: "2026-10-21T10:00:00Z", created_by: "c1", created_at: "2026-10-21T10:00:00Z",
        sections: [
            { key: "shared_core", title: "Shared record", status: "available", note: null, items: [
                { id: "m1", text: "Medication: Lisinopril 10 mg", detail: null, source: { kind: "record", table: "medications", id: "m1", label: "Recorded by Elena Park", href: "/patients/p1?tab=profile" } },
                { id: "marker", text: "Some conditions are private and are not included in this summary.", detail: null, source: { kind: "rule", table: null, id: null, label: "The patient limits who sees some conditions", href: null } },
            ] },
            { key: "symptoms", title: "Recent confirmed symptoms", status: "empty", note: "No patient-confirmed symptoms in the last 30 days.", items: [] },
        ],
    },
    versions: [{ version: 2, created_by: "c1", created_at: "2026-10-21T10:00:00Z" }, { version: 1, created_by: "c1", created_at: "2026-10-21T09:00:00Z" }],
    events: [{ event_type: "created", version: 1, export_format: null, actor_id: "c1", created_at: "2026-10-21T09:00:00Z" }],
    ...over,
});
const approved = () => detail({ status: "approved", approved_version: 2, approved_by: "c1", approved_at: "2026-10-21T11:00:00Z" });

beforeEach(() => {
    vi.mocked(fetchHandoffSummary).mockResolvedValue(detail());
    window.print = vi.fn();
});
afterEach(() => vi.resetAllMocks());

describe("HandoffSummaryReview", () => {
    it("shows sections with a source chip on every line and the private-conditions marker", async () => {
        render(<HandoffSummaryReview patientId="p1" summaryId="s1" />);
        await screen.findByRole("heading", { name: "Handoff summary for a colleague" });
        expect(screen.getByRole("link", { name: /Source: Recorded by Elena Park/ })).toHaveAttribute("href", "/patients/p1?tab=profile");
        expect(screen.getByText(/Some conditions are private/)).toBeInTheDocument();
        expect(screen.getAllByText(/^Source:/)).toHaveLength(2);
        expect(screen.getByText("No patient-confirmed symptoms in the last 30 days.")).toBeInTheDocument();
        expect(screen.getByLabelText("Narrative")).toHaveValue("Stable.");
    });

    it("collapses and expands a section", async () => {
        render(<HandoffSummaryReview patientId="p1" summaryId="s1" />);
        const toggle = await screen.findByRole("button", { name: /Shared record/ });
        expect(toggle).toHaveAttribute("aria-expanded", "true");
        fireEvent.click(toggle);
        expect(toggle).toHaveAttribute("aria-expanded", "false");
    });

    it("gates export on approval, and approval on a confirmation", async () => {
        vi.mocked(approveHandoffSummary).mockResolvedValue(approved());
        render(<HandoffSummaryReview patientId="p1" summaryId="s1" />);
        await screen.findByText("Draft, not approved");
        expect(screen.getByRole("button", { name: "Print" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "Export FHIR" })).toBeDisabled();
        fireEvent.click(screen.getByRole("button", { name: "Approve" }));
        expect(approveHandoffSummary).not.toHaveBeenCalled();
        const dialog = await screen.findByRole("dialog");
        fireEvent.click(within(dialog).getByRole("button", { name: /Approve version 2/ }));
        await waitFor(() => expect(approveHandoffSummary).toHaveBeenCalledWith("p1", "s1", 2));
        vi.mocked(fetchHandoffSummary).mockResolvedValue(approved());
        await waitFor(() => expect(screen.getByRole("button", { name: "Export FHIR" })).toBeEnabled());
    });

    it("exports FHIR and records a print export for the approved version", async () => {
        vi.mocked(fetchHandoffSummary).mockResolvedValue(approved());
        vi.mocked(exportHandoffSummary).mockResolvedValue({ format: "print", summary: approved(), bundle: null });
        URL.createObjectURL = vi.fn(() => "blob:x");
        URL.revokeObjectURL = vi.fn();
        render(<HandoffSummaryReview patientId="p1" summaryId="s1" />);
        await screen.findByText("Approved");
        fireEvent.click(screen.getByRole("button", { name: "Print" }));
        await waitFor(() => expect(exportHandoffSummary).toHaveBeenCalledWith("p1", "s1", 2, "print"));
        await waitFor(() => expect(window.print).toHaveBeenCalled());
        vi.mocked(exportHandoffSummary).mockResolvedValue({ format: "fhir", summary: approved(), bundle: { resourceType: "Bundle" } });
        fireEvent.click(screen.getByRole("button", { name: "Export FHIR" }));
        await waitFor(() => expect(exportHandoffSummary).toHaveBeenCalledWith("p1", "s1", 2, "fhir"));
        expect(await screen.findByText(/FHIR bundle exported/)).toBeInTheDocument();
    });

    it("requires unsaved edits to be saved first, then saves against the version it saw", async () => {
        vi.mocked(saveHandoffSummary).mockResolvedValue(detail({ current_version: 3 }));
        render(<HandoffSummaryReview patientId="p1" summaryId="s1" />);
        const narrative = await screen.findByLabelText("Narrative");
        fireEvent.change(narrative, { target: { value: "Changed plan." } });
        expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
        fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
        await waitFor(() => expect(saveHandoffSummary).toHaveBeenCalledWith("p1", "s1", { expected_version: 2, narrative: "Changed plan.", notes: null, refresh: false }));
    });

    it("blocks approval while a section could not be read", async () => {
        const broken = detail();
        broken.version.sections[1] = { key: "symptoms", title: "Recent confirmed symptoms", status: "unavailable", note: "This section could not be read. Rebuild the summary before approving it.", items: [] };
        vi.mocked(fetchHandoffSummary).mockResolvedValue(broken);
        render(<HandoffSummaryReview patientId="p1" summaryId="s1" />);
        await screen.findByRole("heading", { name: "Handoff summary for a colleague" });
        expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);
        expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    });

    it("explains a version conflict instead of overwriting", async () => {
        vi.mocked(saveHandoffSummary).mockRejectedValue(Object.assign(new Error("x"), { code: "HANDOFF_VERSION_CONFLICT" }));
        render(<HandoffSummaryReview patientId="p1" summaryId="s1" />);
        fireEvent.change(await screen.findByLabelText("Narrative"), { target: { value: "Other" } });
        fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
        expect(await screen.findByText(/changed since you opened it/)).toBeInTheDocument();
    });

    it("shows an older version read-only", async () => {
        render(<HandoffSummaryReview patientId="p1" summaryId="s1" />);
        await screen.findByLabelText("Narrative");
        vi.mocked(fetchHandoffSummary).mockResolvedValue(detail());
        fireEvent.click(screen.getByRole("button", { name: "View version 1" }));
        await screen.findByText(/which is read-only/);
        expect(screen.queryByLabelText("Narrative")).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    });

    it("says a summary is unavailable on denial and offers retry on a server error", async () => {
        vi.mocked(fetchHandoffSummary).mockRejectedValue(new ApiClientError("no", 404, null));
        const { unmount } = render(<HandoffSummaryReview patientId="p1" summaryId="s1" />);
        expect(await screen.findByText("Summary not available")).toBeInTheDocument();
        unmount();
        vi.mocked(fetchHandoffSummary).mockRejectedValue(new ApiClientError("boom", 500, null));
        render(<HandoffSummaryReview patientId="p1" summaryId="s1" />);
        expect(await screen.findByText("Unable to load this summary")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    });
});

describe("HandoffSummaryList", () => {
    beforeEach(() => {
        vi.mocked(fetchCareTeamOptions).mockResolvedValue([]);
    });

    it("shows an empty state for a patient with no summaries", async () => {
        vi.mocked(listHandoffSummaries).mockResolvedValue([]);
        render(<HandoffSummaryList patientId="p1" />);
        expect(await screen.findByText("No handoff summaries yet")).toBeInTheDocument();
    });

    it("creates a draft and opens its review page", async () => {
        vi.mocked(listHandoffSummaries).mockResolvedValue([]);
        vi.mocked(createHandoffSummary).mockResolvedValue(detail());
        render(<HandoffSummaryList patientId="p1" />);
        await screen.findByText("No handoff summaries yet");
        fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
        await waitFor(() => expect(push).toHaveBeenCalledWith("/patients/p1/handoff/s1"));
    });

    it("asks for a care team when the server requires one, and reports a failed build", async () => {
        vi.mocked(listHandoffSummaries).mockResolvedValue([]);
        vi.mocked(createHandoffSummary).mockRejectedValue(Object.assign(new Error("x"), { code: "CARE_TEAM_REQUIRED" }));
        render(<HandoffSummaryList patientId="p1" />);
        await screen.findByText("No handoff summaries yet");
        fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
        expect(await screen.findByText(/Choose which care team/)).toBeInTheDocument();
        expect(push).not.toHaveBeenCalled();
    });

    it("reports a list that failed to load", async () => {
        vi.mocked(listHandoffSummaries).mockRejectedValue(new Error("down"));
        render(<HandoffSummaryList patientId="p1" />);
        expect(await screen.findByText("Unable to load summaries")).toBeInTheDocument();
    });
});
