import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ExternalRecordReviews } from "@/components/features/external-record-reviews";
import AlertsPage from "@/app/(dashboard)/alerts/page";
import { fetchExternalRecordReviews, type ExternalRecordReviewsResponse } from "@/services/clinicians";

vi.mock("@/services/clinicians", () => ({ fetchExternalRecordReviews: vi.fn() }));
vi.mock("@/hooks/use-clinic-filter", () => ({ useClinicFilter: () => ({ ready: true, multi: false, clinicId: null }) }));
vi.mock("@/components/features/notification-centre", () => ({ NotificationList: () => <p>Notification-backed items</p> }));
vi.mock("@/components/features/notification-provider", () => ({ useNotificationCentre: () => ({ summary: { data: { action_item_count: 2, unread_count: 1 } } }) }));

const snapshot: ExternalRecordReviewsResponse = {
    items: [{ patient_id: "synthetic-patient", patient_name: "Synthetic Patient", clinic_id: "clinic-one", clinic_name: "First clinic", pending_count: 39,
        inspected_candidates: 39, oldest_source_captured_at: "2026-10-01T12:00:00Z", source_times_complete: true }],
    retrieved_at: "2026-10-21T12:00:00Z", page: 1, page_size: 10, assigned_patients: 12, patients_examined: 10, has_more: true, candidate_limit: 200, citation_limit: 20,
};

async function settle() { await act(async () => { await Promise.resolve(); }); }

beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(fetchExternalRecordReviews).mockResolvedValue(snapshot);
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.resetAllMocks(); vi.useRealTimers(); });

