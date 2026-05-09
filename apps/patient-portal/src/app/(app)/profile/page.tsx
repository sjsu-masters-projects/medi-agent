"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { HiOutlineBuildingOffice2, HiOutlinePencilSquare, HiOutlineCheck, HiOutlineXMark } from "react-icons/hi2";
import { useDispatch, useSelector } from "react-redux";
import { PageHeader } from "@/components/layouts";
import { api } from "@/services/api";
import { clearStoredSession } from "@/services/auth-session";
import { Badge, Button, Card, EmptyState, ErrorState, Input, Skeleton } from "@/components/ui";
import { logout } from "@/store/slices/auth-slice";
import type { AppDispatch, RootState } from "@/store/store";
import { Gender, Locale, SUPPORTED_LOCALES, getLocaleLabel, normalizeLocale } from "@/types";
import type { CareTeamMember, Patient } from "@/types";

interface PatientProfileResponse {
    id: string;
    email: string;
    first_name: string;
    last_name: string;
    date_of_birth: string;
    gender?: Patient["gender"];
    preferred_language: Locale;
    timezone?: string;
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

interface EditDraft {
    firstName: string;
    lastName: string;
    preferredLanguage: Locale;
    gender: Patient["gender"] | "";
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
        preferredLanguage: normalizeLocale(profile.preferred_language),
        timezone: profile.timezone ?? "UTC",
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

const GENDER_LABELS: Record<string, string> = {
    [Gender.MALE]: "Male",
    [Gender.FEMALE]: "Female",
    [Gender.OTHER]: "Other",
    [Gender.PREFER_NOT_TO_SAY]: "Prefer not to say",
};

function ProfilePageContent() {
    const dispatch = useDispatch<AppDispatch>();
    const { replace } = useRouter();
    const searchParams = useSearchParams();
    const accessToken = useSelector((state: RootState) => state.auth.accessToken);
    const [patientProfile, setPatientProfile] = useState<Patient | null>(null);
    const [careTeam, setCareTeam] = useState<CareTeamMember[]>([]);
    const [inviteCode, setInviteCode] = useState("");
    const [joinError, setJoinError] = useState("");
    const [joinSuccess, setJoinSuccess] = useState("");
    const [loading, setLoading] = useState(true);
    const [pageError, setPageError] = useState("");
    const [joining, setJoining] = useState(false);

    // Edit state
    const [editing, setEditing] = useState(false);
    const [editDraft, setEditDraft] = useState<EditDraft | null>(null);
    const [saving, setSaving] = useState(false);
    const [saveError, setSaveError] = useState("");
    const [saveSuccess, setSaveSuccess] = useState("");

    const showJoinClinicPrompt = searchParams.get("joinClinic") === "1" && careTeam.length === 0;

    async function fetchCareTeam(token: string) {
        const response = await api.get<CareTeamResponse[]>("/api/v1/patients/me/care-team", {
            token,
        });
        return response.map(mapCareTeamMember);
    }

    useEffect(() => {
        if (!accessToken) {
            replace("/login");
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

                if (!isMounted) return;

                setPatientProfile(mapPatient(profileResponse));
                setCareTeam(careTeamResponse);
            } catch (error) {
                if (isMounted) setPageError((error as Error).message);
            } finally {
                if (isMounted) setLoading(false);
            }
        }

        void loadAccount();
        return () => { isMounted = false; };
    }, [accessToken, replace]);

    function handleLogout() {
        clearStoredSession();
        dispatch(logout());
        replace("/login");
    }

    function startEditing() {
        if (!patientProfile) return;
        setEditDraft({
            firstName: patientProfile.firstName,
            gender: patientProfile.gender ?? "",
            lastName: patientProfile.lastName,
            preferredLanguage: patientProfile.preferredLanguage,
        });
        setSaveError("");
        setSaveSuccess("");
        setEditing(true);
    }

    function cancelEditing() {
        setEditing(false);
        setEditDraft(null);
        setSaveError("");
    }

    async function handleSaveProfile(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!accessToken || !editDraft) return;

        setSaving(true);
        setSaveError("");
        setSaveSuccess("");

