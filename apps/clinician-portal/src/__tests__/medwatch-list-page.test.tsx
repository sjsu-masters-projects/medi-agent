import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MedWatchPage from "@/app/(dashboard)/medwatch/page";
import { clinicFilterState, resetClinicFilter } from "@/test/clinic-filter-mock";
import { approvedDraft, makeDraft, submittedDraft } from "./fixtures/medwatch";

const mocks = vi.hoisted(() => ({ fetchMedWatchDrafts: vi.fn(), replace: vi.fn() }));
const query = vi.hoisted(() => ({ value: "" }));
vi.mock("@/hooks/use-clinic-filter", async () => (await import("@/test/clinic-filter-mock")).clinicFilterModule);
vi.mock("next/navigation", () => ({
    useRouter: () => ({ replace: mocks.replace, push: vi.fn() }),
    useSearchParams: () => new URLSearchParams(query.value),
}));
vi.mock("@/services/clinicians", async (importOriginal) => ({
    ...(await importOriginal<typeof import("@/services/clinicians")>()),
    fetchMedWatchDrafts: mocks.fetchMedWatchDrafts,
}));

const discarded = makeDraft({
    id: "33333333-2222-4333-8444-555555555555",
    discardedAt: "2026-10-11T16:30:00Z",
    discardReason: "Wrong product.",
});

function draftsFor(state: string) {
    if (state === "submitted") return [submittedDraft({ id: "44444444-2222-4333-8444-555555555555" })];
    if (state === "discarded") return [discarded];
    return [
        makeDraft(),
        approvedDraft({ id: "22222222-2222-4333-8444-555555555555" }),
        makeDraft({
            id: "55555555-2222-4333-8444-555555555555",
            missingForApproval: [{ path: "section_g.occupation", code: "occupation_missing" }],
        }),
    ];
}

describe("MedWatch reports list", () => {
    beforeEach(() => {
        mocks.fetchMedWatchDrafts.mockReset();
        mocks.replace.mockReset();
        mocks.fetchMedWatchDrafts.mockImplementation(async (state: string) => draftsFor(state));
        query.value = "";
        window.history.replaceState(null, "", "/medwatch");
    });

    it("tags reports with the clinic and filters by clinic only with several clinics", async () => {
        mocks.fetchMedWatchDrafts.mockImplementation(async (state: string) =>
            state === "active" ? [makeDraft({ clinicName: "Bay Clinic", clinicId: "clinic-b" })] : [],
        );
        resetClinicFilter();
        const { unmount } = render(<MedWatchPage />);
        await screen.findByRole("list", { name: "Drafts reports" });
        expect(screen.queryByText("Bay Clinic")).not.toBeInTheDocument();
        expect(screen.queryByLabelText("Clinic")).not.toBeInTheDocument();
        unmount();

        clinicFilterState.clinics = [
            { clinic_id: "clinic-a", clinic_code: "A", clinic_name: "City Health", role: "admin", status: "active" },
            { clinic_id: "clinic-b", clinic_code: "B", clinic_name: "Bay Clinic", role: "provider", status: "active" },
        ] as never;
        clinicFilterState.clinicId = "clinic-b";
        render(<MedWatchPage />);
        await screen.findByRole("list", { name: "Drafts reports" });
        expect(screen.getAllByText("Bay Clinic", { selector: "span" }).length).toBeGreaterThan(0);
        expect(mocks.fetchMedWatchDrafts).toHaveBeenCalledWith("active", "clinic-b");
        resetClinicFilter();
    });

    it("tabs split active drafts from approved, submitted and discarded reports with counts", async () => {
        render(<MedWatchPage />);
        const list = await screen.findByRole("list", { name: "Drafts reports" });
        expect(within(list).getAllByRole("listitem")).toHaveLength(2);
        expect(screen.getByRole("button", { name: /Drafts\s*2/ })).toHaveAttribute("aria-pressed", "true");
        expect(screen.getByRole("button", { name: /Approved\s*1/ })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /Submitted\s*1/ })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /Discarded\s*1/ })).toBeInTheDocument();
        expect(within(list).getAllByText("SP-K7QD").length).toBeGreaterThan(0);
        // Truncated text keeps its full value available on hover.
        for (const element of within(list).getAllByText("fluticasone/salmeterol inhaler")) {
            expect(element).toHaveAttribute("title", "fluticasone/salmeterol inhaler");
        }
        for (const element of within(list).getAllByText("SP-K7QD")) {
            expect(element).toHaveAttribute("title", "SP-K7QD");
        }
        expect(screen.getByRole("group", { name: /./ })).toBeInTheDocument();
        expect(within(list).getAllByText("fluticasone/salmeterol inhaler").length).toBeGreaterThan(0);
        expect(within(list).getAllByText("1 to complete").length).toBeGreaterThan(0);
        expect(within(list).getAllByRole("link")[0].getAttribute("href")).toMatch(/^\/medwatch\/[0-9a-f-]{36}/);

        fireEvent.click(screen.getByRole("button", { name: /Approved/ }));
        expect(window.location.search).toBe("?tab=approved");
        const approved = await screen.findByRole("list", { name: "Approved reports" });
        expect(within(approved).getAllByText("Approved").length).toBeGreaterThan(0);
    });

    it("restores the tab from the URL and shows an empty-tab sentence", async () => {
        query.value = "tab=submitted";
        mocks.fetchMedWatchDrafts.mockImplementation(async (state: string) => (state === "submitted" ? [] : draftsFor(state)));
        render(<MedWatchPage />);
        expect(await screen.findByText("Reports you recorded as submitted to FDA appear here.")).toBeInTheDocument();
    });

    it("redirects an old assessment deep link to the ADR case page without loading reports", async () => {
        query.value = "assessment=adr-77";
        render(<MedWatchPage />);
        await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/adr-reviews/adr-77"));
        expect(mocks.fetchMedWatchDrafts).not.toHaveBeenCalled();
    });

    it("shows a retry when loading fails", async () => {
        mocks.fetchMedWatchDrafts.mockRejectedValueOnce(new Error("private diagnostic"));
        render(<MedWatchPage />);
        expect(await screen.findByText("Unable to load MedWatch reports", { selector: "h3" })).toBeInTheDocument();
        expect(screen.queryByText("private diagnostic")).not.toBeInTheDocument();
    });
});
