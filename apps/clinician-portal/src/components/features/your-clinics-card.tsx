"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, Button, Card, CopyButton, Modal } from "@/components/ui";
import { CardHeader } from "@/components/features/settings-card";
import { api } from "@/services/api";
import {
    clinicErrorMessage,
    fetchMyClinics,
    leaveClinic,
    setDefaultClinic,
    withClinic,
    type ClinicMembershipSummary,
} from "@/services/clinics";
import { ClinicianRole } from "@/types";

const ROLE_LABELS: Record<string, string> = {
    admin: "Clinic Admin",
    nurse: "Nurse / MA",
    provider: "Provider",
};

interface YourClinicsCardProps {
    /** Called after a change so the rest of Settings reloads (default clinic, picker, team). */
    onChanged: () => void;
    /** Changes when another part of Settings changed a clinic (a rename), to reload the list. */
    revision?: number;
    token: string;
}

/**
 * Every clinic the clinician belongs to, with the role held there. "Make default" changes only
 * which clinic is preselected; "Leave" ends the membership and the clinician's own patient links
 * at that clinic. Both are audited on the server.
 */
export function YourClinicsCard({ onChanged, revision = 0, token }: YourClinicsCardProps) {
    const [clinics, setClinics] = useState<ClinicMembershipSummary[]>([]);
    const [defaultId, setDefaultId] = useState<string | null>(null);
    // Clinic ids where the caller is the only active admin, so Leave can say why it is disabled.
    const [soleAdminAt, setSoleAdminAt] = useState<Set<string>>(new Set());
    const [loaded, setLoaded] = useState(false);
    const [busyId, setBusyId] = useState<string | null>(null);
    const [leaving, setLeaving] = useState<ClinicMembershipSummary | null>(null);
    const [message, setMessage] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        try {
            const result = await fetchMyClinics(token);
            const active = result.clinics.filter((clinic) => clinic.status === "active");
            setClinics(active);
            setDefaultId(result.default_clinic_id);
            const sole = new Set<string>();
            await Promise.all(
                active
                    .filter((clinic) => clinic.role === ClinicianRole.ADMIN)
                    .map(async (clinic) => {
                        try {
                            const staff = await api.get<{ staff: { id: string; role: ClinicianRole }[] }>(
                                withClinic("/api/v1/staff/", clinic.clinic_id),
                                { token },
                            );
                            if (staff.staff.filter((member) => member.role === ClinicianRole.ADMIN).length <= 1) {
                                sole.add(clinic.clinic_id);
                            }
                        } catch {
                            // The server still refuses leaving as the only admin.
                        }
                    }),
            );
            setSoleAdminAt(sole);
        } catch (loadError) {
            setError(clinicErrorMessage(loadError, "Could not load your clinics."));
        } finally {
            setLoaded(true);
        }
    }, [token]);

    useEffect(() => {
        void load();
    }, [load, revision]);

    async function makeDefault(clinic: ClinicMembershipSummary) {
        setBusyId(clinic.clinic_id);
        setError(null);
        setMessage(null);
        try {
            await setDefaultClinic(token, clinic.clinic_id);
            setMessage(`${clinic.clinic_name} is now your default clinic.`);
            await load();
            onChanged();
        } catch (changeError) {
            setError(clinicErrorMessage(changeError, "Could not change your default clinic."));
        } finally {
            setBusyId(null);
        }
    }

    async function confirmLeave() {
        if (!leaving) {
            return;
        }
        setBusyId(leaving.clinic_id);
        setError(null);
        setMessage(null);
        try {
            await leaveClinic(token, leaving.clinic_id);
            setMessage(`You left ${leaving.clinic_name}.`);
            setLeaving(null);
            await load();
            onChanged();
        } catch (leaveError) {
            setLeaving(null);
            setError(clinicErrorMessage(leaveError, "Could not leave this clinic."));
        } finally {
            setBusyId(null);
        }
    }

    if (!loaded && clinics.length === 0) {
        return null;
    }

    return (
        <Card padding="none">
            <div className="scroll-mt-24" id="your-clinics">
                <CardHeader icon="building" sub="Your role differs by clinic. Patients stay linked to the clinic they joined.">
                    <h3 className="text-[15px] font-semibold text-ink">Your clinics</h3>
                </CardHeader>
                {error ? (
                    <p className="border-b border-line px-5 py-3 text-sm text-risk-ink" role="alert">{error}</p>
                ) : null}
                {message ? (
                    <p className="border-b border-line px-5 py-3 text-sm text-ok-ink" role="status">{message}</p>
                ) : null}
                <ul className="divide-y divide-line">
                    {clinics.map((clinic) => {
                        const isDefault = clinic.clinic_id === defaultId;
                        const isAdmin = clinic.role === ClinicianRole.ADMIN;
                        const onlyClinic = clinics.length < 2;
                        const soleAdmin = isAdmin && soleAdminAt.has(clinic.clinic_id);
                        const leaveReason = onlyClinic
                            ? "This is your only clinic."
                            : soleAdmin
                              ? "You're the only admin here."
                              : null;
                        return (
                            <li className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-5 py-3.5" key={clinic.clinic_id}>
                                <div className="min-w-0 space-y-1">
                                    <div className="flex flex-wrap items-center gap-2">
                                        <p className="min-w-0 break-words text-sm font-semibold text-ink">{clinic.clinic_name}</p>
                                        <span className="inline-flex items-center rounded-[7px] bg-[rgba(100,116,139,.1)] px-2 py-0.5 text-xs font-medium text-ink-2">
                                            {ROLE_LABELS[clinic.role] ?? clinic.role}
                                        </span>
                                        {isDefault ? <Badge variant="info">Default</Badge> : null}
                                    </div>
                                    {isAdmin ? (
                                        <div className="flex items-center gap-2 text-[13px] text-muted">
                                            <span>Clinic code</span>
                                            <span className="font-mono text-ink-2">{clinic.clinic_code}</span>
                                            <CopyButton aria-label={`Copy clinic code for ${clinic.clinic_name}`} value={clinic.clinic_code}>
                                                Copy
                                            </CopyButton>
                                        </div>
                                    ) : null}
                                    {leaveReason ? <p className="text-xs text-muted">{leaveReason}</p> : null}
                                </div>
                                <div className="flex items-center gap-1.5">
                                    {isDefault ? null : (
                                        <Button
                                            aria-label={`Make ${clinic.clinic_name} your default clinic`}
                                            disabled={busyId !== null}
                                            onClick={() => void makeDefault(clinic)}
                                            size="sm"
                                            variant="ghost"
                                        >
                                            Make default
                                        </Button>
                                    )}
                                    <Button
                                        aria-label={`Leave ${clinic.clinic_name}`}
                                        disabled={busyId !== null || leaveReason !== null}
                                        onClick={() => setLeaving(clinic)}
                                        size="sm"
                                        title={leaveReason ?? undefined}
                                        variant="danger"
                                    >
                                        Leave
                                    </Button>
                                </div>
                            </li>
                        );
                    })}
                </ul>
            </div>
            <Modal
                onClose={() => {
                    if (busyId === null) {
                        setLeaving(null);
                    }
                }}
                open={leaving !== null}
                title={leaving ? `Leave ${leaving.clinic_name}?` : "Leave clinic"}
            >
                <p className="text-sm text-ink-2">
                    Your patient links and unused invite codes at {leaving?.clinic_name} will end, so you will no longer
                    see those patients, their messages or their reviews. Nothing is deleted, and your other clinics are
                    not affected.
                </p>
                <div className="mt-5 flex flex-wrap justify-end gap-2">
                    <Button disabled={busyId !== null} onClick={() => setLeaving(null)} variant="secondary">
                        Cancel
                    </Button>
                    <Button
                        className="!border-risk-strong !bg-risk-strong !text-white hover:!bg-risk"
                        disabled={busyId !== null}
                        onClick={() => void confirmLeave()}
                    >
                        {busyId !== null ? "Leaving…" : `Leave ${leaving?.clinic_name ?? "clinic"}`}
                    </Button>
                </div>
            </Modal>
        </Card>
    );
}
