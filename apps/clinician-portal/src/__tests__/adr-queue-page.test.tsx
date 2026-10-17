import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ADRReviewsPage from "@/app/(dashboard)/adr-reviews/page";
import { ageLabel } from "@/components/features/work-list";
import { clinicFilterState, resetClinicFilter } from "@/test/clinic-filter-mock";

const mocks = vi.hoisted(() => ({ fetchADRReviewQueue: vi.fn() }));
const query = vi.hoisted(() => ({ value: "" }));
vi.mock("@/hooks/use-clinic-filter", async () => (await import("@/test/clinic-filter-mock")).clinicFilterModule);
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(query.value) }));
vi.mock("@/services/clinicians", async (importOriginal) => ({
    ...(await importOriginal<typeof import("@/services/clinicians")>()),
    ...mocks,
}));

function makeCase(index: number, overrides: Record<string, unknown> = {}) {
    return {
        id: `adr-${index}`,
        patientId: `patient-${index}`,
        patientFirstName: `Patient${index}`,
        patientLastName: "Synthetic",
        symptomReportId: `symptom-${index}`,
        symptom: "dizziness",
        severity: 2,
        onset: null,
        symptomCreatedAt: "2026-10-02T09:52:00Z",
        suspectMedicationId: `medication-${index}`,
        suspectMedicationName: index % 2 ? "lisinopril" : "metformin",
        naranjoScore: index % 9,
        causality: index % 9 >= 5 ? "Probable" : index % 9 >= 1 ? "Possible" : "Doubtful",
        naranjoAnswers: {},
        naranjoAssessment: { missing_questions: index % 3 === 0 ? ["dose_response", "alternative_causes"] : [] },
        evidence: [{ question: "event_after_drug", answer: "yes", evidence: "Never shown in the list." }],
        status: "draft",
        requestedInformation: [],
        patientResponses: [],
        createdAt: `2026-10-${String(1 + (index % 9)).padStart(2, "0")}T09:53:00Z`,
        ...overrides,
    };
}

const cases = [
    ...Array.from({ length: 25 }, (_, index) => makeCase(index + 1)),
    makeCase(100, { status: "draft", lastReviewAction: "request_information", patientFirstName: "Waiting" }),
    makeCase(101, { status: "reviewed", patientFirstName: "Done" }),
    makeCase(102, { status: "dismissed", patientFirstName: "Dropped" }),
];

