"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useSelector } from "react-redux";
import { Badge, Button, Card, CopyButton, Input } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { api } from "@/services/api";
import {
    clinicErrorMessage,
    fetchMyClinics,
    isClinicRequiredError,
    withClinic,
    type ClinicMembershipSummary,
} from "@/services/clinics";
import type { RootState } from "@/store/store";
import { ClinicianRole } from "@/types";
import { EmailPreferences } from "@/components/features/email-preferences";
import { EmailInvitations } from "@/components/features/email-invitations";
import { ClinicPicker } from "@/components/features/clinic-picker";
import { CLINICIAN_LOCALE } from "@/utils/dates";
import { CardHeader, IconTile, cardFooterClass } from "@/components/features/settings-card";

const settingsTabs = ["General Profile", "Team & Roles", "Patient Invites", "Interoperability"] as const;
type SettingsTab = (typeof settingsTabs)[number];

const ROLE_OPTIONS = [
    { label: "Clinic Admin", value: ClinicianRole.ADMIN },
    { label: "Provider", value: ClinicianRole.PROVIDER },
    { label: "Nurse / MA", value: ClinicianRole.NURSE },
] as const;

const InviteLifecycleState = {
    ACTIVE: "active",
    CLAIMED: "claimed",
    INACTIVE: "inactive",
} as const;
type InviteLifecycleState = (typeof InviteLifecycleState)[keyof typeof InviteLifecycleState];

interface StaffMember {
    id: string;
    email: string;
    first_name: string;
    last_name: string;
    role: ClinicianRole;
    specialty: string;
    created_at: string | null;
}

interface ClinicianProfile {
    id: string;
    email: string;
    first_name: string;
    last_name: string;
    specialty: string;
    role: ClinicianRole;
}

interface InviteCodePayload {
    invite_code: string | null;
    care_team_id: string | null;
}

interface InviteCodeRecord {
    care_team_id: string;
    invite_code: string | null;
    status: string;
    role: ClinicianRole | null;
    created_at: string | null;
    invite_expires_at: string | null;
    invite_claimed_at: string | null;
    is_expired: boolean;
    lifecycle_state: InviteLifecycleState;
    patient: {
        id: string | null;
        first_name: string | null;
        last_name: string | null;
        email: string | null;
    } | null;
}

interface InviteCodeListPayload {
    invites: InviteCodeRecord[];
    counts: {
        active: number;
        claimed: number;
        inactive: number;
    };
}

function getInitials(first: string, last: string) {
    return `${first.charAt(0)}${last.charAt(0)}`.toUpperCase();
}

function getRoleTone(role: ClinicianRole) {
    switch (role) {
        case ClinicianRole.ADMIN:
            return "bg-primary-tint text-primary";
        case ClinicianRole.NURSE:
            return "bg-sunken text-ink-2";
        default:
            return "bg-[rgba(100,116,139,.1)] text-ink-2";
    }
}

const GENERAL_SECTIONS = [
    { id: "clinic-profile", label: "Clinic Profile" },
    { id: "my-profile", label: "My Profile" },
    { id: "security", label: "Security" },
    { id: "email-notices", label: "Email notices" },
] as const;
type GeneralSectionId = (typeof GENERAL_SECTIONS)[number]["id"];

const primaryButtonClass =
    "ma-press inline-flex h-[34px] items-center justify-center gap-2 rounded-[9px] bg-primary px-4 text-[13px] font-semibold text-white hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-track disabled:text-[#94A3B8]";
const secondaryButtonClass =
    "ma-press inline-flex h-[34px] items-center justify-center gap-2 rounded-[9px] border border-line-strong bg-surface px-4 text-[13px] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink disabled:cursor-not-allowed disabled:text-[#94A3B8]";
const selectClass =
    "h-[42px] w-full rounded-[10px] border border-line-strong bg-surface px-3.5 text-sm text-ink outline-none transition focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)]";

function ReadOnlyField({ label, value }: { label: string; value: ReactNode }) {
    return (
        <div>
            <p className="mb-1.5 flex items-center gap-1.5 text-[13px] font-medium text-ink-2">
                {label}
                <Icon aria-hidden="true" name="shield" className="h-3.5 w-3.5 text-muted" />
            </p>
            <p className="flex min-h-[42px] cursor-default items-center break-words rounded-[10px] border border-line bg-surface-2 px-3.5 py-2 text-sm text-muted">
                {value}
            </p>
        </div>
    );
}