        try {
            const updated = await api.put<PatientProfileResponse>(
                "/api/v1/patients/me",
                {
                    first_name: editDraft.firstName.trim(),
                    last_name: editDraft.lastName.trim(),
                    preferred_language: editDraft.preferredLanguage,
                    ...(editDraft.gender ? { gender: editDraft.gender } : {}),
                },
                { token: accessToken },
            );
            setPatientProfile(mapPatient(updated));
            setSaveSuccess("Profile updated successfully.");
            setEditing(false);
            setEditDraft(null);
        } catch (error) {
            setSaveError((error as Error).message || "Failed to save profile. Please try again.");
        } finally {
            setSaving(false);
        }
    }

    async function handleJoinClinic(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();

        if (!accessToken) { replace("/login"); return; }

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
        <div className="patient-page space-y-4 pb-8">
            <PageHeader subtitle="Manage your account and linked clinics." title="Profile" />
            <div className="patient-stack -mt-4 space-y-4 px-5">
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
                        {showJoinClinicPrompt ? (
                            <Card className="border-amber-200 bg-amber-50 text-amber-900">
                                <p className="text-sm font-medium">
                                    No active care team is linked yet. Enter your clinic invite code below to complete onboarding.
                                </p>
                            </Card>
                        ) : null}

                        {/* Header card */}
                        <Card className="overflow-hidden border-[#b9ded6] bg-gradient-to-br from-[#147465] to-[#285d8f] text-white shadow-[0_24px_55px_rgba(20,116,101,0.24)]">
                            <div className="flex items-center gap-4">
                                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-white/20 text-2xl font-semibold">
                                    {patientProfile.firstName.charAt(0)}
                                </div>
                                <div className="min-w-0">
                                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#ccebe5]">Patient account</p>
                                    <h2 className="truncate text-xl font-semibold text-white">
                                        {patientProfile.firstName} {patientProfile.lastName}
                                    </h2>
                                    <p className="mt-1 text-sm text-[#dcefeb]">{patientProfile.email}</p>
                                </div>
                            </div>
                        </Card>

                        {/* Personal information card */}
                        <Card className="space-y-4">
                            <div className="flex items-center justify-between gap-3">
                                <div>
                                    <p className="text-xs font-semibold uppercase tracking-wide text-[#7b8798]">Profile details</p>
                                    <h3 className="mt-1 text-xl font-semibold text-[#17233a]">Personal information</h3>
                                </div>
                                {!editing ? (
                                    <button
                                        aria-label="Edit profile"
                                        className="flex min-h-10 items-center gap-1.5 rounded-2xl border border-[#b9ded6] bg-[#e6f4f1] px-3 py-2 text-sm font-semibold text-[#147465] transition hover:bg-[#d0eceb]"
                                        onClick={startEditing}
                                        type="button"
                                    >
                                        <HiOutlinePencilSquare className="h-4 w-4" />
                                        Edit
                                    </button>
                                ) : (
                                    <Badge variant="info">Editing</Badge>
                                )}
                            </div>

                            {saveSuccess && !editing ? (
                                <div className="flex items-center gap-2 rounded-2xl bg-[#ecf8ef] px-4 py-3 text-sm font-medium text-[#256047]">
                                    <HiOutlineCheck className="h-4 w-4 shrink-0" />
                                    {saveSuccess}
                                </div>
                            ) : null}

                            {editing && editDraft ? (
                                <form className="space-y-4" onSubmit={handleSaveProfile}>
                                    <div className="grid gap-3 sm:grid-cols-2">
                                        <Input
                                            label="First name"
                                            onChange={(e) => setEditDraft((d) => d ? { ...d, firstName: e.target.value } : d)}
                                            required
                                            value={editDraft.firstName}
                                        />
                                        <Input
                                            label="Last name"
                                            onChange={(e) => setEditDraft((d) => d ? { ...d, lastName: e.target.value } : d)}
                                            required
                                            value={editDraft.lastName}
                                        />
                                    </div>

                                    <div className="space-y-1">
                                        <label className="block text-[0.95rem] font-semibold text-[#30415f]">
                                            Preferred language
                                        </label>
                                        <select
                                            className="min-h-[3.25rem] w-full rounded-2xl border border-[#d9cbc0] bg-white/90 px-4 py-3 text-base text-[#17233a] outline-none focus:border-[#147465] focus:ring-4 focus:ring-[#147465]/15"
                                            onChange={(e) => setEditDraft((d) => d ? { ...d, preferredLanguage: e.target.value as Locale } : d)}
                                            value={editDraft.preferredLanguage}
                                        >
                                            {SUPPORTED_LOCALES.map((locale) => (
                                                <option key={locale} value={locale}>
                                                    {getLocaleLabel(locale)}
                                                </option>
                                            ))}
                                        </select>
                                    </div>

                                    <div className="space-y-1">
                                        <label className="block text-[0.95rem] font-semibold text-[#30415f]">
                                            Gender <span className="font-normal text-[#8090a5]">(optional)</span>
                                        </label>
                                        <select
                                            className="min-h-[3.25rem] w-full rounded-2xl border border-[#d9cbc0] bg-white/90 px-4 py-3 text-base text-[#17233a] outline-none focus:border-[#147465] focus:ring-4 focus:ring-[#147465]/15"
                                            onChange={(e) => setEditDraft((d) => d ? { ...d, gender: e.target.value as Patient["gender"] | "" } : d)}
                                            value={editDraft.gender}
                                        >
                                            <option value="">Prefer not to say</option>
                                            {Object.entries(GENDER_LABELS).map(([value, label]) => (
                                                <option key={value} value={value}>{label}</option>
                                            ))}
                                        </select>
                                    </div>

                                    {saveError ? (
                                        <div className="rounded-2xl bg-[#fff2ef] px-4 py-3 text-sm font-medium text-[#b94032]">
                                            {saveError}
                                        </div>
                                    ) : null}

                                    <div className="grid grid-cols-2 gap-3">
                                        <Button
                                            disabled={saving}
                                            fullWidth
                                            size="lg"
                                            type="submit"
                                        >
                                            {saving ? "Saving..." : "Save changes"}
                                        </Button>
                                        <Button
                                            disabled={saving}
                                            fullWidth
                                            onClick={cancelEditing}
                                            size="lg"
                                            type="button"
                                            variant="secondary"
                                        >
                                            <HiOutlineXMark className="mr-1 h-4 w-4" />
                                            Cancel
                                        </Button>
                                    </div>
                                </form>
                            ) : (
                                <div className="grid gap-3 text-sm text-[#5b6b83]">
                                    <div className="rounded-2xl bg-[#fff7ed] px-4 py-3 ring-1 ring-[#eaded3]">
                                        <p className="text-xs font-semibold uppercase tracking-wide text-[#7b8798]">Date of birth</p>
                                        <p className="mt-1 font-semibold text-[#30415f]">{patientProfile.dateOfBirth}</p>
                                    </div>
                                    <div className="rounded-2xl bg-[#fff7ed] px-4 py-3 ring-1 ring-[#eaded3]">
                                        <p className="text-xs font-semibold uppercase tracking-wide text-[#7b8798]">Preferred language</p>
                                        <p className="mt-1 font-semibold text-[#30415f]">{getLocaleLabel(patientProfile.preferredLanguage)}</p>
                                    </div>
                                    {patientProfile.gender ? (
                                        <div className="rounded-2xl bg-[#fff7ed] px-4 py-3 ring-1 ring-[#eaded3]">
                                            <p className="text-xs font-semibold uppercase tracking-wide text-[#7b8798]">Gender</p>
                                            <p className="mt-1 font-semibold text-[#30415f]">
                                                {GENDER_LABELS[patientProfile.gender] ?? patientProfile.gender}
                                            </p>
                                        </div>
                                    ) : null}
                                    <div className="rounded-2xl bg-[#fff7ed] px-4 py-3 ring-1 ring-[#eaded3]">
                                        <p className="text-xs font-semibold uppercase tracking-wide text-[#7b8798]">Timezone</p>
                                        <p className="mt-1 font-semibold text-[#30415f]">{patientProfile.timezone ?? "UTC"}</p>
                                    </div>
                                </div>
                            )}
                        </Card>

                        {/* Reminders card */}
                        <Card className="space-y-4">
                            <div className="flex items-center justify-between gap-3">
                                <div>
                                    <p className="text-xs font-semibold uppercase tracking-wide text-[#7b8798]">Reminders</p>
                                    <h3 className="mt-1 text-xl font-semibold text-[#17233a]">Medication and task reminder times</h3>
                                    <p className="mt-1 text-base leading-7 text-[#5b6b83]">
                                        Choose the exact times and days you want reminders sent.
                                    </p>
                                </div>
                                <Badge variant="info">Patient controlled</Badge>
                            </div>
                            <Link href="/reminders">
                                <Button fullWidth size="lg">Manage reminders</Button>
                            </Link>
                        </Card>

                        {/* Care teams card */}
                        <Card className="space-y-4">
                            <div>
                                <p className="text-xs font-semibold uppercase tracking-wide text-[#7b8798]">Connected clinics</p>
                                <h3 className="mt-1 text-xl font-semibold text-[#17233a]">Care teams</h3>
                            </div>
                            {careTeam.length ? (
                                <div className="space-y-3">
                                    {careTeam.map((member) => (
                                        <div className="rounded-2xl border border-[#eaded3] bg-[#fff7ed] px-4 py-4" key={member.id}>
                                            <div className="flex items-start justify-between gap-3">
                                                <div>
                                                    <p className="font-semibold text-[#17233a]">
                                                        Dr. {member.clinicianFirstName} {member.clinicianLastName}
                                                    </p>
                                                    <p className="mt-1 text-sm text-[#5b6b83]">{member.role}</p>
                                                </div>
                                                <Badge variant="success">Linked</Badge>
                                            </div>
                                            <p className="mt-3 text-sm text-[#5b6b83]">{member.clinicName || member.specialtyContext || "Care team active"}</p>
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

                        {/* Join clinic card */}
                        <Card className="space-y-4">
                            <div>
                                <p className="text-xs font-semibold uppercase tracking-wide text-[#7b8798]">Join another clinic</p>
                                <h3 className="mt-1 text-xl font-semibold text-[#17233a]">Add care team access</h3>
                                <p className="mt-1 text-base leading-7 text-[#5b6b83]">
                                    If another clinic shares a code with you, enter it here to link that team to your account.
                                </p>
                            </div>
                            <form className="space-y-3" onSubmit={handleJoinClinic}>
                                <Input
                                    label="Clinic invite code"
                                    onChange={(event) => {
                                        setInviteCode(event.target.value);
                                        if (joinError) setJoinError("");
                                        if (joinSuccess) setJoinSuccess("");
                                    }}
                                    placeholder="CITY-8832"
                                    value={inviteCode}
                                />
                                {joinError ? <div className="rounded-2xl bg-[#fff2ef] px-4 py-3 text-sm font-medium text-[#b94032]">{joinError}</div> : null}
                                {joinSuccess ? <div className="rounded-2xl bg-[#ecf8ef] px-4 py-3 text-sm font-medium text-[#256047]">{joinSuccess}</div> : null}
                                <Button disabled={joining} fullWidth size="lg" type="submit">
                                    {joining ? "Joining clinic..." : "Join clinic"}
                                </Button>
                            </form>
                        </Card>

                        {/* Sign out card */}
                        <Card className="space-y-3 border-red-100 bg-red-50/70">
                            <div>
                                <p className="text-xs font-semibold uppercase tracking-wide text-red-400">Account</p>
                                <h3 className="mt-1 text-lg font-semibold text-slate-900">Sign out safely</h3>
                                <p className="mt-1 text-sm text-slate-600">
                                    Use this if you are on a shared phone or finished reviewing your care plan.
                                </p>
                            </div>
                            <Button fullWidth onClick={handleLogout} size="lg" variant="danger">
                                Sign out
                            </Button>
                        </Card>
                    </>
                ) : null}
            </div>
        </div>
    );
}

export default function ProfilePage() {
    return (
        <Suspense fallback={null}>
            <ProfilePageContent />
        </Suspense>
    );
}
