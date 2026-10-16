"use client";

import type { ClinicMembershipSummary } from "@/services/clinics";

const ROLE_LABELS: Record<string, string> = {
    admin: "Clinic Admin",
    nurse: "Nurse / MA",
    provider: "Provider",
};

interface ClinicPickerProps {
    clinics: ClinicMembershipSummary[];
    onChange: (clinicId: string) => void;
    /** True when the server asked for a clinic (`CLINIC_REQUIRED`) and none is chosen yet. */
    required?: boolean;
    value: string | null;
}

/**
 * A small picker for one clinic-scoped action (staff, invite codes, invitations). It shows only
 * for a clinician with several clinics; with one, the portal sends that clinic automatically.
 * It is not a global switcher: nothing else in the portal changes when it does.
 */
export function ClinicPicker({ clinics, onChange, required = false, value }: ClinicPickerProps) {
    // Suspended memberships cannot act, so they are not offered.
    const active = clinics.filter((clinic) => clinic.status === "active");
    if (active.length < 2) {
        return null;
    }

    return (
        <div className="rounded-xl border border-line bg-surface-2 px-4 py-3">
            <label className="block">
                <span className="mb-1.5 block text-[13px] font-medium text-ink-2">Clinic</span>
                <select
                    className="h-10 w-full max-w-sm rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink"
                    onChange={(event) => onChange(event.target.value)}
                    value={value ?? ""}
                >
                    {value ? null : (
                        <option disabled value="">
                            Choose a clinic
                        </option>
                    )}
                    {active.map((clinic) => (
                        <option key={clinic.clinic_id} value={clinic.clinic_id}>
                            {clinic.clinic_name} · {ROLE_LABELS[clinic.role] ?? clinic.role}
                        </option>
                    ))}
                </select>
            </label>
            <p className="mt-1.5 text-xs text-muted" role={required ? "status" : undefined}>
                {required
                    ? "You belong to more than one clinic. Choose which one this applies to."
                    : "Staff, invitations and patient invite codes belong to one clinic. Your patient lists are not affected."}
            </p>
        </div>
    );
}
