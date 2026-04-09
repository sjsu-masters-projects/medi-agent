"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { HiOutlineBuildingOffice2 } from "react-icons/hi2";
import { useDispatch, useSelector } from "react-redux";
import { PageHeader } from "@/components/layouts";
import { api } from "@/services/api";
import { clearStoredSession } from "@/services/auth-session";
import { Badge, Button, Card, EmptyState, ErrorState, Input, Skeleton } from "@/components/ui";
import { logout } from "@/store/slices/auth-slice";
import type { AppDispatch, RootState } from "@/store/store";
import type { CareTeamMember, Language, Patient } from "@/types";

interface PatientProfileResponse {
    id: string;
    email: string;
    first_name: string;
    last_name: string;
    date_of_birth: string;
    gender?: Patient["gender"];
    preferred_language: Language;
    created_at: string;
}

interface CareTeamResponse {
    id: string;
    patient_id: string;
    clinician_id: string;
    clinician_first_name: string;
    clinician_last_name: string;
    role: string;
    specialty_context?: string;
    clinic_name?: string;
    status: CareTeamMember["status"];
    created_at: string;
}

function mapPatient(profile: PatientProfileResponse): Patient {
    return {
        createdAt: profile.created_at,
        dateOfBirth: profile.date_of_birth,
        email: profile.email,
        firstName: profile.first_name,
        gender: profile.gender,
        id: profile.id,
        lastName: profile.last_name,
        preferredLanguage: profile.preferred_language,
    };
}

function mapCareTeamMember(member: CareTeamResponse): CareTeamMember {
    return {
        clinicName: member.clinic_name,
        clinicianFirstName: member.clinician_first_name,
        clinicianId: member.clinician_id,
        clinicianLastName: member.clinician_last_name,
        createdAt: member.created_at,
        id: member.id,
        patientId: member.patient_id,
        role: member.role,
        specialtyContext: member.specialty_context,
        status: member.status,
    };
}

function formatLanguage(language: Language) {
    return language === "es" ? "Spanish" : "English";
}

