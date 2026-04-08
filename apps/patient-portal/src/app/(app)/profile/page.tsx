"use client";

import { useRouter } from "next/navigation";
import { useDispatch } from "react-redux";
import { PageHeader } from "@/components/layouts";
import { Badge, Button, Card } from "@/components/ui";
import { logout } from "@/store/slices/auth-slice";
import type { AppDispatch } from "@/store/store";
import type { CareTeamMember, Patient } from "@/types";

const patientProfile: Patient = {
    createdAt: "2026-01-10T00:00:00Z",
    dateOfBirth: "1985-03-15",
    email: "sarah@example.com",
    firstName: "Sarah",
    id: "demo-patient",
    lastName: "Johnson",
    preferredLanguage: "en",
};

const careTeam: CareTeamMember[] = [
    {
        clinicName: "City Health",
        clinicianFirstName: "Emily",
        clinicianId: "provider-1",
        clinicianLastName: "Smith",
        createdAt: "2026-01-10T00:00:00Z",
        id: "care-team-1",
        patientId: "demo-patient",
        role: "Primary Care",
        status: "active",
    },
];

export default function ProfilePage() {
    const dispatch = useDispatch<AppDispatch>();
    const router = useRouter();

    function handleLogout() {
        window.localStorage.removeItem("mediagent-patient-auth");
        dispatch(logout());
        router.replace("/login");
    }

    return (
        <div className="space-y-4 bg-gray-50 pb-8">
            <PageHeader subtitle="Personal information and linked clinicians." title="Profile" />
            <div className="-mt-4 space-y-4 px-5">
                <Card className="overflow-hidden border-sky-100 bg-gradient-to-br from-sky-600 to-sky-700 text-white shadow-lg shadow-sky-100">
                    <div className="flex items-center gap-4">
                        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-white/20 text-2xl font-semibold">
                            S
                        </div>
                        <div className="min-w-0">
                            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-100">Patient account</p>
                            <h2 className="truncate text-xl font-semibold text-white">
                                {patientProfile.firstName} {patientProfile.lastName}
                            </h2>
                            <p className="mt-1 text-sm text-sky-100">{patientProfile.email}</p>
                        </div>
                    </div>
                </Card>

                <Card className="space-y-4">
                    <div className="flex items-center justify-between gap-3">
                        <div>
                            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Profile details</p>
                            <h3 className="mt-1 text-lg font-semibold text-slate-900">Personal information</h3>
                        </div>
                        <Badge variant="info">Active</Badge>
                    </div>
                    <div className="grid gap-3 text-sm text-slate-600">
                        <div className="rounded-2xl bg-slate-50 px-4 py-3">
                            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Date of birth</p>
                            <p className="mt-1 font-medium text-slate-800">{patientProfile.dateOfBirth}</p>
                        </div>
                        <div className="rounded-2xl bg-slate-50 px-4 py-3">
                            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Preferred language</p>
                            <p className="mt-1 font-medium text-slate-800">English</p>
                        </div>
                    </div>
                </Card>

                <Card className="space-y-3">
                    <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Connected clinic</p>
                        <h3 className="mt-1 text-lg font-semibold text-slate-900">Care team</h3>
                    </div>
                    {careTeam.map((member) => (
                        <div className="rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4" key={member.id}>
                            <div className="flex items-start justify-between gap-3">
                                <div>
                                    <p className="font-medium text-slate-900">
                                        Dr. {member.clinicianFirstName} {member.clinicianLastName}
                                    </p>
                                    <p className="mt-1 text-sm text-slate-500">{member.role}</p>
                                </div>
                                <Badge variant="success">Linked</Badge>
                            </div>
                            <p className="mt-3 text-sm text-slate-500">{member.clinicName}</p>
                        </div>
                    ))}
                </Card>

                <Card className="space-y-3 border-red-100 bg-red-50/70">
                    <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-red-400">Account</p>
                        <h3 className="mt-1 text-lg font-semibold text-slate-900">Sign out safely</h3>
                        <p className="mt-1 text-sm text-slate-600">
                            Use this if you are on a shared phone or finished reviewing your care plan.
                        </p>
                    </div>
                    <Button fullWidth onClick={handleLogout} variant="danger">
                        Sign out
                    </Button>
                </Card>
            </div>
        </div>
    );
}
