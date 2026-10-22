import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UploadCareTeamPicker } from "@/components/features/upload-care-team-picker";
import type { UploadCareTeamOption } from "@/types";

const cardio: UploadCareTeamOption = { care_team_id: "t1", specialty: "Cardiology", clinician_name: "Dr. Park", clinic_id: "c1", clinic_name: "Cedar Grove" };
const ortho: UploadCareTeamOption = { care_team_id: "t2", specialty: "Orthopaedics", clinician_name: "Dr. Lee", clinic_id: "c2", clinic_name: "Willow Terrace" };

function renderPicker(options: UploadCareTeamOption[], locale: "en-US" | "es-MX" = "en-US") {
    const onConfirm = vi.fn(); const onCancel = vi.fn();
    render(<UploadCareTeamPicker open locale={locale} fileName="labs.pdf" options={options} busy={false} onCancel={onCancel} onConfirm={onConfirm} />);
    return { onConfirm, onCancel };
}

describe("UploadCareTeamPicker", () => {
    afterEach(cleanup);

    it("requires a choice before uploading", () => {
        const { onConfirm } = renderPicker([cardio, ortho]);
        expect(screen.getByRole("dialog", { name: "Which care team is this for?" })).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
        expect(screen.getByRole("alert")).toHaveTextContent("Choose a care team, or “Not sure”, to continue.");
        expect(onConfirm).not.toHaveBeenCalled();
    });

    it("lists each care team and Not sure with its explanation, and returns the chosen team", () => {
        const { onConfirm } = renderPicker([cardio, ortho]);
        expect(screen.getByRole("radio", { name: "Cardiology · Dr. Park · Cedar Grove" })).toBeInTheDocument();
        expect(screen.getByText("Your care teams will decide who reviews it.")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("radio", { name: "Orthopaedics · Dr. Lee · Willow Terrace" }));
        fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
        expect(onConfirm).toHaveBeenCalledWith({ care_team_id: "t2" });
    });

    it("sends not_sure when the patient is unsure", () => {
        const { onConfirm } = renderPicker([cardio, ortho]);
        fireEvent.click(screen.getByRole("radio", { name: /Not sure/ }));
        fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
        expect(onConfirm).toHaveBeenCalledWith({ not_sure: true });
    });

    it("preselects a single care team and shows it read-only without a Not sure option", () => {
        const { onConfirm } = renderPicker([cardio]);
        const radio = screen.getByRole("radio", { name: "Cardiology · Dr. Park · Cedar Grove" });
        expect(radio).toBeChecked();
        expect(radio).toBeDisabled();
        expect(screen.queryByRole("radio", { name: /Not sure/ })).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
        expect(onConfirm).toHaveBeenCalledWith({ care_team_id: "t1" });
    });

    it("cancels", () => {
        const { onCancel } = renderPicker([cardio, ortho]);
        fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
        expect(onCancel).toHaveBeenCalled();
    });

    it("is available in es-MX (draft wording)", () => {
        renderPicker([cardio, ortho], "es-MX");
        expect(screen.getByRole("dialog", { name: "¿Para qué equipo de atención es esto?" })).toBeInTheDocument();
        expect(screen.getByText("Tus equipos de atención decidirán quién lo revisa.")).toBeInTheDocument();
    });
});
