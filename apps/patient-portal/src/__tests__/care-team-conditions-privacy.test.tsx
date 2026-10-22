import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ConditionsPrivacy } from "@/components/features/conditions-privacy";

const { get, put } = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));
vi.mock("@/services/api", () => ({ api: { get, put } }));
vi.mock("react-redux", () => ({ useSelector: (select: (state: unknown) => unknown) => select({ auth: { accessToken: "token" } }) }));

const recorded_by = { specialty: "Cardiology", clinician_name: "Dr. Park", clinic_name: "Cedar Grove" };
const conditions = [
    { id: "c1", name: "Hypertension", icd10_code: null, status: "active", is_sensitive: false, recorded_by },
    { id: "c2", name: "Anxiety", icd10_code: null, status: "active", is_sensitive: true, recorded_by },
];

describe("ConditionsPrivacy", () => {
    beforeEach(() => { get.mockReset(); put.mockReset(); get.mockResolvedValue(conditions); });
    afterEach(cleanup);

    it("lists each condition with a Keep private switch and the explanation", async () => {
        render(<ConditionsPrivacy locale="en-US" />);
        const sw = await screen.findByRole("switch", { name: "Keep Hypertension private" });
        expect(sw).toHaveAttribute("aria-checked", "false");
        expect(screen.getByRole("switch", { name: "Keep Anxiety private" })).toHaveAttribute("aria-checked", "true");
        expect(screen.getAllByText("Only the care team that recorded this sees it. Medications and allergies are always shared for your safety.")).toHaveLength(2);
        expect(get).toHaveBeenCalledWith("/api/v1/care-team/patient/conditions", { token: "token" });
    });

    it("asks to confirm, then saves and announces the change", async () => {
        put.mockResolvedValue({});
        render(<ConditionsPrivacy locale="en-US" />);
        fireEvent.click(await screen.findByRole("switch", { name: "Keep Hypertension private" }));
        const dialog = screen.getByRole("dialog", { name: "Keep this condition private?" });
        expect(put).not.toHaveBeenCalled();
        fireEvent.click(within(dialog).getByRole("button", { name: "Confirm" }));
        expect(screen.getByRole("switch", { name: "Keep Hypertension private" })).toHaveAttribute("aria-checked", "true");
        await waitFor(() => expect(put).toHaveBeenCalledWith("/api/v1/care-team/patient/conditions/c1/sensitivity", { is_sensitive: true }, { token: "token" }));
        expect(await screen.findByRole("status")).toHaveTextContent("Hypertension is now private.");
    });

    it("does nothing when the confirmation is cancelled", async () => {
        render(<ConditionsPrivacy locale="en-US" />);
        fireEvent.click(await screen.findByRole("switch", { name: "Keep Hypertension private" }));
        fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
        expect(put).not.toHaveBeenCalled();
        expect(screen.getByRole("switch", { name: "Keep Hypertension private" })).toHaveAttribute("aria-checked", "false");
    });

    it("rolls the switch back and says so when the save fails", async () => {
        put.mockRejectedValue(new Error("synthetic failure"));
        render(<ConditionsPrivacy locale="en-US" />);
        fireEvent.click(await screen.findByRole("switch", { name: "Keep Hypertension private" }));
        fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Confirm" }));
        expect(await screen.findByRole("alert")).toHaveTextContent("We could not save that change. Your setting is back to what it was.");
        expect(screen.getByRole("switch", { name: "Keep Hypertension private" })).toHaveAttribute("aria-checked", "false");
    });

    it("confirms before sharing a private condition again", async () => {
        put.mockResolvedValue({});
        render(<ConditionsPrivacy locale="en-US" />);
        fireEvent.click(await screen.findByRole("switch", { name: "Keep Anxiety private" }));
        const dialog = screen.getByRole("dialog", { name: "Share this condition again?" });
        fireEvent.click(within(dialog).getByRole("button", { name: "Confirm" }));
        await waitFor(() => expect(put).toHaveBeenCalledWith("/api/v1/care-team/patient/conditions/c2/sensitivity", { is_sensitive: false }, { token: "token" }));
    });

    it("renders nothing when there are no conditions and ignores unrelated rows", async () => {
        get.mockResolvedValue([{ id: "doc", file_name: "x.pdf" }]);
        const { container } = render(<ConditionsPrivacy locale="en-US" />);
        await waitFor(() => expect(get).toHaveBeenCalled());
        expect(container).toBeEmptyDOMElement();
    });

    it("shows an inline error with retry when the list cannot load", async () => {
        get.mockRejectedValueOnce(new Error("down"));
        render(<ConditionsPrivacy locale="en-US" />);
        expect(await screen.findByRole("alert")).toHaveTextContent("Your health conditions could not be loaded.");
        fireEvent.click(screen.getByRole("button", { name: "Try again" }));
        expect(await screen.findByRole("switch", { name: "Keep Hypertension private" })).toBeInTheDocument();
    });

    it("is available in es-MX (draft wording)", async () => {
        render(<ConditionsPrivacy locale="es-MX" />);
        expect(await screen.findByRole("switch", { name: "Mantener privada: Hypertension" })).toBeInTheDocument();
        expect(screen.getByRole("heading", { name: "Condiciones de salud" })).toBeInTheDocument();
    });
});
