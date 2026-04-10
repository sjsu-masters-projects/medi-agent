"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { HiOutlineClipboardDocument, HiOutlineMagnifyingGlass, HiOutlinePrinter } from "react-icons/hi2";
import { useSelector } from "react-redux";
import { Badge, Button, Card, Input } from "@/components/ui";
import { api } from "@/services/api";
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

export default function SettingsPage() {
    const token = useSelector((state: RootState) => state.auth.accessToken);
    const [staffList, setStaffList] = useState<StaffMember[]>([]);
    const [clinicName, setClinicName] = useState("");
    const [loading, setLoading] = useState(true);
    const [inviteEmail, setInviteEmail] = useState("");
    const [inviteRole, setInviteRole] = useState("provider");
    const [inviteStatus, setInviteStatus] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [actionMenuId, setActionMenuId] = useState<string | null>(null);
    const [activeTab, setActiveTab] = useState<SettingsTab>("Team & Roles");
    const [staffQuery, setStaffQuery] = useState("");
    const [inviteCode, setInviteCode] = useState<string>("");
    const [inviteCodeLoading, setInviteCodeLoading] = useState(false);

    const loadStaff = useCallback(async () => {
        if (!token) {
            return;
        }
        try {
            const result = await api.get<{ staff: StaffMember[]; clinic_name: string }>(
                "/api/v1/staff/",
                { token },
            );
            setStaffList(result.staff);
            setClinicName(result.clinic_name);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setLoading(false);
        }
    }, [token]);

    useEffect(() => {
        void loadStaff();
    }, [loadStaff]);

    useEffect(() => {
        if (!token) return;
        void handleGenerateInviteCode();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [token]);

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
        setError(null);
        try {
            await api.put(`/api/v1/staff/${memberId}/role`, { role: newRole }, { token });
            setStaffList((current) =>
                current.map((m) => (m.id === memberId ? { ...m, role: newRole } : m)),
            );
        } catch (e) {
            setError((e as Error).message);
        }
        setActionMenuId(null);
    }

    async function handleRemove(memberId: string) {
        if (!token) {
            return;
        }
        setError(null);
        try {
            await api.delete(`/api/v1/staff/${memberId}`, { token });
            setStaffList((current) => current.filter((m) => m.id !== memberId));
        } catch (e) {
            setError((e as Error).message);
        }
        setActionMenuId(null);
    }

    async function handleGenerateInviteCode() {
        if (!token) {
            return;
        }
        setInviteCodeLoading(true);
        setError(null);
        try {
            const result = await api.post<{ invite_code: string }>(
                "/api/v1/clinicians/me/invite-code",
                {},
                { token },
            );
            setInviteCode(result.invite_code);
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setInviteCodeLoading(false);
        }
    }

    async function handleCopyInviteCode() {
        if (!inviteCode || typeof navigator === "undefined" || !navigator.clipboard) {
            return;
        }
        await navigator.clipboard.writeText(inviteCode);
        setInviteStatus("Invite code copied");
    }

    const filteredStaffList = staffList.filter((member) => {
        const q = staffQuery.trim().toLowerCase();
        if (!q) return true;
        return `${member.first_name} ${member.last_name} ${member.email}`.toLowerCase().includes(q);
    });

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

            <div className="grid gap-8 xl:grid-cols-[2fr_1fr]">
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
                    </Card>

                    <Card className="overflow-hidden px-0 py-0" padding="sm">
                        <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-6 py-5">
                            <h3 className="text-xl font-bold text-slate-900">
                                {loading ? "Loading staff..." : `Active Staff (${staffList.length})`}
                            </h3>
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
                                    <button
                                        className="rounded-md px-2 py-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
                                        onClick={() => setActionMenuId(actionMenuId === member.id ? null : member.id)}
                                        type="button"
                                    >
                                        &#x22EE;
                                    </button>
                                    {actionMenuId === member.id ? (
                                        <div className="absolute right-0 top-full z-10 mt-1 w-48 rounded-lg border border-slate-200 bg-white py-1 shadow-lg">
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

                <div className="space-y-6">
                    <div className="rounded-xl border border-slate-700 bg-gradient-to-br from-slate-800 to-slate-950 p-6 text-white shadow-lg">
                        <h3 className="text-2xl font-bold">Patient Invite Code</h3>
                        <p className="mt-2 max-w-sm text-sm text-slate-300">
                            Share this unique code with patients so they can link their MediAgent mobile app to your clinic.
                        </p>
                        <div className="mt-6 flex items-center justify-between rounded-xl border border-slate-700 bg-slate-900/60 px-4 py-5">
                            <span className="text-3xl font-bold tracking-[0.14em]">
                                {inviteCodeLoading ? "LOADING" : inviteCode || "—"}
                            </span>
                            <button className="rounded-md bg-slate-800 px-3 py-2 text-slate-300" onClick={() => void handleCopyInviteCode()} type="button">
                                <HiOutlineClipboardDocument className="h-5 w-5" />
                            </button>
                        </div>
                        <button
                            className="mt-3 w-full rounded-lg border border-white/25 bg-white/10 px-4 py-2 text-sm text-white hover:bg-white/15"
                            onClick={() => void handleGenerateInviteCode()}
                            type="button"
                        >
                            {inviteCodeLoading ? "Generating…" : "Generate New Invite Code"}
                        </button>
                        <button
                            className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg border border-white/20 bg-white/10 px-4 py-3 text-sm font-medium text-white transition hover:bg-white/15"
                            type="button"
                        >
                            <HiOutlinePrinter className="h-5 w-5" />
                            <span>Print Handouts for Front Desk</span>
                        </button>
                    </div>

                    <Card className="space-y-4">
                        <div className="flex items-center justify-between">
                            <h3 className="text-xl font-bold text-slate-900">Security</h3>
                        </div>
                        <div className="space-y-3 text-sm">
                            <div className="flex items-center justify-between">
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

                    <Card className="space-y-4">
                        <div className="flex items-center justify-between">
                            <h3 className="text-xl font-bold text-slate-900">Clinic Profile</h3>
                        </div>
                        <div className="space-y-4 text-sm">
                            <div>
                                <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">Clinic Name</p>
                                <p className="mt-1 font-medium text-slate-900">{clinicName || "—"}</p>
                            </div>
                        </div>
                    </Card>
                </div>
            </div>
        </div>
    );
}
