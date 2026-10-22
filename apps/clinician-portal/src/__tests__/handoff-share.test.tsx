import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HandoffSharePanel } from "@/components/features/handoff-share-panel";
import { SharedHandoffView } from "@/components/features/shared-handoff-view";
import { SharedWithMeList } from "@/components/features/shared-handoff-list";
import { ApiClientError } from "@/services/api";
import {
    exportSharedHandoff,
    fetchSharedHandoff,
    listHandoffShares,
    listShareCandidates,
    listSharedWithMe,
    revokeHandoffShare,
    shareHandoffSummary,
    type HandoffRecipient,
    type HandoffShare,
    type SharedHandoffDetail,
} from "@/services/handoff-summaries";

vi.mock("@/services/care-team-plans", () => ({
    errorCode: (error: unknown) => (error as { code?: string } | null)?.code ?? null,
}));
vi.mock("@/services/handoff-summaries", () => ({
    listShareCandidates: vi.fn(),
    listHandoffShares: vi.fn(),
    shareHandoffSummary: vi.fn(),
    revokeHandoffShare: vi.fn(),
    listSharedWithMe: vi.fn(),
    fetchSharedHandoff: vi.fn(),
    exportSharedHandoff: vi.fn(),
}));

const person = (id: string, first: string, last: string, clinic: string, basis: HandoffRecipient["bases"]): HandoffRecipient => ({
    clinician_id: id, first_name: first, last_name: last, specialty: "Cardiology", clinics: [{ id: `c-${clinic}`, name: clinic }], bases: basis,
});
const omar = person("u1", "Omar", "Reyes", "Birch Clinic", ["care_team"]);
const tessa = person("u2", "Tessa", "Lin", "Cedar Grove", ["clinic_member"]);
const share = (over: Partial<HandoffShare> = {}): HandoffShare => ({
    id: "sh1", summary_id: "s1", version: 2, recipient_id: "u1", recipient_name: "Omar Reyes", recipient_specialty: "Orthopaedics",
    shared_at: "2026-10-22T10:00:00Z", revoked_at: null, replayed: false, ...over,
});
const shared = (over: Partial<SharedHandoffDetail> = {}): SharedHandoffDetail => ({
    share_id: "sh1", summary_id: "s1", version: 1, title: "Handoff for Dr. Lin", purpose: "colleague", patient_id: "p1", patient_name: "Lucia Synthetic",
    author_name: "Elena Park", author_specialty: "Cardiology", author_clinic: "Cedar Grove", shared_at: "2026-10-22T10:00:00Z",
    approved_by_name: "Elena Park", approved_at: "2026-10-22T09:00:00Z", built_at: "2026-10-22T08:00:00Z", newer: null,
    narrative: "Stable.", notes: "Call the family.",
    sections: [{ key: "shared_core", title: "Shared record", status: "available", note: null, items: [
        { id: "m1", text: "Medication: Lisinopril", detail: null, source: { kind: "record", table: null, id: null, label: "Recorded by Elena Park", href: null } },
    ] }],
    ...over,
});

beforeEach(() => {
    vi.mocked(listShareCandidates).mockResolvedValue([omar, tessa]);
    vi.mocked(listHandoffShares).mockResolvedValue([]);
    window.print = vi.fn();
});
afterEach(() => vi.resetAllMocks());

function open() {
    const onChanged = vi.fn();
    render(<HandoffSharePanel onChanged={onChanged} onClose={vi.fn()} open summaryId="s1" version={2} />);
    return onChanged;
}