export default function ProfilePage() {
    const dispatch = useDispatch<AppDispatch>();
    const router = useRouter();
    const accessToken = useSelector((state: RootState) => state.auth.accessToken);
    const [patientProfile, setPatientProfile] = useState<Patient | null>(null);
    const [careTeam, setCareTeam] = useState<CareTeamMember[]>([]);
    const [inviteCode, setInviteCode] = useState("");
    const [joinError, setJoinError] = useState("");
    const [joinSuccess, setJoinSuccess] = useState("");
    const [loading, setLoading] = useState(true);
    const [pageError, setPageError] = useState("");
    const [joining, setJoining] = useState(false);

    async function fetchCareTeam(token: string) {
        const response = await api.get<CareTeamResponse[]>("/api/v1/patients/me/care-team", {
            token,
        });
        return response.map(mapCareTeamMember);
    }

    useEffect(() => {
        if (!accessToken) {
            router.replace("/login");
            return;
        }

        const token: string = accessToken;

        let isMounted = true;

        async function loadAccount() {
            setLoading(true);
            setPageError("");

            try {
                const [profileResponse, careTeamResponse] = await Promise.all([
                    api.get<PatientProfileResponse>("/api/v1/patients/me", { token }),
                    fetchCareTeam(token),
                ]);

                if (!isMounted) {
                    return;
                }

                setPatientProfile(mapPatient(profileResponse));
                setCareTeam(careTeamResponse);
            } catch (error) {
                if (isMounted) {
                    setPageError((error as Error).message);
                }
            } finally {
                if (isMounted) {
                    setLoading(false);
                }
            }
        }

        void loadAccount();

        return () => {
            isMounted = false;
        };
    }, [accessToken, router]);

    function handleLogout() {
        clearStoredSession();
        dispatch(logout());
        router.replace("/login");
    }

    async function handleJoinClinic(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();

        if (!accessToken) {
            router.replace("/login");
            return;
        }

        if (!inviteCode.trim()) {
            setJoinError("Enter a clinic invite code to continue.");
            return;
        }

        setJoinError("");
        setJoinSuccess("");
        setJoining(true);

        try {
            await api.post(
                `/api/v1/patients/me/care-team/join?invite_code=${encodeURIComponent(inviteCode.trim())}`,
                undefined,
                { token: accessToken },
            );
            const refreshedCareTeam = await fetchCareTeam(accessToken);
            setCareTeam(refreshedCareTeam);
            setInviteCode("");
            setJoinSuccess("Clinic linked successfully. Your new care team is now available.");
        } catch (error) {
            setJoinError((error as Error).message);
        } finally {
            setJoining(false);
        }
    }

    return (
        <div className="space-y-4 bg-gray-50 pb-8">
            <PageHeader subtitle="Manage your account and linked clinics." title="Profile" />
            <div className="-mt-4 space-y-4 px-5">
                {loading ? (
                    <div className="space-y-4">
                        <Skeleton className="h-32 w-full rounded-3xl" />
                        <Skeleton className="h-48 w-full rounded-3xl" />
                        <Skeleton className="h-56 w-full rounded-3xl" />
                    </div>
                ) : null}

                {!loading && pageError ? (
                    <ErrorState
                        description={pageError}
                        onRetry={() => window.location.reload()}
                        title="Unable to load your profile"
                    />
                ) : null}

                {!loading && !pageError && patientProfile ? (
                    <>
                        <Card className="overflow-hidden border-sky-100 bg-gradient-to-br from-sky-600 to-sky-700 text-white shadow-lg shadow-sky-100">
                            <div className="flex items-center gap-4">
                                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-white/20 text-2xl font-semibold">
                                    {patientProfile.firstName.charAt(0)}
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
                                    <p className="mt-1 font-medium text-slate-800">{formatLanguage(patientProfile.preferredLanguage)}</p>
                                </div>
                            </div>
                        </Card>

                        <Card className="space-y-4">
                            <div>
                                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Connected clinics</p>
                                <h3 className="mt-1 text-lg font-semibold text-slate-900">Care teams</h3>
                            </div>
                            {careTeam.length ? (
                                <div className="space-y-3">
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
                                            <p className="mt-3 text-sm text-slate-500">{member.clinicName || member.specialtyContext || "Care team active"}</p>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <EmptyState
                                    description="Add a clinic invite code to connect your account with a care team."
                                    icon={<HiOutlineBuildingOffice2 />}
                                    title="No care teams linked yet"
                                />
                            )}
                        </Card>

                        <Card className="space-y-4">
                            <div>
                                <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Join another clinic</p>
                                <h3 className="mt-1 text-lg font-semibold text-slate-900">Add care team access</h3>
                                <p className="mt-1 text-sm text-slate-500">
                                    If another clinic shares a code with you, enter it here to link that team to your account.
                                </p>
                            </div>
                            <form className="space-y-3" onSubmit={handleJoinClinic}>
                                <Input
                                    label="Clinic invite code"
                                    onChange={(event) => {
                                        setInviteCode(event.target.value);
                                        if (joinError) {
                                            setJoinError("");
                                        }
                                        if (joinSuccess) {
                                            setJoinSuccess("");
                                        }
                                    }}
                                    placeholder="CITY-8832"
                                    value={inviteCode}
                                />
                                {joinError ? <p className="text-sm text-red-600">{joinError}</p> : null}
                                {joinSuccess ? <p className="text-sm text-green-600">{joinSuccess}</p> : null}
                                <Button disabled={joining} fullWidth type="submit">
                                    {joining ? "Joining clinic..." : "Join clinic"}
                                </Button>
                            </form>
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
                    </>
                ) : null}
            </div>
        </div>
    );
}