describe("External record reviews", () => {
    it("shows explicit source counts, actual capture/retrieval times and existing clinic-preserving destination", async () => {
        const { container } = render(<ExternalRecordReviews clinicId="clinic-one" ready />);
        await settle();
        expect(fetchExternalRecordReviews).toHaveBeenCalledWith(1, "clinic-one");
        expect(screen.getByText("39 pending candidates")).toBeInTheDocument();
        expect(screen.getByText(/separate from notification and unread counts/)).toBeInTheDocument();
        expect(screen.getByText(/Counts apply to this patient page only/)).toBeInTheDocument();
        expect(screen.getByText(/at most 200 candidates per patient and 20 citations/)).toBeInTheDocument();
        expect(container.querySelector('time[datetime="2026-10-01T12:00:00Z"]')).toBeInTheDocument();
        expect(container.querySelector('time[datetime="2026-10-21T12:00:00Z"]')).toBeInTheDocument();
        expect(screen.getByRole("link", { name: /Review External Records/ })).toHaveAttribute("href", "/patients/synthetic-patient?tab=imports&clinic=clinic-one");
        expect(screen.queryByRole("button", { name: /approve|reject|acknowledge/i })).not.toBeInTheDocument();
    });

    it("refreshes visible rows at 15 seconds and on focus, and retains rows on same-scope failure", async () => {
        render(<ExternalRecordReviews clinicId={null} ready />);
        await settle();
        vi.mocked(fetchExternalRecordReviews).mockRejectedValueOnce(new Error("Unavailable"));
        await act(async () => { vi.advanceTimersByTime(15000); });
        expect(screen.getByRole("alert")).toHaveTextContent("Previously retrieved rows are retained");
        expect(screen.getByText("39 pending candidates")).toBeInTheDocument();
        vi.mocked(fetchExternalRecordReviews).mockResolvedValue({ ...snapshot, items: [] });
        fireEvent(window, new Event("focus"));
        await settle();
        expect(screen.queryByRole("alert")).not.toBeInTheDocument();
        expect(screen.getByText(/No pending external record reviews among/)).toBeInTheDocument();
    });

    it("does not poll hidden tabs, resumes on visibility return and cleans up listeners/timers", async () => {
        const view = render(<ExternalRecordReviews clinicId={null} ready />);
        await settle();
        vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
        await act(async () => { vi.advanceTimersByTime(45000); });
        fireEvent(window, new Event("focus"));
        expect(fetchExternalRecordReviews).toHaveBeenCalledTimes(1);
        vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
        fireEvent(document, new Event("visibilitychange"));
        await settle();
        expect(fetchExternalRecordReviews).toHaveBeenCalledTimes(2);
        view.unmount();
        fireEvent(window, new Event("focus"));
        fireEvent(document, new Event("visibilitychange"));
        await act(async () => { vi.advanceTimersByTime(30000); });
        expect(fetchExternalRecordReviews).toHaveBeenCalledTimes(2);
    });

    it("clears the prior clinic immediately and ignores its late response", async () => {
        let old!: (value: ExternalRecordReviewsResponse) => void;
        vi.mocked(fetchExternalRecordReviews).mockImplementationOnce(() => new Promise((resolve) => { old = resolve; }));
        const view = render(<ExternalRecordReviews clinicId="clinic-one" ready />);
        vi.mocked(fetchExternalRecordReviews).mockResolvedValue({ ...snapshot, items: [] });
        view.rerender(<ExternalRecordReviews clinicId="clinic-two" ready />);
        await settle();
        await act(async () => { old(snapshot); });
        expect(screen.queryByText("Synthetic Patient")).not.toBeInTheDocument();
        expect(screen.getByText(/No pending external record reviews among/)).toBeInTheDocument();
        expect(fetchExternalRecordReviews).toHaveBeenLastCalledWith(1, "clinic-two");
    });

    it("never relabels loaded clinic rows after a failed scope change", async () => {
        const view = render(<ExternalRecordReviews clinicId="clinic-one" ready />);
        await settle();
        expect(screen.getByText("Synthetic Patient")).toBeInTheDocument();
        vi.mocked(fetchExternalRecordReviews).mockRejectedValue(new Error("Unavailable"));
        view.rerender(<ExternalRecordReviews clinicId="clinic-two" ready />);
        expect(screen.queryByText("Synthetic Patient")).not.toBeInTheDocument();
        await settle();
        expect(screen.getByRole("alert")).toHaveTextContent("Review counts are unavailable");
        expect(screen.queryByText(/No pending external record reviews/)).not.toBeInTheDocument();
    });

    it("paginates assigned patients and resets page after clinic change", async () => {
        const view = render(<ExternalRecordReviews clinicId="clinic-one" ready />);
        await settle();
        vi.mocked(fetchExternalRecordReviews).mockResolvedValue({ ...snapshot, items: [], page: 2, has_more: false, patients_examined: 2 });
        fireEvent.click(screen.getByRole("button", { name: "Next patients" }));
        await settle();
        expect(fetchExternalRecordReviews).toHaveBeenLastCalledWith(2, "clinic-one");
        expect(screen.getByRole("button", { name: "Next patients" })).toBeDisabled();
        view.rerender(<ExternalRecordReviews clinicId="clinic-two" ready />);
        await settle();
        expect(fetchExternalRecordReviews).toHaveBeenLastCalledWith(1, "clinic-two");
    });

    it("discloses incomplete oldest-source coverage without inventing a date", async () => {
        vi.mocked(fetchExternalRecordReviews).mockResolvedValue({ ...snapshot, items: [{ ...snapshot.items[0]!, oldest_source_captured_at: null, source_times_complete: false, inspected_candidates: 200, pending_count: 250 }] });
        render(<ExternalRecordReviews clinicId={null} ready />);
        await settle();
        expect(screen.getByText(/Oldest captured source inspected: Unavailable/)).toBeInTheDocument();
        expect(screen.getByText(/full queue may contain older sources/)).toBeInTheDocument();
    });

    it("waits for clinic scope and does not overlap refreshes", async () => {
        const view = render(<ExternalRecordReviews clinicId={null} ready={false} />);
        await settle();
        expect(fetchExternalRecordReviews).not.toHaveBeenCalled();
        vi.mocked(fetchExternalRecordReviews).mockImplementation(() => new Promise(() => {}));
        view.rerender(<ExternalRecordReviews clinicId={null} ready />);
        await act(async () => { vi.advanceTimersByTime(45000); });
        fireEvent(window, new Event("focus"));
        expect(fetchExternalRecordReviews).toHaveBeenCalledTimes(1);
    });

    it("appears only in Alerts Needs attention and leaves notification counts independent", async () => {
        render(<AlertsPage />);
        await settle();
        expect(screen.getByRole("region", { name: "External record reviews" })).toBeInTheDocument();
        expect(screen.getByText("2 need attention · 1 unread")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "History" }));
        expect(screen.queryByRole("region", { name: "External record reviews" })).not.toBeInTheDocument();
    });
});
