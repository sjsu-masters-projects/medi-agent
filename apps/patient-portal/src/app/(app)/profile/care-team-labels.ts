import type { Locale } from "@/types";

const ROLE_LABELS: Record<string, [string, string]> = {
    assigned_provider: ["Assigned care provider", "Profesional de atención asignado"],
    primary_care: ["Primary care", "Atención primaria"],
    cardiologist: ["Cardiology", "Cardiología"],
    cardiology: ["Cardiology", "Cardiología"],
    endocrinologist: ["Endocrinology", "Endocrinología"],
    endocrinology: ["Endocrinology", "Endocrinología"],
    care_team_nurse: ["Care team nurse", "Personal de enfermería del equipo de atención"],
    authorized_patient_proxy: ["Authorized patient representative", "Representante autorizado del paciente"],
    physician: ["Physician", "Profesional de medicina"],
    nurse_practitioner: ["Nurse practitioner", "Profesional de enfermería de práctica avanzada"],
    physician_assistant: ["Physician assistant", "Asistente médico"],
    registered_nurse: ["Registered nurse", "Personal de enfermería titulado"],
    pharmacist: ["Pharmacist", "Profesional de farmacia"],
    front_desk_admin: ["Front desk staff", "Personal de recepción"],
    records_admin: ["Records staff", "Personal de expedientes"],
};

export function careTeamRoleLabel(role: string, locale: Locale): string {
    const code = role.trim().toLowerCase().replace(/\s+/g, "_");
    const labels = Object.hasOwn(ROLE_LABELS, code)
        ? ROLE_LABELS[code] : ["Care team member", "Integrante del equipo de atención"];
    return labels![locale === "es-MX" ? 1 : 0]!;
}
