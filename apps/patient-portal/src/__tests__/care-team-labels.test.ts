import { describe, expect, it } from "vitest";
import { careTeamRoleLabel } from "@/app/(app)/profile/care-team-labels";

const labels = [
    ["assigned_provider", "Assigned care provider", "Profesional de atención asignado"],
    ["primary_care", "Primary care", "Atención primaria"],
    ["cardiologist", "Cardiology", "Cardiología"],
    ["cardiology", "Cardiology", "Cardiología"],
    ["endocrinologist", "Endocrinology", "Endocrinología"],
    ["endocrinology", "Endocrinology", "Endocrinología"],
    ["care_team_nurse", "Care team nurse", "Personal de enfermería del equipo de atención"],
    ["authorized_patient_proxy", "Authorized patient representative", "Representante autorizado del paciente"],
    ["physician", "Physician", "Profesional de medicina"],
    ["nurse_practitioner", "Nurse practitioner", "Profesional de enfermería de práctica avanzada"],
    ["physician_assistant", "Physician assistant", "Asistente médico"],
    ["registered_nurse", "Registered nurse", "Personal de enfermería titulado"],
    ["pharmacist", "Pharmacist", "Profesional de farmacia"],
    ["front_desk_admin", "Front desk staff", "Personal de recepción"],
    ["records_admin", "Records staff", "Personal de expedientes"],
];
describe("care team role labels", () => {
    it.each(labels)("localizes %s", (code, english, spanish) => {
        expect(careTeamRoleLabel(code!, "en-US")).toBe(english);
        expect(careTeamRoleLabel(code!, "es-MX")).toBe(spanish);
    });
    it.each(["unknown_private_role", "", "constructor", "__proto__"])("uses generic copy for %s", (code) => {
        expect(careTeamRoleLabel(code, "en-US")).toBe("Care team member");
        expect(careTeamRoleLabel(code, "es-MX")).toBe("Integrante del equipo de atención");
    });
    it("accepts existing readable English values without exposing untranslated text", () => {
        expect(careTeamRoleLabel("Primary Care", "es-MX")).toBe("Atención primaria");
        expect(careTeamRoleLabel(" Cardiology ", "es-MX")).toBe("Cardiología");
    });
});
