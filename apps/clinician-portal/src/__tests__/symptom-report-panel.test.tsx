import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PatientTimeline } from "@/components/features/patient-timeline";
import { SymptomReportPanel } from "@/components/features/symptom-report-panel";
import {
    fetchPatientTimeline,
    fetchSymptomReport,
    markSymptomReportReviewed,
    type ClinicianSymptomReport,
} from "@/services/clinicians";

vi.mock("@/services/clinicians", () => ({
    fetchPatientTimeline: vi.fn(),
    fetchSymptomReport: vi.fn(),
    markSymptomReportReviewed: vi.fn(),
}));

const base: ClinicianSymptomReport = {
    id: "report-1", patient_id: "patient-1", symptom: "Mareo", severity: 6, onset: "Ayer", duration: null,
    body_area: null, confirmed_at: "2026-10-20T17:00:00+00:00", locale: "es-MX", timezone: "America/Los_Angeles",
    status: "shared",
    events: [
        { kind: "reported", at: "2026-10-20T17:00:00+00:00", actor_name: null },
        { kind: "shared_with_care_team", at: "2026-10-20T17:00:01+00:00", actor_name: null },
    ],
    answers: [
        { question_id: "severity", label: "Intensidad (0 a 10)", state: "answered", display: "6", wording: null, captured_at: null },
        { question_id: "course", label: "Cómo ha cambiado", state: "unknown", display: "No sé", wording: null, captured_at: null },
    ],
    summary: null, flagged_for_adr: false, related_medication_name: null,
    provenance: {
        report_id: "report-1", intake_id: "intake-1", source_message_id: "message-1", session_id: "default",
        schema_version: "symptom-report/1", library_version: "v1", submitted_status: "submitted",
        confirmed_at: "2026-10-20T17:00:00+00:00", language: "es-MX", timezone: "America/Los_Angeles", consent_recorded: true,
    },
    triage: { safety_rule_version: "triage-floor/1", safety_result: "no_existing_rule_matched", escalation_urgency: null, escalation_delivery: null, escalation_at: null },
    review: { state: "pending", reviewed_at: null, reviewed_by_name: null, care_team_id: null },
    already_reviewed: null,
};
const reviewed: ClinicianSymptomReport = {
    ...base, status: "reviewed", already_reviewed: false,
    review: { state: "reviewed", reviewed_at: "2026-10-21T01:00:00+00:00", reviewed_by_name: "Synthetic Reviewer", care_team_id: "team-1" },
};

beforeEach(() => vi.resetAllMocks());

describe("SymptomReportPanel", () => {
    it("shows confirmed answers, safety outcome, provenance and consent", async () => {
        vi.mocked(fetchSymptomReport).mockResolvedValue(base);
        render(<SymptomReportPanel patientId="patient-1" reportId="report-1" onClose={vi.fn()} />);
        expect(screen.getByRole("status")).toHaveTextContent("Loading report");
        await screen.findByText("Intensidad (0 a 10)");
        expect(screen.getByText("No sé")).toBeInTheDocument();
        expect(screen.getByText(/No existing emergency rule matched/)).toBeInTheDocument();
        expect(screen.getByText("message-1")).toBeInTheDocument();
        expect(screen.getByText("Explicit consent recorded at confirmation")).toBeInTheDocument();
        expect(screen.getByText("Awaiting review")).toBeInTheDocument();
        expect(fetchSymptomReport).toHaveBeenCalledWith("patient-1", "report-1");
    });

    it("marks reviewed once even on a double click, then shows who reviewed", async () => {
        vi.mocked(fetchSymptomReport).mockResolvedValue(base);
        let resolve!: (value: ClinicianSymptomReport) => void;
        vi.mocked(markSymptomReportReviewed).mockReturnValue(new Promise((r) => { resolve = r; }));
        const onReviewed = vi.fn();
        render(<SymptomReportPanel patientId="patient-1" reportId="report-1" onClose={vi.fn()} onReviewed={onReviewed} />);
        const button = await screen.findByRole("button", { name: "Mark reviewed" });
        fireEvent.click(button);
        fireEvent.click(button);
        expect(markSymptomReportReviewed).toHaveBeenCalledTimes(1);
        resolve(reviewed);
        await screen.findByText(/Reviewed by Synthetic Reviewer/);
        expect(screen.queryByRole("button", { name: "Mark reviewed" })).not.toBeInTheDocument();
        expect(onReviewed).toHaveBeenCalledTimes(1);
    });

    it("reports a colleague's earlier review instead of creating another", async () => {
        vi.mocked(fetchSymptomReport).mockResolvedValue(base);
        vi.mocked(markSymptomReportReviewed).mockResolvedValue({ ...reviewed, already_reviewed: true });
        render(<SymptomReportPanel patientId="patient-1" reportId="report-1" onClose={vi.fn()} />);
        fireEvent.click(await screen.findByRole("button", { name: "Mark reviewed" }));
        await screen.findByText(/Already reviewed by Synthetic Reviewer/);
    });

    it("keeps the report open and offers a retry when review fails", async () => {
        vi.mocked(fetchSymptomReport).mockResolvedValue(base);
        vi.mocked(markSymptomReportReviewed).mockRejectedValueOnce(new Error("down")).mockResolvedValueOnce(reviewed);
        render(<SymptomReportPanel patientId="patient-1" reportId="report-1" onClose={vi.fn()} />);
        fireEvent.click(await screen.findByRole("button", { name: "Mark reviewed" }));
        expect(await screen.findByRole("alert")).toHaveTextContent("Nothing was changed");
        fireEvent.click(screen.getByRole("button", { name: "Mark reviewed" }));
        await screen.findByText(/Reviewed by/);
    });

    it("never concludes anything from a failed load, and a denial shows no report", async () => {
        vi.mocked(fetchSymptomReport).mockRejectedValueOnce(new Error("403")).mockResolvedValueOnce(base);
        render(<SymptomReportPanel patientId="patient-1" reportId="other" onClose={vi.fn()} />);
        await screen.findByText("Unable to load this report");
        expect(screen.queryByRole("button", { name: "Mark reviewed" })).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: /try again|retry/i }));
        await waitFor(() => expect(screen.getByText("Intensidad (0 a 10)")).toBeInTheDocument());
    });
});

describe("timeline entry point", () => {
    it("opens the structured report from a symptom timeline event", async () => {
        vi.mocked(fetchPatientTimeline).mockResolvedValue({
            patient_id: "patient-1", retrieved_at: "2026-10-21T12:00:00Z", sources: [],
            events: [{
                id: "e1", domain: "symptom", source_table: "symptom_reports", source_id: "report-1",
                occurred_at: "2026-10-20T17:00:00Z", timestamp_label: "Recorded", title: "Patient-confirmed symptom",
                details: { symptom: "Mareo" }, source_href: "/patients/patient-1?tab=timeline#source-e1",
                destination_href: "/patients/patient-1?tab=symptoms#symptom-report-1",
            }],
        });
        vi.mocked(fetchSymptomReport).mockResolvedValue(base);
        render(<PatientTimeline patientId="patient-1" />);
        fireEvent.click(await screen.findByRole("button", { name: /Open structured report/ }));
        await screen.findByText("Intensidad (0 a 10)");
        expect(fetchSymptomReport).toHaveBeenCalledWith("patient-1", "report-1");
    });
});
