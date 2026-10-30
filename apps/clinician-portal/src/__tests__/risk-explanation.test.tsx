import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RiskExplanationDialog } from "@/components/features/risk-explanation";
import type { PatientRiskData } from "@/services/clinicians";

const patient: PatientRiskData = {
    patient_id: "synthetic", first_name: "Demo", last_name: "Patient", risk_level: "unknown",
    adherence_score: 0, open_adr_count: 0, active_med_count: 0, recent_symptom_severity: null, last_activity: "",
    risk_explanation: {
        rule_version: "outpatient-review-priority-v1", calculated_at: "2026-10-21T12:00:00Z",
        adherence_available: false, adherence_window_days: 30, symptom_window_days: 7, factors: ["Adherence unknown"],
    },
};

describe("RiskExplanation source freshness", () => {
    it("keeps old snapshots compatible and unknown", () => {
        render(<RiskExplanationDialog patient={patient} onClose={vi.fn()} />);
        expect(screen.getByText("Source dates aren't available for this calculation.")).toBeInTheDocument();
        expect(screen.getByText(/not the last clinical review/)).toBeInTheDocument();
        const version = screen.getByText("outpatient-review-priority-v1");
        expect(version.closest("details")).not.toHaveAttribute("open");
    });

    it("distinguishes genuine source timestamps, missing data and failed reads", () => {
        render(<RiskExplanationDialog patient={{ ...patient, risk_explanation: {
            ...patient.risk_explanation!, source_freshness: [
                { source: "adherence_logs", timestamp_field: "logged_at", latest_at: "2026-10-01T09:00:00Z", status: "available" },
                { source: "symptom_reports", timestamp_field: "created_at", latest_at: null, status: "unknown" },
                { source: "adr_assessments", timestamp_field: "updated_at", latest_at: null, status: "unavailable" },
            ],
        } }} onClose={vi.fn()} />);
        expect(screen.getByText("Latest adherence response (30-day window)")).toBeInTheDocument();
        expect(screen.getByText("No dated record available")).toBeInTheDocument();
        expect(screen.getByText("Couldn't be read — refresh the dashboard")).toBeInTheDocument();
        expect(document.querySelector('time[datetime="2026-10-01T09:00:00Z"]')).toBeInTheDocument();
        expect(document.querySelector('time[datetime="2026-10-21T12:00:00Z"]')).toBeInTheDocument();
        expect(screen.getByText(/not a single point-in-time view/)).toBeInTheDocument();
        expect(screen.getByText(/not that it is current or reviewed/)).toBeInTheDocument();
    });

    it("never substitutes calculation time for invalid source dates", () => {
        render(<RiskExplanationDialog patient={{ ...patient, risk_explanation: {
            ...patient.risk_explanation!, source_freshness: [{ source: "medications", timestamp_field: "created_at", latest_at: "invalid", status: "available" }],
        } }} onClose={vi.fn()} />);
        expect(screen.getByText("No dated record available")).toBeInTheDocument();
    });
});
