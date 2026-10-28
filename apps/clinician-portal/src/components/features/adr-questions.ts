/**
 * The ten Naranjo questions as the clinician portal names them, and who answers each.
 * The sets mirror the backend's PATIENT_ANSWERABLE_NARANJO_QUESTIONS and
 * CLINICIAN_ANSWERABLE_NARANJO_QUESTIONS (PV-001-D); the server enforces both.
 */

export const QUESTION_LABELS: Record<string, string> = {
    alternative_causes: "Alternative causes",
    dose_response: "Dose-response relationship",
    event_after_drug: "Event followed medication",
    improved_on_dechallenge: "Improved after stopping",
    objective_evidence: "Objective evidence",
    previous_reports: "Previous conclusive reports",
    reappeared_on_rechallenge: "Reappeared after restarting",
    reappeared_with_placebo: "Reappeared with placebo",
    similar_previous_reaction: "Similar previous reaction",
    toxic_drug_concentration: "Toxic drug concentration",
};

export function questionLabel(question: string) {
    return QUESTION_LABELS[question] ?? question.replaceAll("_", " ");
}

/** Asked of the patient through Request information; always retrospective. */
export const PATIENT_ANSWERABLE_QUESTIONS = new Set([
    "event_after_drug",
    "improved_on_dechallenge",
    "reappeared_on_rechallenge",
    "dose_response",
    "similar_previous_reaction",
]);

export type ClinicianQuestion =
    | "previous_reports"
    | "alternative_causes"
    | "reappeared_with_placebo"
    | "toxic_drug_concentration"
    | "objective_evidence";

/** Recorded by an assigned clinician; never asked of a patient. In display order. */
export const CLINICIAN_QUESTIONS: ReadonlyArray<{
    question: ClinicianQuestion;
    prompt: string;
    /** The scale's points for Yes and No; "Not known" is always 0. */
    points: { yes: number; no: number };
}> = [
    {
        question: "previous_reports",
        prompt: "Are there previous conclusive reports of this reaction, for example in the product label or published literature?",
        points: { yes: 1, no: 0 },
    },
    {
        question: "alternative_causes",
        prompt: "Are there causes other than this medicine that could on their own have produced the reaction?",
        points: { yes: -1, no: 2 },
    },
    {
        question: "reappeared_with_placebo",
        prompt: "Did the reaction reappear when a placebo was given?",
        points: { yes: -1, no: 1 },
    },
    {
        question: "toxic_drug_concentration",
        prompt: "Was the medicine detected in blood or other fluids at a concentration known to be toxic?",
        points: { yes: 1, no: 0 },
    },
    {
        question: "objective_evidence",
        prompt: "Was the reaction confirmed by objective evidence, such as an examination or a test result?",
        points: { yes: 1, no: 0 },
    },
];