describe("ADR review queue", () => {
    beforeEach(() => {
        mocks.fetchADRReviewQueue.mockReset();
        mocks.fetchADRReviewQueue.mockResolvedValue(cases);
        query.value = "";
        window.history.replaceState(null, "", "/adr-reviews");
    });

    it("shows the clinic chip and filter only with several clinics, and filters on the server", async () => {
        mocks.fetchADRReviewQueue.mockResolvedValue([makeCase(1, { clinicId: "clinic-b", clinicName: "Bay Clinic" })]);
        resetClinicFilter();
        const { unmount } = render(<ADRReviewsPage />);
        await screen.findByRole("list", { name: "Awaiting review cases" });
        expect(screen.queryByText("Bay Clinic")).not.toBeInTheDocument();
        expect(screen.queryByLabelText("Clinic")).not.toBeInTheDocument();
        unmount();

        clinicFilterState.clinics = [
            { clinic_id: "clinic-a", clinic_code: "A", clinic_name: "City Health", role: "admin", status: "active" },
            { clinic_id: "clinic-b", clinic_code: "B", clinic_name: "Bay Clinic", role: "provider", status: "active" },
        ] as never;
        clinicFilterState.clinicId = "clinic-b";
        render(<ADRReviewsPage />);
        await screen.findByRole("list", { name: "Awaiting review cases" });
        expect(screen.getAllByText("Bay Clinic", { selector: "span" }).length).toBeGreaterThan(0);
        expect(mocks.fetchADRReviewQueue).toHaveBeenLastCalledWith({ status: "all", clinicId: "clinic-b" });
        resetClinicFilter();
    });

    it("lists 25+ cases as one compact page of rows with tab counts and no evidence", async () => {
        render(<ADRReviewsPage />);
        const list = await screen.findByRole("list", { name: "Awaiting review cases" });
        expect(mocks.fetchADRReviewQueue).toHaveBeenCalledWith({ status: "all", clinicId: null });
        expect(within(list).getAllByRole("listitem")).toHaveLength(10);
        expect(screen.queryByText("Never shown in the list.")).not.toBeInTheDocument();
        expect(screen.getByRole("tab", { name: /Awaiting review\s*25/ })).toHaveAttribute("aria-selected", "true");
        expect(screen.getByRole("tab", { name: /Information requested\s*1/ })).toBeInTheDocument();
        expect(screen.getByRole("tab", { name: /Reviewed\s*1/ })).toBeInTheDocument();
        expect(screen.getByRole("tab", { name: /Dismissed\s*1/ })).toBeInTheDocument();
        expect(screen.getByText(/Scores are decision support, not a verdict/)).toBeInTheDocument();
        expect(screen.getByText("1–10")).toBeInTheDocument();
    });

    it("sorts by score by default and opens a row as a link carrying the queue state", async () => {
        render(<ADRReviewsPage />);
        const list = await screen.findByRole("list", { name: "Awaiting review cases" });
        const first = within(list).getAllByRole("link")[0];
        expect(first).toHaveTextContent("Patient8");
        expect(first.getAttribute("href")).toBe("/adr-reviews/adr-8");
        fireEvent.change(screen.getByRole("searchbox"), { target: { value: "patient3" } });
        const link = within(screen.getByRole("list", { name: "Awaiting review cases" })).getAllByRole("link")[0];
        expect(link.getAttribute("href")).toBe(`/adr-reviews/adr-3?from=${encodeURIComponent("q=patient3")}`);
    });

    it("keeps tab, search and page in the URL so Back restores them", async () => {
        const view = render(<ADRReviewsPage />);
        await screen.findByRole("list", { name: "Awaiting review cases" });
        fireEvent.click(screen.getByRole("button", { name: "Next" }));
        expect(window.location.search).toBe("?page=2");
        expect(screen.getByText("11–20")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("tab", { name: /Reviewed/ }));
        expect(window.location.search).toBe("?tab=reviewed");
        expect((await screen.findAllByText("Done Synthetic")).length).toBeGreaterThan(0);
        view.unmount();

        query.value = "tab=dismissed";
        render(<ADRReviewsPage />);
        expect((await screen.findAllByText("Dropped Synthetic")).length).toBeGreaterThan(0);
        expect(screen.getByRole("tab", { name: /Dismissed/ })).toHaveAttribute("aria-selected", "true");
    });

    it("shows the information-requested tab, missing counts and an empty-tab sentence", async () => {
        mocks.fetchADRReviewQueue.mockResolvedValue([cases[25]]);
        query.value = "tab=information";
        render(<ADRReviewsPage />);
        expect((await screen.findAllByText("Waiting Synthetic")).length).toBeGreaterThan(0);
        fireEvent.click(screen.getByRole("tab", { name: /Awaiting review/ }));
        expect(await screen.findByText("No assessments are waiting for your review.")).toBeInTheDocument();
    });

    it("shows missing items in amber text and a dash when nothing is missing", async () => {
        mocks.fetchADRReviewQueue.mockResolvedValue([makeCase(3), makeCase(4)]);
        render(<ADRReviewsPage />);
        const list = await screen.findByRole("list", { name: "Awaiting review cases" });
        expect(within(list).getAllByText("2 items").length).toBeGreaterThan(0);
        expect(within(list).getAllByText("—").length).toBeGreaterThan(0);
    });

    it("has a stacked layout for 390 px and a grid for 1280 px, with no horizontal scroller", async () => {
        render(<ADRReviewsPage />);
        const list = await screen.findByRole("list", { name: "Awaiting review cases" });
        const row = within(list).getAllByRole("listitem")[0];
        expect(row.querySelector(".md\\:hidden")).not.toBeNull();
        expect(row.querySelector(".hidden.md\\:grid")).not.toBeNull();
        expect(list.querySelector("[class*='overflow-x-auto']")).toBeNull();
        expect(list.querySelector("[class*='min-w-[']")).toBeNull();
    });

    it("shows a skeleton while loading and a retry on failure", async () => {
        mocks.fetchADRReviewQueue.mockRejectedValueOnce(new Error("private diagnostic"));
        render(<ADRReviewsPage />);
        expect(screen.getByRole("status", { name: "Loading ADR reviews" })).toBeInTheDocument();
        expect(await screen.findByText("Unable to load ADR reviews", { selector: "h3" })).toBeInTheDocument();
        expect(screen.queryByText("private diagnostic")).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: /try again/i }));
        await waitFor(() => expect(screen.getByRole("list", { name: "Awaiting review cases" })).toBeInTheDocument());
    });
});

describe("ageLabel", () => {
    const now = new Date("2026-10-16T12:00:00Z");
    it.each([
        ["2026-10-16T11:59:30Z", "just now"],
        ["2026-10-16T11:30:00Z", "30 min"],
        ["2026-10-16T07:00:00Z", "5 h"],
        ["2026-10-13T12:00:00Z", "3 d"],
        ["not a date", "—"],
    ])("%s -> %s", (iso, expected) => expect(ageLabel(iso, now)).toBe(expected));
});
