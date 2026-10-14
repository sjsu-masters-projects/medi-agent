/**
 * Synthetic Form 3500 drafts for clinician-portal tests. Every name, email and identifier
 * is invented; none describes a real person.
 */
import type { MedWatchDraft, MedWatchFormData } from "@/services/clinicians";
import { blankProduct } from "@/services/medwatch-form-3500";

export const ATTESTATION_TEXT =
    "I have reviewed this draft and its sources. Approving it makes it exportable as " +
    "Form FDA 3500. I will submit it to FDA myself; MediAgent does not submit it to " +
    "FDA. I am responsible for its content.";

export function makeForm(
    overrides: { narrative?: string; outcomes?: MedWatchFormData["section_b"]["outcomes"] } = {},
): MedWatchFormData {
    return {
        form_version: "fda-3500-2025-09",
        section_a: {
            identifier: "SP-K7QD",
            age_value: "",
            age_unit: null,
            date_of_birth: "1988-04-03",
            sex: "F",
            weight_value: "",
            weight_unit: null,
            race: [],
            hispanic_latino: false,
        },
        section_b: {
            report_types: ["adverse_event"],
            outcomes: overrides.outcomes ?? [],
            death_date: null,
            event_date: "2026-10-02",
            event_date_confirmed: false,
            report_date: null,
            narrative: overrides.narrative ?? "Dizziness (patient-reported severity 2/10).",
            tests: [],
            tests_comments: "",
            other_history: "",
        },
        section_d: {
            product_1: {
                ...blankProduct(),
                name: "fluticasone/salmeterol inhaler",
                dose: "1",
                frequency: "BID",
                route: "Respiratory (inhalation)",
                therapy_start: "2026-09-28",
            },
            product_2: null,
        },
        section_f: { others: [{ name: "albuterol", start: null, end: null }] },
        section_g: {
            first_name: "Synthetic",
            last_name: "Clinician",
            address: "",
            city: "",
            state: "",
            zip_code: "",
            country: "",
            phone: "",
            email: "clinician@example.com",
            health_professional: null,
            occupation: null,
            also_reported_to: [],
            identity_withheld: false,
        },
        mediagent_review: {
            naranjo_score: 3,
            causality: "Possible" as MedWatchFormData["mediagent_review"]["causality"],
            reportability_rationale: "Clinically significant new event.",
        },
        legacy: {},
    };
}

export function makeDraft(overrides: Partial<MedWatchDraft> = {}): MedWatchDraft {
    return {
        id: "11111111-2222-4333-8444-555555555555",
        adrAssessmentId: "adr-1",
        patientId: "patient-1",
        formData: makeForm(),
        sourceEvidence: [
            {
                field_paths: ["section_b.narrative"],
                source_type: "patient_symptom_report",
                source_id: "symptom-1",
                attribution: "Patient-reported symptom",
                excerpt: "I became dizzy after starting the inhaler.",
                citation: "symptom_reports/symptom-1",
            },
        ],
        clinicianEditedFields: [],
        status: "draft",
        createdBy: "clinician-1",
        approvedBy: null,
        approvedAt: null,
        approvalNote: null,
        revision: 1,
        exportVersion: "fda-3500-2025-09",
        createdAt: "2026-10-09T10:00:00Z",
        updatedAt: "2026-10-09T10:00:00Z",
        missingForApproval: [],
        nameWarnings: [],
        currentSubmission: null,
        submissionHistory: [],
        attestation: { version: "medwatch-3500-approval-v1", text: ATTESTATION_TEXT },
        template: { revision: "09/2025", expires: "2027-09-30", maySuperseded: false },
        pdfAvailable: true,
        discardedAt: null,
        discardReason: null,
        ...overrides,
    };
}

export function approvedDraft(overrides: Partial<MedWatchDraft> = {}): MedWatchDraft {
    return makeDraft({
        status: "reviewed",
        revision: 3,
        approvedBy: "clinician-1",
        approvedAt: "2026-10-09T18:00:00Z",
        approvalNote: "Evidence and form reviewed.",
        ...overrides,
    });
}

export function submittedDraft(overrides: Partial<MedWatchDraft> = {}): MedWatchDraft {
    const original = {
        id: "submission-1",
        submittedOn: "2026-10-10",
        method: "medwatch_online" as const,
        methodDetail: null,
        fdaReference: "MW-0000001",
        recordedBy: "clinician-1",
        recordedByName: "Dr. Synthetic Clinician",
        createdAt: "2026-10-10T17:00:00Z",
        amendsId: null,
        amendReason: null,
    };
    return approvedDraft({
        status: "submitted",
        currentSubmission: original,
        submissionHistory: [original],
        ...overrides,
    });
}
