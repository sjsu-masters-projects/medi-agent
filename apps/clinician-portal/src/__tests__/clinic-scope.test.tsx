import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ClinicChip } from "@/components/features/clinic-chip";
import { clinicScopeLabel } from "@/hooks/clinic-scope";
import type { ClinicFilter } from "@/hooks/use-clinic-filter";

const clinic = (id: string, name: string) => ({ clinic_id: id, clinic_name: name, clinic_code: null, role: "provider", status: "active" }) as never;
const filter = (clinics: unknown[], clinicId: string | null = null, ready = true): ClinicFilter => ({
    clinics: clinics as never,
    clinicId,
    clinicName: clinics.map((c) => c as { clinic_id: string; clinic_name: string }).find((c) => c.clinic_id === clinicId)?.clinic_name ?? null,
    multi: clinics.length >= 2,
    ready,
    setClinicId: () => undefined,
});

describe("clinicScopeLabel", () => {
    const two = [clinic("a", "Cedar Grove"), clinic("b", "Willow Terrace")];
    it("says All clinics for a multi-clinic clinician with no filter", () => {
        expect(clinicScopeLabel(filter(two))).toBe("All clinics");
    });
    it("names the selected clinic when filtered", () => {
        expect(clinicScopeLabel(filter(two, "b"))).toBe("Willow Terrace");
    });
    it("names nothing for a single-clinic clinician or before the clinics load", () => {
        expect(clinicScopeLabel(filter([clinic("a", "Cedar Grove")]))).toBeNull();
        expect(clinicScopeLabel(filter([], null, false))).toBeNull();
        expect(clinicScopeLabel(filter([], null, true))).toBeNull();
    });
});

describe("ClinicChip", () => {
    it("does not truncate a long clinic name and keeps it as the title", () => {
        render(<ClinicChip name="Cedar Grove Community Health Center" />);
        const chip = screen.getByText("Cedar Grove Community Health Center");
        expect(chip).toHaveAttribute("title", "Cedar Grove Community Health Center");
        expect(chip.className).not.toContain("truncate");
        expect(chip.className).not.toMatch(/max-w-\[\d+px\]/);
    });
});