describe("HandoffSharePanel", () => {
    it("offers only the people the server returns, with specialty, clinic and why", async () => {
        open();
        const dialog = await screen.findByRole("dialog", { name: "Share this summary" });
        expect(await within(dialog).findByText("Dr. Omar Reyes")).toBeInTheDocument();
        expect(within(dialog).getByText(/Cardiology · Birch Clinic/)).toBeInTheDocument();
        expect(within(dialog).getByText("Treats this patient")).toBeInTheDocument();
        expect(within(dialog).getByText("Member of your clinic")).toBeInTheDocument();
        expect(within(dialog).getByText(/sees only this version, read-only/)).toBeInTheDocument();
    });

    it("filters by clinic chip and sends the search to the server", async () => {
        open();
        await screen.findByText("Dr. Omar Reyes");
        fireEvent.click(screen.getByRole("button", { name: "Cedar Grove" }));
        expect(screen.queryByText("Dr. Omar Reyes")).not.toBeInTheDocument();
        expect(screen.getByText("Dr. Tessa Lin")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Cedar Grove" })).toHaveAttribute("aria-pressed", "true");
        fireEvent.change(screen.getByRole("searchbox"), { target: { value: "lin" } });
        await waitFor(() => expect(listShareCandidates).toHaveBeenCalledWith("s1", "lin"));
    });

    it("shares the open version with one person and says they were notified", async () => {
        vi.mocked(shareHandoffSummary).mockResolvedValue(share());
        const onChanged = open();
        fireEvent.click(await screen.findByRole("button", { name: "Share with Dr. Omar Reyes" }));
        await waitFor(() => expect(shareHandoffSummary).toHaveBeenCalledWith("s1", 2, "u1"));
        expect(await screen.findByText(/Shared version 2 with Dr. Omar Reyes. They have been notified./)).toBeInTheDocument();
        expect(onChanged).toHaveBeenCalled();
    });

    it("lists current shares and revokes one", async () => {
        vi.mocked(listHandoffShares).mockResolvedValue([share(), share({ id: "old", version: 1, recipient_name: "Old Version" })]);
        vi.mocked(revokeHandoffShare).mockResolvedValue(share({ revoked_at: "2026-10-22T11:00:00Z" }));
        open();
        const revoke = await screen.findByRole("button", { name: "Revoke access for Omar Reyes" });
        expect(screen.queryByText("Old Version")).not.toBeInTheDocument();
        expect(screen.getByText("Shared")).toBeInTheDocument();
        fireEvent.click(revoke);
        await waitFor(() => expect(revokeHandoffShare).toHaveBeenCalledWith("sh1"));
        expect(await screen.findByText("Access removed for Omar Reyes.")).toBeInTheDocument();
    });

    it("explains a refusal and never claims success", async () => {
        vi.mocked(shareHandoffSummary).mockRejectedValue(Object.assign(new Error("x"), { code: "HANDOFF_NOT_APPROVED" }));
        open();
        fireEvent.click(await screen.findByRole("button", { name: "Share with Dr. Omar Reyes" }));
        expect(await screen.findByText(/Only the approved version can be shared/)).toBeInTheDocument();
        expect(screen.queryByText(/They have been notified/)).not.toBeInTheDocument();
    });

    it("reports colleagues that could not be loaded and retries", async () => {
        vi.mocked(listShareCandidates).mockRejectedValueOnce(new Error("down"));
        open();
        fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
        expect(await screen.findByText("Dr. Omar Reyes")).toBeInTheDocument();
    });
});

describe("SharedHandoffView", () => {
    it("is read-only: names who shared and when, no edit or approve, no record links", async () => {
        vi.mocked(fetchSharedHandoff).mockResolvedValue(shared());
        render(<SharedHandoffView shareId="sh1" />);
        await screen.findByRole("heading", { name: "Handoff for Dr. Lin" });
        expect(screen.getByText(/Shared by Dr. Elena Park on 2026-10-22/)).toBeInTheDocument();
        expect(screen.getByText("Medication: Lisinopril")).toBeInTheDocument();
        expect(screen.getByText("Call the family.")).toBeInTheDocument();
        expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: /^(Approve|Save changes|Share)$/ })).not.toBeInTheDocument();
        expect(screen.queryByRole("link", { name: /Source:/ })).not.toBeInTheDocument();
        expect(screen.getByText("Source: Recorded by Elena Park")).toBeInTheDocument();
        expect(screen.queryByText(/newer version/)).not.toBeInTheDocument();
    });

    it("points to a newer version only when the server says it is also shared", async () => {
        vi.mocked(fetchSharedHandoff).mockResolvedValue(shared({ newer: { share_id: "sh2", version: 2 } }));
        render(<SharedHandoffView shareId="sh1" />);
        const link = await screen.findByRole("link", { name: "Open version 2" });
        expect(link).toHaveAttribute("href", "/handoff-shared/sh2");
        expect(screen.getByText(/A newer version exists/)).toBeInTheDocument();
    });

    it("records a print and a FHIR export through the server", async () => {
        vi.mocked(fetchSharedHandoff).mockResolvedValue(shared());
        vi.mocked(exportSharedHandoff).mockResolvedValue({ format: "print", summary: shared(), bundle: null });
        URL.createObjectURL = vi.fn(() => "blob:x");
        URL.revokeObjectURL = vi.fn();
        render(<SharedHandoffView shareId="sh1" />);
        fireEvent.click(await screen.findByRole("button", { name: "Print" }));
        await waitFor(() => expect(exportSharedHandoff).toHaveBeenCalledWith("sh1", "print"));
        await waitFor(() => expect(window.print).toHaveBeenCalled());
        vi.mocked(exportSharedHandoff).mockResolvedValue({ format: "fhir", summary: shared(), bundle: { resourceType: "Bundle" } });
        fireEvent.click(screen.getByRole("button", { name: "Export FHIR" }));
        expect(await screen.findByText(/FHIR bundle exported/)).toBeInTheDocument();
    });

    it("says a revoked or foreign share is unavailable, and offers retry on a server error", async () => {
        vi.mocked(fetchSharedHandoff).mockRejectedValue(new ApiClientError("no", 404, null));
        const { unmount } = render(<SharedHandoffView shareId="sh1" />);
        expect(await screen.findByText("Summary not available")).toBeInTheDocument();
        unmount();
        vi.mocked(fetchSharedHandoff).mockRejectedValue(new ApiClientError("boom", 500, null));
        render(<SharedHandoffView shareId="sh1" />);
        expect(await screen.findByText("Unable to load this summary")).toBeInTheDocument();
    });
});

