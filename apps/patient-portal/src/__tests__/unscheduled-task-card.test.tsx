import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MedicationCard } from "@/components/features/medication-card";
import { ObligationCard } from "@/components/features/obligation-card";

describe("Unscheduled task status", () => {
    it.each([
        ["active", "", "Disponible"], ["active", "08:00", "Para ahora"],
        ["upcoming", "08:00", "Próxima"], ["completed", "", "Completada"],
        ["missed", "08:00", "No realizada"], ["skipped", "", "Dificultad reportada"],
    ] as const)("localizes %s medication and activity status for time %s", (status, time, label) => {
        render(<><MedicationCard locale="es-MX" id="synthetic-med" name="Source medication" dosage="500 mg" instructions="Source medication instruction" time={time} status={status} onMarkComplete={vi.fn()} /><ObligationCard locale="es-MX" id="synthetic-activity" description="Source activity" instructions="Source activity instruction" type="custom" time={time} status={status} onMarkComplete={vi.fn()} /></>);
        expect(screen.getAllByText(label)).toHaveLength(2);
        expect(screen.getByText("Source medication instruction")).toBeInTheDocument();
        expect(screen.getByText("Source activity instruction")).toBeInTheDocument();
    });

    it.each([
        ["custom", "Actividad de atención", "Atención"], ["diet", "Actividad de nutrición", "Nutrición"],
        ["exercise", "Actividad de movimiento", "Movimiento"], ["hydration", "Actividad de hidratación", "Hidratación"],
        ["monitoring", "Control de salud", "Control"], ["follow_up", "Actividad de seguimiento", "Seguimiento"],
    ] as const)("localizes the %s activity fallback and type", (type, activity, badge) => {
        render(<ObligationCard locale="es-MX" id="synthetic" description="Source title" type={type} time="" status="active" onMarkComplete={vi.fn()} />);
        expect(screen.getByText(activity)).toBeInTheDocument();
        expect(screen.getByText(badge)).toBeInTheDocument();
    });

    it("localizes provider copy and preserves medication actions and submitting guards", () => {
        const complete = vi.fn();
        const barrier = vi.fn();
        const props = { locale: "es-MX" as const, id: "synthetic", name: "Source medication", dosage: "500 mg", time: "", status: "active" as const, onMarkComplete: complete, onReportBarrier: barrier };
        const { rerender } = render(<MedicationCard {...props} prescriber="Dr. Synthetic" />);
        expect(screen.getByText("Recetado por Dr. Synthetic")).toBeInTheDocument();
        expect(screen.getByText("Toma según la receta.")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Marcar como tomado" }));
        fireEvent.click(screen.getByRole("button", { name: "No pude hacer esto" }));
        expect(complete).toHaveBeenCalledWith("synthetic");
        expect(barrier).toHaveBeenCalledWith("synthetic");
        rerender(<MedicationCard {...props} approvedBy="Dr. Synthetic" submitting />);
        expect(screen.getByText("Plan de atención aprobado por Dr. Synthetic")).toBeInTheDocument();
        expect(screen.queryByText("Recetado por Dr. Synthetic")).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Marcar como tomado" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "No pude hacer esto" })).toBeDisabled();
    });

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
