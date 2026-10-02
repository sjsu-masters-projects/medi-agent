import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MedicationCard } from "@/components/features/medication-card";
import { ObligationCard } from "@/components/features/obligation-card";

describe("Unscheduled task status", () => {
    it("does not describe an unscheduled medication as due now", () => {
        render(
            <MedicationCard
                id="synthetic"
                name="Synthetic medication"
                dosage="test"
                time=""
                status="active"
                onMarkComplete={vi.fn()}
            />,
        );
        expect(screen.getByText("Available")).toBeInTheDocument();
        expect(screen.queryByText("Due now")).not.toBeInTheDocument();
    });

    it("does not describe an event-based activity as due now", () => {
        render(
            <ObligationCard
                id="synthetic"
                description="After-walking check"
                type="monitoring"
                time=""
                status="active"
                onMarkComplete={vi.fn()}
            />,
        );
        expect(screen.getByText("Available")).toBeInTheDocument();
        expect(screen.queryByText("Due now")).not.toBeInTheDocument();
    });
});