describe("SharedWithMeList", () => {
    const item = (over = {}) => ({
        share_id: "sh1", summary_id: "s1", version: 1, title: "Handoff", purpose: "colleague" as const, patient_id: "p1", patient_name: "Lucia Synthetic",
        author_name: "Elena Park", author_specialty: "Cardiology", shared_at: "2026-10-22T10:00:00Z", approved_at: "2026-10-22T09:00:00Z", newer: null, ...over,
    });

    it("links each share, marks one with a newer shared version, and filters by patient", async () => {
        vi.mocked(listSharedWithMe).mockResolvedValue([item(), item({ share_id: "sh2", patient_id: "p2", newer: { share_id: "x", version: 2 } })]);
        render(<SharedWithMeList />);
        const links = await screen.findAllByRole("link");
        expect(links[0]).toHaveAttribute("href", "/handoff-shared/sh1");
        expect(screen.getByText("A newer version exists")).toBeInTheDocument();
    });

    it("limits to one patient, and has empty and error states", async () => {
        vi.mocked(listSharedWithMe).mockResolvedValue([item(), item({ share_id: "sh2", patient_id: "p2" })]);
        const { unmount } = render(<SharedWithMeList patientId="p1" />);
        expect(await screen.findAllByRole("link")).toHaveLength(1);
        unmount();
        vi.mocked(listSharedWithMe).mockResolvedValue([]);
        const second = render(<SharedWithMeList />);
        expect(await screen.findByText("Nothing shared with you")).toBeInTheDocument();
        second.unmount();
        vi.mocked(listSharedWithMe).mockRejectedValue(new Error("down"));
        render(<SharedWithMeList />);
        expect(await screen.findByText("Unable to load shared summaries")).toBeInTheDocument();
    });
});
