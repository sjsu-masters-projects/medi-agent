"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { HiOutlineClipboardDocument, HiOutlineMagnifyingGlass } from "react-icons/hi2";
import { useSelector } from "react-redux";
import { Badge, Button, Card, Input } from "@/components/ui";
import { api, isRetryableApiError } from "@/services/api";
import type { RootState } from "@/store/store";

const settingsTabs = ["General Profile", "Team & Roles", "Patient Invites", "Integrations (MCP)"] as const;
type SettingsTab = (typeof settingsTabs)[number];

const ROLE_OPTIONS = [
    { label: "Clinic Admin", value: "admin" },
    { label: "Provider", value: "provider" },
    { label: "Nurse / MA", value: "nurse" },
] as const;

interface StaffMember {
    id: string;
    email: string;
    first_name: string;
    last_name: string;
    role: string;
    specialty: string;
    created_at: string | null;
}

interface ClinicianProfile {
    id: string;
    email: string;
    first_name: string;
    last_name: string;
    specialty: string;
    role: string;
}

interface InviteCodePayload {
    invite_code: string | null;
    care_team_id: string | null;
}

interface InviteCodeRecord {
    care_team_id: string;
    invite_code: string | null;
    status: string;
    role: string | null;
    created_at: string | null;
    invite_expires_at: string | null;
    invite_claimed_at: string | null;
    is_expired: boolean;
    lifecycle_state: "active" | "claimed" | "inactive";
    patient: {
        id: string | null;
        first_name: string | null;
        last_name: string | null;
        email: string | null;
    } | null;
    created_by: {
        id: string;
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

function getRoleTone(role: string) {
    switch (role) {
        case "admin":
            return "bg-slate-800 text-white";
        case "nurse":
            return "bg-purple-100 text-purple-700";
        default:
            return "bg-green-100 text-blue-700";
    }
}

function getRoleLabel(role: string) {
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

    return parsed.toLocaleString(undefined, {
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

function getCreatorLabel(record: InviteCodeRecord) {
    if (!record.created_by) {
        return "—";
    }

    const first = record.created_by.first_name?.trim() || "";
    const last = record.created_by.last_name?.trim() || "";
    const fullName = `${first} ${last}`.trim();
    return fullName || record.created_by.email || "—";
}

async function withReadRetry<T>(read: () => Promise<T>): Promise<T> {
    try {
        return await read();
    } catch (error) {
        if (!isRetryableApiError(error)) {
            throw error;
        }

        await new Promise((resolve) => window.setTimeout(resolve, 250));
        return read();
    }
}

export default function SettingsPage() {
    const token = useSelector((state: RootState) => state.auth.accessToken);
    const [staffList, setStaffList] = useState<StaffMember[]>([]);
    const [clinicName, setClinicName] = useState("");
    const [clinicCode, setClinicCode] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [inviteEmail, setInviteEmail] = useState("");
    const [inviteRole, setInviteRole] = useState("provider");
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

    const loadStaff = useCallback(async () => {
        if (!token) {
            return;
        }
        try {
            const result = await withReadRetry(() =>
                api.get<{ staff: StaffMember[]; clinic_name: string; clinic_code?: string | null }>(
                    "/api/v1/staff/",
                    { token },
                ),
            );
            setStaffList(result.staff);
            setClinicName(result.clinic_name);
            setClinicCode(result.clinic_code ?? null);
        } catch (e) {
            setError(
                isRetryableApiError(e)
                    ? "Clinic settings are temporarily unavailable. Please retry."
                    : (e as Error).message,
            );
        } finally {
            setLoading(false);
        }
    }, [token]);

    useEffect(() => {
        void loadStaff();
    }, [loadStaff]);

    const loadProfile = useCallback(async () => {
        if (!token) {
            return;
        }

        try {
            const result = await withReadRetry(() => api.get<ClinicianProfile>("/api/v1/clinicians/me", { token }));
            setProfile(result);
            setFirstName(result.first_name);
            setLastName(result.last_name);
            setSpecialty(result.specialty || "");
        } catch (e) {
            setError(
                isRetryableApiError(e)
                    ? "Profile details are temporarily unavailable. Please retry."
                    : (e as Error).message,
            );
        }
    }, [token]);

    useEffect(() => {
        void loadProfile();
    }, [loadProfile]);

    const loadInviteCodes = useCallback(async () => {
        if (!token) {
            return;
        }

        setInviteCodeLoading(true);
        setError(null);

        try {
            const result = await withReadRetry(() =>
                api.get<InviteCodeListPayload>("/api/v1/clinicians/me/invite-codes", {
                    token,
                }),
            );
            const records = result.invites || [];
            setInviteRecords(records);
            const firstActiveCode = records.find((record) => record.lifecycle_state === "active")?.invite_code;
            setInviteCode(firstActiveCode ?? "");
        } catch (e) {
            setError(
                isRetryableApiError(e)
                    ? "Invite codes are temporarily unavailable. Please retry."
                    : (e as Error).message,
            );
        } finally {
            setInviteCodeLoading(false);
        }
    }, [token]);

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
            await api.post<InviteCodePayload>("/api/v1/clinicians/me/invite-code", {}, { token });
            await loadInviteCodes();
            setInviteStatus("New patient invite code generated");
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setInviteCodeLoading(false);
        }
    }, [loadInviteCodes, token]);

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
            const result = await api.post<{ status: string }>(
                "/api/v1/staff/invite",
                { email: inviteEmail, role: inviteRole },
                { token },
            );
            setInviteStatus(result.status === "added" ? "Added to clinic" : "Invitation pending");
            setInviteEmail("");
            void loadStaff();
        } catch (e) {
            setError((e as Error).message);
        }
    }