function getRoleLabel(role: ClinicianRole) {
    return ROLE_OPTIONS.find((r) => r.value === role)?.label ?? role;
}

function formatDateTime(value: string | null | undefined) {
    if (!value) {
        return "—";
    }

    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
        return "—";
    }

    return parsed.toLocaleString(CLINICIAN_LOCALE, {
        dateStyle: "medium",
        timeStyle: "short",
    });
}

function getPatientLabel(record: InviteCodeRecord) {
    if (!record.patient) {
        return "—";
    }

    const first = record.patient.first_name?.trim() || "";
    const last = record.patient.last_name?.trim() || "";
    const fullName = `${first} ${last}`.trim();
    return fullName || record.patient.email || "—";
}

export default function SettingsPage() {
    const token = useSelector((state: RootState) => state.auth.accessToken);
    const [staffList, setStaffList] = useState<StaffMember[]>([]);
    const [clinicName, setClinicName] = useState("");
    const [clinicCode, setClinicCode] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [inviteEmail, setInviteEmail] = useState("");
    const [inviteRole, setInviteRole] = useState<ClinicianRole>(ClinicianRole.PROVIDER);
    const [inviteStatus, setInviteStatus] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [profileSaving, setProfileSaving] = useState(false);
    const [profile, setProfile] = useState<ClinicianProfile | null>(null);
    const [firstName, setFirstName] = useState("");
    const [lastName, setLastName] = useState("");
    const [specialty, setSpecialty] = useState("");
    const [actionMenuId, setActionMenuId] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<SettingsTab>("General Profile");
    const [staffQuery, setStaffQuery] = useState("");
    const [inviteCode, setInviteCode] = useState<string>("");
    const [inviteCodeLoading, setInviteCodeLoading] = useState(false);
    const [inviteRecords, setInviteRecords] = useState<InviteCodeRecord[]>([]);
    const [revokingInviteId, setRevokingInviteId] = useState<string | null>(null);
    // Presentational only: highlights the section navigator entry the user last chose.
    const [activeSection, setActiveSection] = useState<GeneralSectionId>("clinic-profile");
    // Clinic-scoped actions (staff, invitations, invite codes) belong to one clinic. With one
    // membership the portal sends it automatically; with several the server answers
    // CLINIC_REQUIRED and the picker below asks which one. Nothing else in the portal changes.
    const [clinics, setClinics] = useState<ClinicMembershipSummary[]>([]);
    const [clinicId, setClinicId] = useState<string | null>(null);
    const [clinicsReady, setClinicsReady] = useState(false);
    const [clinicRequired, setClinicRequired] = useState(false);
    // Staff invitations are admin-only on the server. The right is the role held at the chosen
    // clinic; the profile role is only a fallback when the clinic list could not be loaded.
    const roleAtClinic = clinics.length > 0
        ? clinics.find((clinic) => clinic.clinic_id === clinicId)?.role
        : profile?.role;
    const isClinicAdmin = roleAtClinic === ClinicianRole.ADMIN;

    useEffect(() => {
        if (!token) {
            return;
        }
        let cancelled = false;
        void (async () => {
            try {
                const result = await fetchMyClinics(token);
                if (cancelled) {
                    return;
                }
                setClinics(result.clinics);
                if (result.clinics.length === 1) {
                    setClinicId(result.clinics[0].clinic_id);
                }
            } catch {
                // The server still resolves a single clinic and asks for a choice otherwise.
            } finally {
                if (!cancelled) {
                    setClinicsReady(true);
                }
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [token]);

    const handleClinicError = useCallback((e: unknown) => {
        if (isClinicRequiredError(e)) {
            setClinicRequired(true);
            setError(null);
            return;
        }
        setError(clinicErrorMessage(e, "Something went wrong. Please try again."));
    }, []);

    const loadStaff = useCallback(async () => {
        if (!token || !clinicsReady) {
            return;
        }
        try {
            const result = await api.get<{ staff: StaffMember[]; clinic_name: string; clinic_code?: string | null }>(
                withClinic("/api/v1/staff/", clinicId),
                { token },
            );
            setClinicRequired(false);
            setStaffList(result.staff);
            setClinicName(result.clinic_name);
            setClinicCode(result.clinic_code ?? null);
        } catch (e) {
            setStaffList([]);
            handleClinicError(e);
        } finally {
            setLoading(false);
        }
    }, [clinicId, clinicsReady, handleClinicError, token]);

    useEffect(() => {
        void loadStaff();
    }, [loadStaff]);

    const loadProfile = useCallback(async () => {
        if (!token) {
            return;
        }

        try {
            const result = await api.get<ClinicianProfile>("/api/v1/clinicians/me", { token });
            setProfile(result);
            setFirstName(result.first_name);
            setLastName(result.last_name);
            setSpecialty(result.specialty || "");
        } catch (e) {
            setError((e as Error).message);
        }
    }, [token]);

    useEffect(() => {
        void loadProfile();
    }, [loadProfile]);

    const loadInviteCodes = useCallback(async () => {
        if (!token || !clinicsReady) {
            return;
        }

        setInviteCodeLoading(true);
        setError(null);

        try {
            const result = await api.get<InviteCodeListPayload>(
                withClinic("/api/v1/clinicians/me/invite-codes", clinicId),
                { token },
            );
            const records = result.invites || [];
            setInviteRecords(records);
            const firstActiveCode = records.find(
                (record) => record.lifecycle_state === InviteLifecycleState.ACTIVE,
            )?.invite_code;
            setInviteCode(firstActiveCode ?? "");
        } catch (e) {
            setInviteRecords([]);
            setInviteCode("");
            handleClinicError(e);
        } finally {
            setInviteCodeLoading(false);
        }
    }, [clinicId, clinicsReady, handleClinicError, token]);

    useEffect(() => {
        void loadInviteCodes();
    }, [loadInviteCodes]);

    const handleGenerateInviteCode = useCallback(async () => {
        if (!token) {
            return;
        }

        setInviteCodeLoading(true);
        setError(null);

        try {
            await api.post<InviteCodePayload>(
                "/api/v1/clinicians/me/invite-code",
                clinicId ? { clinic_id: clinicId } : {},
                { token },
            );
            await loadInviteCodes();
            setInviteStatus("New patient invite code generated");
        } catch (e) {
            handleClinicError(e);
        } finally {
            setInviteCodeLoading(false);
        }
    }, [clinicId, handleClinicError, loadInviteCodes, token]);

    const handleRevokeInviteCode = useCallback(
        async (careTeamId: string) => {
            if (!token) {
                return;
            }

            setRevokingInviteId(careTeamId);
            setError(null);

            try {
                await api.post(`/api/v1/clinicians/me/invite-codes/${careTeamId}/revoke`, {}, { token });
                await loadInviteCodes();
                setInviteStatus("Invite code revoked");
            } catch (e) {
                setError((e as Error).message);
            } finally {
                setRevokingInviteId(null);
            }
        },
        [loadInviteCodes, token],
    );

    async function handleInvite() {
        if (!token || !inviteEmail) {
            return;
        }
        setError(null);
        setInviteStatus(null);
        try {
            const result = await api.post<{ status: string; email_sent?: boolean }>(
                "/api/v1/staff/invite",
                { email: inviteEmail, role: inviteRole, ...(clinicId ? { clinic_id: clinicId } : {}) },
                { token },
            );
            setInviteStatus(result.status === "already_pending"
                ? "An invitation is already pending. Sending does not change clinic membership."
                : result.email_sent
                  ? "Invitation email handed to the provider; inbox delivery is not confirmed yet. Clinic access changes only after acceptance."
                  : "Invitation queued for email delivery. Clinic access changes only after acceptance.");
            setInviteEmail("");
            void loadStaff();
        } catch (e) {
            handleClinicError(e);
        }
    }

    async function handleRoleChange(memberId: string, newRole: ClinicianRole) {
        if (!token) {
            return;
        }

        if (profile?.id && memberId === profile.id) {
            setError("You cannot change your own role.");
            return;
        }

        const member = staffList.find((entry) => entry.id === memberId);
        if (!member) {
            setError("Unable to find selected staff member.");
            return;
        }

        if (member.role === newRole) {
            setActionMenuId(null);
            return;
        }

        if (typeof window !== "undefined") {
            const fullName = `${member.first_name} ${member.last_name}`.trim() || member.email;
            if (newRole === ClinicianRole.ADMIN) {
                const confirmed = window.confirm(
                    `Grant Clinic Admin access to ${fullName}? This allows full staff and clinic management.`,
                );
                if (!confirmed) {
                    return;
                }
            }

            if (member.role === ClinicianRole.ADMIN && newRole !== ClinicianRole.ADMIN) {
                const confirmed = window.confirm(
                    `Remove Clinic Admin access from ${fullName}? They will lose admin permissions.`,
                );
                if (!confirmed) {
                    return;
                }
            }
        }

        setError(null);
        try {
            await api.put(
                `/api/v1/staff/${memberId}/role`,
                { role: newRole, ...(clinicId ? { clinic_id: clinicId } : {}) },
                { token },
            );
            await loadStaff();
            setActionMenuId(null);
        } catch (e) {
            handleClinicError(e);
        }
    }

    async function handleRemove(memberId: string) {
        if (!token) {
            return;
        }

        if (profile?.id && memberId === profile.id) {
            setError("You cannot remove yourself from the clinic.");
            return;
        }

        setError(null);
        try {
            await api.delete(withClinic(`/api/v1/staff/${memberId}`, clinicId), { token });
            await loadStaff();
            setActionMenuId(null);
        } catch (e) {
            handleClinicError(e);
        }
    }

    async function handleSaveProfile() {
        if (!token) {
            return;
        }

        setProfileSaving(true);
        setError(null);
        setInviteStatus(null);

        try {
            const result = await api.put<ClinicianProfile>(
                "/api/v1/clinicians/me",
                {
                    first_name: firstName.trim(),
                    last_name: lastName.trim(),
                    specialty: specialty.trim(),
                },
                { token },
            );
            setProfile(result);
            setFirstName(result.first_name);
            setLastName(result.last_name);
            setSpecialty(result.specialty || "");
            setInviteStatus("Profile updated");
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setProfileSaving(false);
        }
    }

    const filteredStaffList = staffList.filter((member) => {
        const q = staffQuery.trim().toLowerCase();
        if (!q) return true;
        return `${member.first_name} ${member.last_name} ${member.email}`.toLowerCase().includes(q);
    });

    const activeInvites = inviteRecords.filter(
        (record) => record.lifecycle_state === InviteLifecycleState.ACTIVE,
    );
    const claimedInvites = inviteRecords.filter(
        (record) => record.lifecycle_state === InviteLifecycleState.CLAIMED,
    );
    const inactiveInvites = inviteRecords.filter(
        (record) => record.lifecycle_state === InviteLifecycleState.INACTIVE,
    );

    return (
        <div className="ma-page space-y-5">
            <div>
                <h1 className="text-2xl font-semibold tracking-[-0.02em] text-ink">Clinic settings</h1>
                {clinicName ? <p className="mt-1 text-sm text-muted">{clinicName}</p> : null}
            </div>

            <ClinicPicker clinics={clinics} onChange={setClinicId} required={clinicRequired} value={clinicId} />

            <div role="group" aria-label="Settings views" className="flex h-11 max-w-full gap-6 overflow-x-auto border-b border-line-strong">
                {settingsTabs.map((tab) => (
                    <button
                        aria-pressed={tab === activeTab}
                        className={`relative h-11 shrink-0 whitespace-nowrap text-sm transition-colors ${tab === activeTab ? "font-medium text-ink" : "text-muted hover:text-ink-2"}`}
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        type="button"
                    >
                        {tab}
                        {tab === activeTab ? (
                            <span aria-hidden="true" className="absolute inset-x-0 bottom-0 h-0.5 rounded-full bg-primary" />
                        ) : null}
                    </button>
                ))}
            </div>

            {error ? (
                <p role="alert" className="flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink">
                    <Icon aria-hidden="true" name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{error}</span>
                </p>
            ) : null}
            {inviteStatus ? (
                <p role="status" className="flex items-start gap-2.5 rounded-xl border border-ok-line bg-ok-soft px-4 py-3 text-sm text-ok-ink">
                    <Icon aria-hidden="true" name="info" className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{inviteStatus}</span>
                </p>
            ) : null}

            {activeTab === "General Profile" ? (
                <div className="ma-enter grid gap-6 xl:grid-cols-[200px_minmax(0,1fr)]">
                    <nav aria-label="Settings sections" className="hidden xl:block">
                        <ul className="sticky top-24 space-y-1">
                            {GENERAL_SECTIONS.map((section) => (
                                <li key={section.id}>
                                    <a
                                        aria-current={activeSection === section.id ? "true" : undefined}
                                        className={`flex h-9 items-center rounded-lg px-3 text-sm transition-colors ${activeSection === section.id ? "bg-sunken font-medium text-ink" : "text-muted hover:bg-surface-2 hover:text-ink-2"}`}
                                        href={`#${section.id}`}
                                        onClick={() => setActiveSection(section.id)}
                                    >
                                        {section.label}
                                    </a>
                                </li>
                            ))}
                        </ul>
                    </nav>

                    <div className="min-w-0 space-y-5">
                        <Card padding="none">
                            <div className="scroll-mt-24" id="clinic-profile">
                                <CardHeader icon="building">
                                    <h3 className="text-[15px] font-semibold text-ink">Clinic Profile</h3>
                                </CardHeader>
                                <div className="divide-y divide-line">
                                    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 px-5 py-4">
                                        <p className="text-[13px] text-muted">Clinic Name</p>
                                        <p className="text-sm font-medium text-ink">{clinicName || "—"}</p>
                                    </div>
                                    <div className="space-y-2 px-5 py-4">
                                        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
                                            <p className="text-[13px] text-muted">Clinic Code</p>
                                            <div className="flex items-center gap-2">
                                                <p className="rounded-[10px] border border-line-strong bg-surface-2 px-3 py-1.5 font-mono text-lg tracking-[0.08em] text-ink">
                                                    {clinicCode || "Unavailable"}
                                                </p>
                                                <CopyButton aria-label="Copy clinic code" value={clinicCode}>
                                                    Copy
                                                </CopyButton>
                                            </div>
                                        </div>
                                        <p className="text-[13px] text-muted">
                                            New clinicians can join with this clinic code. Sending an invite is optional.
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </Card>

                        <Card padding="none">
                            <div className="scroll-mt-24" id="my-profile">
                                <CardHeader icon="user">
                                    <h3 className="text-[15px] font-semibold text-ink">My Profile</h3>
                                </CardHeader>
                                <div className="grid gap-4 px-5 py-5 md:grid-cols-2">
                                    <Input
                                        label="First Name"
                                        onChange={(event) => setFirstName(event.target.value)}
                                        placeholder="First name"
                                        value={firstName}
                                    />
                                    <Input
                                        label="Last Name"
                                        onChange={(event) => setLastName(event.target.value)}
                                        placeholder="Last name"
                                        value={lastName}
                                    />
                                    <Input
                                        label="Specialty"
                                        onChange={(event) => setSpecialty(event.target.value)}
                                        placeholder="Family Medicine"
                                        value={specialty}
                                    />
                                    <ReadOnlyField
                                        label="Role"
                                        value={profile ? getRoleLabel(profile.role) : "Loading profile…"}
                                    />
                                    <ReadOnlyField label="Email" value={profile?.email || "—"} />
                                </div>
                                <div className={cardFooterClass}>
                                    <Button onClick={() => setActiveTab("Team & Roles")} variant="secondary">
                                        Manage team
                                    </Button>
                                    <Button disabled={profileSaving || !profile} onClick={() => void handleSaveProfile()}>{profileSaving ? "Saving…" : "Save Profile"}</Button>
                                </div>
                            </div>
                        </Card>

                        <Card padding="none">
                            <div className="scroll-mt-24" id="security">
                                <CardHeader icon="shield">
                                    <h3 className="text-[15px] font-semibold text-ink">Security</h3>
                                </CardHeader>
                                <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
                                    <div>
                                        <p className="text-sm font-medium text-ink">Multi-Factor Authentication</p>
                                        <p className="mt-0.5 text-[13px] text-muted">Protect your account with a TOTP authenticator app.</p>
                                    </div>
                                    <Link className={primaryButtonClass} href="/settings/mfa">
                                        Configure
                                    </Link>
                                </div>
                            </div>
                        </Card>
                        {token ? <EmailPreferences token={token} /> : null}
                    </div>
                </div>
            ) : null}

            {activeTab === "Team & Roles" ? (
                <div className="ma-enter space-y-5">
                    {token && isClinicAdmin ? <EmailInvitations clinicId={clinicId} token={token} revision={inviteStatus} /> : null}
                    {profile && !isClinicAdmin && !clinicRequired ? (
                        <p role="note" className="rounded-xl border border-line bg-surface-2 px-4 py-3 text-sm text-ink-2">
                            Only clinic admins can invite team members.
                        </p>
                    ) : null}
                    {isClinicAdmin ? <Card padding="none">
                        <CardHeader icon="users" sub="Send an email invitation to add staff to your MediAgent workspace.">
                            <h2 className="text-[15px] font-semibold text-ink">Invite Team Member</h2>
                        </CardHeader>
                        <div className="space-y-3 px-5 py-5">
                            <div className="grid gap-4 md:grid-cols-[minmax(0,1.3fr)_minmax(0,0.8fr)_auto] md:items-end">
                                <Input
                                    label="Email Address"
                                    onChange={(event) => setInviteEmail(event.target.value)}
                                    placeholder="colleague@clinic.org"
                                    value={inviteEmail}
                                />
                                <label className="block">
                                    <span className="mb-1.5 block text-[13px] font-medium text-ink-2">Role Access</span>
                                    <select
                                        className={selectClass}
                                        onChange={(event) => setInviteRole(event.target.value as ClinicianRole)}
                                        value={inviteRole}
                                    >
                                        {ROLE_OPTIONS.map((option) => (
                                            <option key={option.value} value={option.value}>
                                                {option.label}
                                            </option>
                                        ))}
                                    </select>
                                </label>
                                <Button onClick={handleInvite} size="lg">
                                    Send Invite
                                </Button>
                            </div>
                            <p className="text-[13px] text-muted">Clinic code for self-registration is available under General Profile.</p>
                        </div>
                    </Card> : null}

                    <Card className="overflow-visible" padding="none">
                        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
                            <div className="flex items-center gap-3">
                                <IconTile name="users" />
                                <h3 className="text-[15px] font-semibold text-ink">
                                    {loading ? "Loading staff..." : `Active Staff (${staffList.length})`}
                                </h3>
                            </div>
                            <div className="flex flex-wrap items-center gap-2">
                                <label className="relative block">
                                    <Icon aria-hidden="true" name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
                                    <input
                                        aria-label="Search team"
                                        className="h-[34px] w-64 max-w-full rounded-[9px] border border-line-strong bg-surface pl-9 pr-3 text-[13px] text-ink outline-none transition placeholder:text-[#94A3B8] focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)]"
                                        onChange={(event) => setStaffQuery(event.target.value)}
                                        placeholder="Search team..."
                                        value={staffQuery}
                                    />
                                </label>
                                <button
                                    className={secondaryButtonClass}
                                    disabled={loading}
                                    onClick={() => void loadStaff()}
                                    type="button"
                                >
                                    <Icon aria-hidden="true" name="refresh" className="h-4 w-4" />
                                    Refresh
                                </button>
                            </div>
                        </div>
                        <div className="hidden gap-4 border-b border-line px-[22px] py-3 font-mono text-[11px] uppercase tracking-[0.06em] text-muted md:grid md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1fr)_96px]">
                            <span>Name &amp; Email</span>
                            <span>Role</span>
                            <span>Status</span>
                            <span className="text-right">Actions</span>
                        </div>
                        {filteredStaffList.map((member, index) => (
                            <div
                                className={`grid grid-cols-2 items-center gap-4 px-[22px] py-4 transition-colors hover:bg-[rgba(100,116,139,.05)] md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1fr)_96px] ${index > 0 ? "border-t border-line" : ""}`}
                                key={member.id}
                            >
                                <div className="col-span-2 flex min-w-0 items-center gap-3 md:col-span-1">
                                    <div aria-hidden="true" className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full bg-track text-xs font-semibold text-ink-2">
                                        {getInitials(member.first_name, member.last_name)}
                                    </div>
                                    <div className="min-w-0 break-words">
                                        <p className="text-sm font-semibold text-ink">
                                            {member.first_name} {member.last_name}
                                        </p>
                                        <p className="text-[13px] text-muted">{member.email}</p>
                                    </div>
                                </div>
                                <div className="flex items-center">
                                    <span className={`inline-flex items-center gap-1.5 rounded-[7px] px-2 py-1 text-xs font-medium ${getRoleTone(member.role)}`}>
                                        {member.role === ClinicianRole.ADMIN ? <Icon aria-hidden="true" name="shield" className="h-3.5 w-3.5" /> : null}
                                        {getRoleLabel(member.role)}
                                    </span>
                                </div>
                                <div className="flex items-center">
                                    <Badge variant="success">Active</Badge>
                                </div>
                                <div className="relative col-span-2 flex items-center justify-end gap-2 md:col-span-1">
                                    {profile?.id && member.id === profile.id ? (
                                        <span className="text-xs font-medium text-muted">You</span>
                                    ) : null}
                                    <button
                                        aria-label={`Actions for ${member.first_name} ${member.last_name}`}
                                        aria-expanded={actionMenuId === member.id}
                                        className="ma-press flex h-8 w-8 items-center justify-center rounded-lg text-muted transition hover:bg-sunken hover:text-ink disabled:cursor-not-allowed disabled:text-[#94A3B8] disabled:hover:bg-transparent"
                                        disabled={Boolean(profile?.id && member.id === profile.id)}
                                        onClick={() => setActionMenuId(actionMenuId === member.id ? null : member.id)}
                                        title={profile?.id && member.id === profile.id ? "No actions available for your own account" : "Open actions"}
                                        type="button"
                                    >
                                        <Icon aria-hidden="true" name="more" className="h-4 w-4" />
                                    </button>
                                    {actionMenuId === member.id ? (
                                        <div className="absolute right-0 top-full z-30 mt-1 w-52 rounded-xl border border-line bg-surface p-1 shadow-[var(--shadow-pop)]">
                                            {ROLE_OPTIONS.filter((r) => r.value !== member.role).map((option) => (
                                                <button
                                                    className="block w-full rounded-lg px-3 py-2 text-left text-[13px] text-ink-2 hover:bg-surface-2 hover:text-ink"
                                                    key={option.value}
                                                    onClick={() => handleRoleChange(member.id, option.value)}
                                                    type="button"
                                                >
                                                    Change to {option.label}
                                                </button>
                                            ))}
                                            <hr className="my-1 border-line" />
                                            <button
                                                className="block w-full rounded-lg px-3 py-2 text-left text-[13px] text-risk-ink hover:bg-risk-soft"
                                                onClick={() => handleRemove(member.id)}
                                                type="button"
                                            >
                                                Remove from clinic
                                            </button>
                                        </div>
                                    ) : null}
                                </div>
                            </div>
                        ))}
                        {!loading && filteredStaffList.length === 0 ? (
                            <div className="flex flex-col items-center gap-3 px-6 py-10 text-center">
                                <span aria-hidden="true" className="flex h-12 w-12 items-center justify-center rounded-2xl bg-sunken text-muted">
                                    <Icon name="users" className="h-5 w-5" />
                                </span>
                                <p className="text-sm text-muted">No staff members yet.</p>
                            </div>
                        ) : null}
                    </Card>
                </div>
            ) : null}

            {activeTab === "Patient Invites" ? (
                <div className="ma-enter space-y-5">
                    <Card padding="none">
                        <CardHeader icon="link" sub="Invite history shows codes created by your account at this clinic.">
                            <h3 className="text-[15px] font-semibold text-ink">Patient Invite Codes</h3>
                        </CardHeader>
                        <div className="space-y-4 px-5 py-5">
                            <p className="max-w-[72ch] text-sm text-ink-2">
                                Generate single-use codes for patient onboarding. New codes remain active until claimed, revoked, or expired.
                            </p>
                            <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl bg-sunken px-5 py-4">
                                <div>
                                    <p className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">Latest Active Code</p>
                                    <span className="mt-1 block font-mono text-[28px] font-medium tracking-[0.14em] text-ink">
                                        {inviteCodeLoading ? "LOADING" : inviteCode || "—"}
                                    </span>
                                </div>
                                <CopyButton
                                    aria-label="Copy latest invite code"
                                    className="ma-press flex h-[34px] w-[34px] items-center justify-center rounded-[9px] border border-line-strong bg-surface text-ink-2 hover:bg-surface-2 hover:text-ink disabled:cursor-not-allowed disabled:text-[#94A3B8]"
                                    value={inviteCodeLoading ? "" : inviteCode}
                                >
                                    <Icon aria-hidden="true" name="file" className="h-4 w-4" />
                                </CopyButton>
                            </div>
                        </div>
                        <div className={cardFooterClass}>
                            <button
                                className={primaryButtonClass}
                                disabled={inviteCodeLoading}
                                onClick={() => void handleGenerateInviteCode()}
                                type="button"
                            >
                                <Icon aria-hidden="true" name="plus" className="h-4 w-4" />
                                {inviteCodeLoading ? "Generating…" : "Generate New Invite Code"}
                            </button>
                        </div>
                    </Card>

                    <Card padding="none">
                        <CardHeader icon="check" action={<p className="text-[13px] text-muted">Share these with new patients</p>}>
                            <h4 className="text-[15px] font-semibold text-ink">Active Codes ({activeInvites.length})</h4>
                        </CardHeader>
                        {activeInvites.length === 0 ? (
                            <p className="px-5 py-8 text-center text-sm text-muted">
                                No active invite codes yet.
                            </p>
                        ) : (
                            <div className="divide-y divide-line">
                                {activeInvites.map((record) => (
                                    <div className="flex flex-wrap items-center justify-between gap-4 px-[22px] py-4 transition-colors hover:bg-[rgba(100,116,139,.05)]" key={record.care_team_id}>
                                        <div className="min-w-0 space-y-2">
                                            <p className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">Invite Code</p>
                                            <p className="inline-block rounded-[10px] border border-line-strong bg-surface-2 px-3 py-1.5 font-mono text-lg text-ink">{record.invite_code || "—"}</p>
                                            <div className="flex flex-wrap gap-x-6 gap-y-1 text-[13px] text-ink-2">
                                                <p>Created: {formatDateTime(record.created_at)}</p>
                                                <p>Expires: {formatDateTime(record.invite_expires_at)}</p>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <CopyButton aria-label={`Copy invite code ${record.invite_code ?? ""}`.trim()} value={record.invite_code}>
                                                Copy
                                            </CopyButton>
                                            <Button
                                                onClick={() => void handleRevokeInviteCode(record.care_team_id)}
                                                size="sm"
                                                variant="danger"
                                            >
                                                {revokingInviteId === record.care_team_id ? "Revoking…" : "Revoke"}
                                            </Button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </Card>

                    <div className="grid gap-5 xl:grid-cols-2">
                        <Card padding="none">
                            <CardHeader icon="user" action={<p className="text-[13px] text-muted">Successfully linked patients</p>}>
                                <h4 className="text-[15px] font-semibold text-ink">Claimed Codes ({claimedInvites.length})</h4>
                            </CardHeader>
                            {claimedInvites.length === 0 ? (
                                <p className="px-5 py-8 text-center text-sm text-muted">
                                    No claimed invite codes yet.
                                </p>
                            ) : (
                                <div className="divide-y divide-line">
                                    {claimedInvites.map((record) => (
                                        <div className="grid gap-2 px-[22px] py-4 text-sm text-ink-2 md:grid-cols-3" key={record.care_team_id}>
                                            <p className="min-w-0 break-words">
                                                <span className="text-[13px] text-muted">Code:</span> <span className="font-mono text-ink">{record.invite_code || "—"}</span>
                                            </p>
                                            <p className="min-w-0 break-words">
                                                <span className="text-[13px] text-muted">Patient:</span> <span className="text-ink">{getPatientLabel(record)}</span>
                                            </p>
                                            <p className="min-w-0 break-words">
                                                <span className="text-[13px] text-muted">Claimed:</span> {formatDateTime(record.invite_claimed_at)}
                                            </p>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </Card>

                        <Card padding="none">
                            <CardHeader icon="history" action={<p className="text-[13px] text-muted">Revoked or expired history</p>}>
                                <h4 className="text-[15px] font-semibold text-ink">Inactive Codes ({inactiveInvites.length})</h4>
                            </CardHeader>
                            {inactiveInvites.length === 0 ? (
                                <p className="px-5 py-8 text-center text-sm text-muted">
                                    No inactive codes.
                                </p>
                            ) : (
                                <div className="divide-y divide-line">
                                    {inactiveInvites.map((record) => (
                                        <div className="grid gap-2 px-[22px] py-4 text-sm text-ink-2 md:grid-cols-3" key={record.care_team_id}>
                                            <p className="min-w-0 break-words">
                                                <span className="text-[13px] text-muted">Code:</span> <span className="font-mono text-ink">{record.invite_code || "—"}</span>
                                            </p>
                                            <p className="min-w-0 break-words">
                                                <span className="text-[13px] text-muted">Created:</span> {formatDateTime(record.created_at)}
                                            </p>
                                            <p className="min-w-0 break-words">
                                                <span className="text-[13px] text-muted">Expired:</span> {record.is_expired ? "Yes" : "No"}
                                            </p>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </Card>
                    </div>
                </div>
            ) : null}

            {activeTab === "Interoperability" ? (
                <div className="ma-enter">
                    <Card padding="none">
                        <CardHeader icon="globe">
                            <h3 className="text-[15px] font-semibold text-ink">SMART on FHIR</h3>
                        </CardHeader>
                        <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
                            <p className="max-w-[72ch] text-sm text-ink-2">
                                Import synthetic sandbox records into the clinician review queue with source-level lineage.
                            </p>
                            <Link className={secondaryButtonClass} href="/smart-import">
                                Open SMART import
                                <Icon aria-hidden="true" name="arrow" className="h-4 w-4" />
                            </Link>
                        </div>
                    </Card>
                </div>
            ) : null}
        </div>
    );
}
