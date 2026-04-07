"use client";

import { useRouter } from "next/navigation";
import { PageHeader } from "@/components/layouts";
import { Button, Card } from "@/components/ui";
import { logout } from "@/store/slices/auth-slice";
import { store } from "@/store/store";
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
    const router = useRouter();

    function handleLogout() {
        window.localStorage.removeItem("mediagent-patient-auth");
        store.dispatch(logout());
        router.replace("/login");
    }

    return (
        <div className="space-y-4 bg-gray-50 pb-8">
            <PageHeader subtitle="Personal information and linked clinicians." title="Profile" />
            <div className="space-y-4 px-5">
                <Card className="space-y-4">
                    <div>
                        <h2 className="text-lg font-semibold text-gray-900">
                            {patientProfile.firstName} {patientProfile.lastName}
                        </h2>
                        <p className="text-sm text-gray-500">{patientProfile.email}</p>
                    </div>
                    <div className="grid gap-3 text-sm text-gray-600">
                        <p>Date of birth: {patientProfile.dateOfBirth}</p>
                        <p>Preferred language: English</p>
                    </div>
                </Card>

                <Card className="space-y-3">
                    <h2 className="text-lg font-semibold text-gray-900">Care team</h2>
                    {careTeam.map((member) => (
                        <div className="rounded-lg border border-gray-200 p-4" key={member.id}>
                            <p className="font-medium text-gray-900">
                                Dr. {member.clinicianFirstName} {member.clinicianLastName}
                            </p>
                            <p className="text-sm text-gray-500">
                                {member.role} at {member.clinicName}
                            </p>
                        </div>
                    ))}
                </Card>

                <Button fullWidth onClick={handleLogout} variant="danger">
                    Sign out
                </Button>
            </div>
        </div>
    );
}
