import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MedicationCard } from "@/components/features/medication-card";

describe("MedicationCard", () => {
    it("renders medication data and calls mark complete", () => {
        const onMarkComplete = vi.fn();
        render(
            <MedicationCard
                dosage="500mg"
                id="med-1"
                name="Metformin"
                onMarkComplete={onMarkComplete}
                status="active"
                time="08:00"
            />,
        );

        expect(screen.getByText("Metformin")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: /mark as taken/i }));
        expect(onMarkComplete).toHaveBeenCalledWith("med-1");
    });
});
