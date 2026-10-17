import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ fetchMyClinics: vi.fn(), replace: vi.fn(), query: { value: "" } }));

vi.mock("next/navigation", () => ({
    usePathname: () => "/patients",
    useRouter: () => ({ replace: mocks.replace }),
    useSearchParams: () => new URLSearchParams(mocks.query.value),
}));
vi.mock("react-redux", () => ({
    useSelector: (select: (state: unknown) => unknown) => select({ auth: { accessToken: "session" } }),
}));
vi.mock("@/services/clinics", () => ({ fetchMyClinics: mocks.fetchMyClinics }));

import { ClinicChip, ClinicFilterEmpty, ClinicFilterField, LinkedAt } from "@/components/features/clinic-chip";
import { useClinicFilter } from "@/hooks/use-clinic-filter";

const clinicA = { clinic_id: "clinic-a", clinic_code: "AAA111", clinic_name: "City Health", role: "admin", status: "active" };
const clinicB = { clinic_id: "clinic-b", clinic_code: "BBB222", clinic_name: "Bay Clinic", role: "provider", status: "active" };
const suspended = { clinic_id: "clinic-c", clinic_code: "CCC333", clinic_name: "Closed Clinic", role: "provider", status: "suspended" };

function Harness() {
    const filter = useClinicFilter();
    return (
        <div>
            <p data-testid="state">{`${filter.multi}|${filter.clinicId}|${filter.ready}`}</p>
            <ClinicFilterField filter={filter} />
            {filter.clinicId ? <ClinicFilterEmpty filter={filter} /> : null}
        </div>
    );
}

describe("clinic filter", () => {
    beforeEach(() => {
        vi.resetAllMocks();
        mocks.query.value = "";
    });
    afterEach(cleanup);

    it("offers All clinics first and each active clinic with two or more clinics", async () => {
        mocks.fetchMyClinics.mockResolvedValue({ clinics: [clinicA, clinicB, suspended], default_clinic_id: "clinic-a" });
        render(<Harness />);
        const select = await screen.findByLabelText("Clinic");
        expect([...select.querySelectorAll("option")].map((option) => option.textContent)).toEqual([
            "All clinics",
            "City Health",
            "Bay Clinic",
        ]);
        expect(select).toHaveValue("");
        expect(screen.getByTestId("state")).toHaveTextContent("true|null|true");
    });

    it("shows nothing for a single-clinic clinician, even with a stale ?clinic= in the URL", async () => {
        mocks.query.value = "clinic=clinic-a";
        mocks.fetchMyClinics.mockResolvedValue({ clinics: [clinicA], default_clinic_id: "clinic-a" });
        render(<Harness />);
        await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("false|null|true"));
        expect(screen.queryByLabelText("Clinic")).not.toBeInTheDocument();
    });

    it("reads the selected clinic from the URL and ignores one the clinician does not belong to", async () => {
        mocks.query.value = "clinic=clinic-b";
        mocks.fetchMyClinics.mockResolvedValue({ clinics: [clinicA, clinicB], default_clinic_id: "clinic-a" });
        const { unmount } = render(<Harness />);
        expect(await screen.findByLabelText("Clinic")).toHaveValue("clinic-b");
        unmount();

        mocks.query.value = "clinic=someone-elses";
        render(<Harness />);
        expect(await screen.findByLabelText("Clinic")).toHaveValue("");
    });

    it("writes the choice to the URL and clears it for All clinics", async () => {
        mocks.query.value = "x=1";
        mocks.fetchMyClinics.mockResolvedValue({ clinics: [clinicA, clinicB], default_clinic_id: "clinic-a" });
        render(<Harness />);
        fireEvent.change(await screen.findByLabelText("Clinic"), { target: { value: "clinic-a" } });
        expect(mocks.replace).toHaveBeenCalledWith("/patients?x=1&clinic=clinic-a", { scroll: false });
    });

    it("says no patients match at the clinic and offers Show all clinics", async () => {
        mocks.query.value = "clinic=clinic-b";
        mocks.fetchMyClinics.mockResolvedValue({ clinics: [clinicA, clinicB], default_clinic_id: "clinic-a" });
        render(<Harness />);
        expect(await screen.findByText(/No patients at Bay Clinic match/)).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Show all clinics" }));
        expect(mocks.replace).toHaveBeenCalledWith("/patients", { scroll: false });
    });

    it("does not break when the clinic list cannot be loaded", async () => {
        mocks.fetchMyClinics.mockRejectedValue(new Error("down"));
        render(<Harness />);
        await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("false|null|true"));
        expect(screen.queryByLabelText("Clinic")).not.toBeInTheDocument();
    });
});

describe("clinic chip", () => {
    afterEach(cleanup);

    it("is a neutral truncated pill with the full name as a tooltip", () => {
        render(<ClinicChip name="City Health Group of Northern California" />);
        const chip = screen.getByText("City Health Group of Northern California");
        expect(chip).toHaveAttribute("title", "City Health Group of Northern California");
        expect(chip.className).toContain("truncate");
        expect(chip.className).toContain("bg-surface-2");
        expect(chip.className).toContain("text-[11px]");
    });

    it("renders nothing without a name, and the header line names the clinic", () => {
        const { container } = render(<><ClinicChip name={null} /><LinkedAt name={null} /></>);
        expect(container).toBeEmptyDOMElement();
        cleanup();
        render(<LinkedAt name="Bay Clinic" />);
        expect(screen.getByText(/Linked at/)).toHaveTextContent("Linked at Bay Clinic");
    });
});