    async function handleRoleChange(memberId: string, newRole: string) {
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
            if (newRole === "admin") {
                const confirmed = window.confirm(
                    `Grant Clinic Admin access to ${fullName}? This allows full staff and clinic management.`,
                );
                if (!confirmed) {
                    return;
                }
            }

            if (member.role === "admin" && newRole !== "admin") {
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
            await api.put(`/api/v1/staff/${memberId}/role`, { role: newRole }, { token });
            await loadStaff();
            setActionMenuId(null);
        } catch (e) {
            setError((e as Error).message);
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
            await api.delete(`/api/v1/staff/${memberId}`, { token });
            await loadStaff();
            setActionMenuId(null);
        } catch (e) {
            setError((e as Error).message);
        }
    }

    async function handleCopyInviteCode(code: string | null = inviteCode) {
        if (!code || typeof navigator === "undefined" || !navigator.clipboard) {
            return;
        }

        await navigator.clipboard.writeText(code);
        setInviteStatus("Invite code copied");
    }

    async function handleCopyClinicCode() {
        if (!clinicCode || typeof navigator === "undefined" || !navigator.clipboard) {
            return;
        }
        await navigator.clipboard.writeText(clinicCode);
        setInviteStatus("Clinic code copied");
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

    const isClinicAdmin = profile?.role === "admin";
    const activeInvites = inviteRecords.filter((record) => record.lifecycle_state === "active");
    const claimedInvites = inviteRecords.filter((record) => record.lifecycle_state === "claimed");
    const inactiveInvites = inviteRecords.filter((record) => record.lifecycle_state === "inactive");
    const latestActiveInvite = activeInvites[0] ?? null;

    return (
        <div className="mx-auto max-w-7xl space-y-8">
            <div className="inline-flex rounded-xl border border-slate-200 bg-slate-100 p-1">
                {settingsTabs.map((tab) => (
                    <button
                        className={`rounded-lg px-5 py-2.5 text-sm ${tab === activeTab ? "bg-white font-semibold text-slate-900 shadow-sm" : "font-medium text-slate-600"}`}
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        type="button"
                    >
                        {tab}
                    </button>
                ))}
            </div>

            {error ? <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p> : null}
            {inviteStatus ? <p className="rounded-lg bg-green-50 px-4 py-3 text-sm text-green-700">{inviteStatus}</p> : null}

            {activeTab === "General Profile" ? (
                <div className="grid gap-6 lg:grid-cols-2">
                    <Card className="space-y-4">
                        <div className="flex items-center justify-between">
                            <h3 className="text-xl font-bold text-slate-900">Clinic Profile</h3>
                        </div>
                        <div className="space-y-4 text-sm">
                            <div>
                                <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Clinic Name</p>
                                <p className="mt-1 font-medium text-slate-900">{clinicName || "—"}</p>
                            </div>
                            <div>
                                <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Clinic Code</p>
                                <div className="mt-1 flex items-center gap-3">
                                    <p className="font-mono text-base font-semibold tracking-[0.08em] text-slate-900">
                                        {clinicCode || "Unavailable"}
                                    </p>
                                    <Button
                                        className="px-3 py-1.5 text-xs"
                                        onClick={() => void handleCopyClinicCode()}
                                        size="sm"
                                        variant="secondary"
                                    >
                                        Copy
                                    </Button>
                                </div>
                                <p className="mt-1 text-xs text-slate-500">
                                    New clinicians can join with this clinic code. Sending an invite is optional.
                                </p>
                            </div>
                        </div>
                    </Card>

                    <Card className="space-y-4">
                        <h3 className="text-xl font-bold text-slate-900">My Profile</h3>
                        <div className="space-y-4">
                            <div className="grid gap-4 md:grid-cols-2">
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
                            </div>
                            <Input
                                label="Specialty"
                                onChange={(event) => setSpecialty(event.target.value)}
                                placeholder="Family Medicine"
                                value={specialty}
                            />
                            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
                                <div>
                                    <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Role</p>
                                    <p className="mt-1 font-semibold text-slate-900">{getRoleLabel(profile?.role || "provider")}</p>
                                </div>
                                <div className="mt-3">
                                    <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Email</p>
                                    <p className="mt-1 font-medium text-slate-800">{profile?.email || "—"}</p>
                                </div>
                            </div>
                            <div className="flex items-center gap-3">
                                <Button onClick={() => void handleSaveProfile()}>{profileSaving ? "Saving…" : "Save Profile"}</Button>
                                <Button onClick={() => setActiveTab("Team & Roles")} variant="secondary">
                                    Register a doctor now
                                </Button>
                            </div>
                        </div>
                    </Card>

                    <Card className="space-y-4 lg:col-span-2">
                        <div className="flex items-center justify-between">
                            <h3 className="text-xl font-bold text-slate-900">Security</h3>
                        </div>
                        <div className="space-y-3 text-sm">
                            <div className="flex items-center justify-between rounded-lg border border-slate-200 p-4">
                                <div>
                                    <p className="font-medium text-slate-900">Multi-Factor Authentication</p>
                                    <p className="text-xs text-slate-500">Protect your account with a TOTP authenticator app.</p>
                                </div>
                                <Link
                                    className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700"
                                    href="/settings/mfa"
                                >
                                    Configure
                                </Link>
                            </div>
                        </div>
                    </Card>
                </div>
            ) : null}

            {activeTab === "Team & Roles" ? (
                <div className="space-y-8">
                    <Card className="space-y-6">
                        <div>
                            <h2 className="text-2xl font-bold text-slate-900">Invite Team Member</h2>
                            <p className="mt-1 text-sm text-slate-500">Send an email invitation to add staff to your MediAgent workspace.</p>
                        </div>
                        <div className="grid gap-4 md:grid-cols-[1.3fr_0.8fr_auto] md:items-end">
                            <Input
                                label="Email Address"
                                onChange={(event) => setInviteEmail(event.target.value)}
                                placeholder="colleague@clinic.org"
                                value={inviteEmail}
                            />
                            <label className="block">
                                <span className="mb-1 block text-sm font-bold uppercase tracking-[0.12em] text-slate-700">Role Access</span>
                                <select
                                    className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 shadow-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500"
                                    onChange={(event) => setInviteRole(event.target.value)}
                                    value={inviteRole}
                                >
                                    {ROLE_OPTIONS.map((option) => (
                                        <option key={option.value} value={option.value}>
                                            {option.label}
                                        </option>
                                    ))}
                                </select>
                            </label>
                            <Button className="h-[42px] px-6 font-semibold" onClick={handleInvite}>
                                Send Invite
                            </Button>
                        </div>
                        <p className="text-xs text-slate-500">Clinic code for self-registration is available under General Profile.</p>
                    </Card>

                    <Card className="overflow-visible px-0 py-0" padding="sm">
                        <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-6 py-5">
                            <h3 className="text-xl font-bold text-slate-900">
                                {loading ? "Loading staff..." : `Active Staff (${staffList.length})`}
                            </h3>
                            <div className="flex items-center gap-3">
                                <Button
                                    className="px-3 py-2 text-xs"
                                    onClick={() => void loadStaff()}
                                    size="sm"
                                    variant="secondary"
                                >
                                    Refresh
                                </Button>
                                <label className="relative block">
                                    <HiOutlineMagnifyingGlass className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                                    <input
                                        className="w-64 rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm text-slate-700 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500"
                                        onChange={(event) => setStaffQuery(event.target.value)}
                                        placeholder="Search team..."
                                        value={staffQuery}
                                    />
                                </label>
                            </div>
                        </div>
                        <div className="grid grid-cols-[1.6fr_1fr_1fr_0.5fr] gap-4 border-b border-slate-200 bg-slate-50 px-6 py-4 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                            <span>Name &amp; Email</span>
                            <span>Role</span>
                            <span>Status</span>
                            <span className="text-right">Actions</span>
                        </div>
                        {filteredStaffList.map((member, index) => (
                            <div
                                className={`grid grid-cols-[1.6fr_1fr_1fr_0.5fr] gap-4 px-6 py-4 ${index > 0 ? "border-t border-slate-100" : ""}`}
                                key={member.id}
                            >
                                <div className="flex items-center gap-3">
                                    <div className={`flex h-10 w-10 items-center justify-center rounded-full text-xs font-bold ${getRoleTone(member.role)}`}>
                                        {getInitials(member.first_name, member.last_name)}
                                    </div>
                                    <div>
                                        <p className="text-sm font-bold text-slate-900">
                                            {member.first_name} {member.last_name}
                                        </p>
                                        <p className="text-xs text-slate-500">{member.email}</p>
                                    </div>
                                </div>
                                <div className="flex items-center text-sm font-medium text-slate-700">
                                    {getRoleLabel(member.role)}
                                </div>
                                <div className="flex items-center">
                                    <Badge variant="success">Active</Badge>
                                </div>
                                <div className="relative flex items-center justify-end">
                                    {profile?.id && member.id === profile.id ? (
                                        <span className="text-xs font-medium text-slate-400">You</span>
                                    ) : null}
                                    <button
                                        className="rounded-md px-2 py-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600 disabled:cursor-not-allowed disabled:text-slate-300"
                                        disabled={Boolean(profile?.id && member.id === profile.id)}
                                        onClick={() => setActionMenuId(actionMenuId === member.id ? null : member.id)}
                                        title={profile?.id && member.id === profile.id ? "No actions available for your own account" : "Open actions"}
                                        type="button"
                                    >
                                        &#x22EE;
                                    </button>
                                    {actionMenuId === member.id ? (
                                        <div className="absolute right-0 top-full z-30 mt-1 w-48 rounded-lg border border-slate-200 bg-white py-1 shadow-lg">
                                            {ROLE_OPTIONS.filter((r) => r.value !== member.role).map((option) => (
                                                <button
                                                    className="block w-full px-4 py-2 text-left text-sm text-slate-700 hover:bg-slate-50"
                                                    key={option.value}
                                                    onClick={() => handleRoleChange(member.id, option.value)}
                                                    type="button"
                                                >
                                                    Change to {option.label}
                                                </button>
                                            ))}
                                            <hr className="my-1 border-slate-100" />
                                            <button
                                                className="block w-full px-4 py-2 text-left text-sm text-red-600 hover:bg-red-50"
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
                            <p className="px-6 py-8 text-center text-sm text-slate-400">No staff members yet.</p>
                        ) : null}
                    </Card>
                </div>
            ) : null}

            {activeTab === "Patient Invites" ? (
                <div className="max-w-5xl space-y-6">
                    <div className="rounded-xl border border-slate-700 bg-gradient-to-br from-slate-800 to-slate-950 p-6 text-white shadow-lg">
                        <h3 className="text-2xl font-bold">Patient Invite Codes</h3>
                        <p className="mt-2 max-w-xl text-sm text-slate-300">
                            Generate single-use codes for patient onboarding. New codes remain active until claimed, revoked, or expired.
                        </p>
                        <p className="mt-1 max-w-xl text-xs text-slate-400">
                            {isClinicAdmin
                                ? "Invite history shows clinic-wide codes and who issued each one."
                                : "Invite history shows codes created by your account."}
                        </p>
                        <div className="mt-6 flex items-center justify-between rounded-xl border border-slate-700 bg-slate-900/60 px-4 py-5">
                            <div>
                                <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Latest Active Code</p>
                                <span className="mt-1 block text-3xl font-bold tracking-[0.14em]">
                                    {inviteCodeLoading ? "LOADING" : inviteCode || "—"}
                                </span>
                                {isClinicAdmin && latestActiveInvite?.created_by ? (
                                    <p className="mt-2 text-xs text-slate-400">
                                        Issued by {getCreatorLabel(latestActiveInvite)}
                                    </p>
                                ) : null}
                            </div>
                            <button
                                className="rounded-md bg-slate-800 px-3 py-2 text-slate-300"
                                onClick={() => void handleCopyInviteCode()}
                                type="button"
                            >
                                <HiOutlineClipboardDocument className="h-5 w-5" />
                            </button>
                        </div>
                        <button
                            className="mt-3 w-full rounded-lg border border-white/25 bg-white/10 px-4 py-2 text-sm text-white hover:bg-white/15 disabled:cursor-not-allowed disabled:opacity-60"
                            disabled={inviteCodeLoading}
                            onClick={() => void handleGenerateInviteCode()}
                            type="button"
                        >
                            {inviteCodeLoading ? "Generating…" : "Generate New Invite Code"}
                        </button>
                    </div>

                    <Card className="space-y-4">
                        <div className="flex items-center justify-between">
                            <h4 className="text-lg font-bold text-slate-900">Active Codes ({activeInvites.length})</h4>
                            <p className="text-xs text-slate-500">Share these with new patients</p>
                        </div>
                        {activeInvites.length === 0 ? (
                            <p className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                                No active invite codes yet.
                            </p>
                        ) : (
                            <div className="space-y-3">
                                {activeInvites.map((record) => (
                                    <div className="rounded-lg border border-slate-200 p-4" key={record.care_team_id}>
                                        <div className="flex flex-wrap items-center justify-between gap-3">
                                            <div>
                                                <p className="text-xs uppercase tracking-[0.18em] text-slate-500">Invite Code</p>
                                                <p className="font-mono text-lg font-semibold text-slate-900">{record.invite_code || "—"}</p>
                                                {isClinicAdmin && record.created_by ? (
                                                    <p className="mt-1 text-xs text-slate-500">
                                                        Generated by {getCreatorLabel(record)}
                                                    </p>
                                                ) : null}
                                            </div>
                                            <div className="flex items-center gap-2">
                                                <Button
                                                    className="px-3 py-1.5 text-xs"
                                                    onClick={() => void handleCopyInviteCode(record.invite_code)}
                                                    size="sm"
                                                    variant="secondary"
                                                >
                                                    Copy
                                                </Button>
                                                {!record.created_by || profile?.id === record.created_by.id ? (
                                                    <Button
                                                        className="px-3 py-1.5 text-xs"
                                                        onClick={() => void handleRevokeInviteCode(record.care_team_id)}
                                                        size="sm"
                                                        variant="secondary"
                                                    >
                                                        {revokingInviteId === record.care_team_id ? "Revoking…" : "Revoke"}
                                                    </Button>
                                                ) : null}
                                            </div>
                                        </div>
                                        <div className="mt-3 grid gap-2 text-xs text-slate-600 md:grid-cols-2">
                                            <p>Created: {formatDateTime(record.created_at)}</p>
                                            <p>Expires: {formatDateTime(record.invite_expires_at)}</p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </Card>

                    <Card className="space-y-4">
                        <div className="flex items-center justify-between">
                            <h4 className="text-lg font-bold text-slate-900">Claimed Codes ({claimedInvites.length})</h4>
                            <p className="text-xs text-slate-500">Successfully linked patients</p>
                        </div>
                        {claimedInvites.length === 0 ? (
                            <p className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                                No claimed invite codes yet.
                            </p>
                        ) : (
                            <div className="space-y-3">
                                {claimedInvites.map((record) => (
                                    <div className="rounded-lg border border-slate-200 p-4" key={record.care_team_id}>
                                        <div className={`grid gap-2 text-sm text-slate-700 ${isClinicAdmin ? "md:grid-cols-4" : "md:grid-cols-3"}`}>
                                            <p>
                                                <span className="font-semibold text-slate-900">Code:</span> {record.invite_code || "—"}
                                            </p>
                                            <p>
                                                <span className="font-semibold text-slate-900">Patient:</span> {getPatientLabel(record)}
                                            </p>
                                            <p>
                                                <span className="font-semibold text-slate-900">Claimed:</span> {formatDateTime(record.invite_claimed_at)}
                                            </p>
                                            {isClinicAdmin && record.created_by ? (
                                                <p>
                                                    <span className="font-semibold text-slate-900">Generated By:</span> {getCreatorLabel(record)}
                                                </p>
                                            ) : null}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </Card>

                    <Card className="space-y-4">
                        <div className="flex items-center justify-between">
                            <h4 className="text-lg font-bold text-slate-900">Inactive Codes ({inactiveInvites.length})</h4>
                            <p className="text-xs text-slate-500">Revoked or expired history</p>
                        </div>
                        {inactiveInvites.length === 0 ? (
                            <p className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
                                No inactive codes.
                            </p>
                        ) : (
                            <div className="space-y-3">
                                {inactiveInvites.map((record) => (
                                    <div className="rounded-lg border border-slate-200 p-4" key={record.care_team_id}>
                                        <div className={`grid gap-2 text-sm text-slate-700 ${isClinicAdmin ? "md:grid-cols-4" : "md:grid-cols-3"}`}>
                                            <p>
                                                <span className="font-semibold text-slate-900">Code:</span> {record.invite_code || "—"}
                                            </p>
                                            <p>
                                                <span className="font-semibold text-slate-900">Created:</span> {formatDateTime(record.created_at)}
                                            </p>
                                            <p>
                                                <span className="font-semibold text-slate-900">Expired:</span> {record.is_expired ? "Yes" : "No"}
                                            </p>
                                            {isClinicAdmin && record.created_by ? (
                                                <p>
                                                    <span className="font-semibold text-slate-900">Generated By:</span> {getCreatorLabel(record)}
                                                </p>
                                            ) : null}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </Card>
                </div>
            ) : null}

            {activeTab === "Integrations (MCP)" ? (
                <div className="max-w-3xl">
                    <Card className="space-y-4">
                        <h3 className="text-xl font-bold text-slate-900">MCP Integrations</h3>
                        <p className="text-sm text-slate-600">
                            Configure external assistant and automation integrations for your clinic workspace.
                        </p>
                        <p className="text-sm text-slate-500">
                            Integration setup is available through backend admin tooling. This panel is read-only for now.
                        </p>
                    </Card>
                </div>
            ) : null}
        </div>
    );
}
