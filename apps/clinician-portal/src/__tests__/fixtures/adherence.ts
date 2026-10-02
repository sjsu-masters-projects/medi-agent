import type { PatientDeepDive } from "@/services/clinicians";

export const adherencePatient: PatientDeepDive = {
  patient_id: "synthetic-patient",
  first_name: "Test",
  last_name: "Patient",
  email: "synthetic@example.test",
  timezone: "America/Los_Angeles",
  risk_level: "unknown",
  adherence_score: 0.5,
  medications: [
    {
      id: "med-1",
      patientId: "synthetic-patient",
      name: "Synthetic medication",
      dosage: "500 mg",
      frequency: "once daily",
      route: "oral",
      isActive: true,
      createdAt: "2026-10-01T00:00:00Z",
    },
  ],
  adherence_series: [
    { date: "2026-09-30", score: 0, completed: 0, expected: 0 },
    { date: "2026-10-01", score: 0, completed: 0, expected: 1 },
    { date: "2026-10-02", score: 0.5, completed: 1, expected: 2 },
  ],
  adherence_barriers: [
    {
      target_type: "obligation",
      target_id: "walk",
      barrier_code: "schedule",
      notes: "Synthetic scheduling barrier",
      logged_at: "2026-10-02T08:00:00Z",
    },
    {
      target_type: "medication",
      target_id: "old-med",
      barrier_code: "cost",
      logged_at: "2026-10-01T08:00:00Z",
    },
  ],
  obligations: [
    {
      id: "walk",
      description: "Synthetic walking activity",
      obligation_type: "exercise",
      frequency: "three times per week",
      is_active: true,
    },
  ],
  symptom_reports: [],
  chat_messages: [],
  conditions: [],
  allergies: [],
  documents: [],
};
