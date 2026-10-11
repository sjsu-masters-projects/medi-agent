"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
    HiOutlineBuildingOffice2,
    HiOutlineCheck,
    HiOutlinePencilSquare,
    HiOutlineXMark,
} from "react-icons/hi2";
import { useDispatch, useSelector } from "react-redux";
import { PageHeader } from "@/components/layouts";
import { PatientLanguageControl } from "@/components/layouts/patient-language-control";
import { Modal } from "@/components/ui/modal";
import { api } from "@/services/api";
import { clearStoredSession } from "@/services/auth-session";
import {
    Badge,
    Button,
    Card,
    EmptyState,
    ErrorState,
    Input,
    Skeleton,
} from "@/components/ui";
import { logout } from "@/store/slices/auth-slice";
import type { AppDispatch, RootState } from "@/store/store";
import { normalizeLocale, SUPPORTED_LOCALES, type Locale } from "@/types";
import type { CareTeamMember, Patient } from "@/types";
import { careTeamRoleLabel } from "./care-team-labels";
import { profileCopy, profileGenderLabels } from "./profile-copy";
import { useSharedPatientProfile } from "@/hooks/use-patient-profile";

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
    gender: Patient["gender"] | "";
    lastName: string;
    preferredLanguage: Locale;
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

function ProfilePageContent() {
    const sharedProfile = useSharedPatientProfile();
    const dispatch = useDispatch<AppDispatch>();
    const { replace } = useRouter();
    const searchParams = useSearchParams();
    const accessToken = useSelector(
        (state: RootState) => state.auth.accessToken,
    );
    const [patientProfile, setPatientProfile] = useState<Patient | null>(null);
    const [careTeam, setCareTeam] = useState<CareTeamMember[]>([]);
    const [inviteCode, setInviteCode] = useState("");
    const [joinError, setJoinError] = useState<
        "" | "enterCode" | "invalidCode" | "joinError"
    >("");
    const [joinSuccess, setJoinSuccess] = useState(false);
    const [loading, setLoading] = useState(true);
    const [pageError, setPageError] = useState(false);
    const [joining, setJoining] = useState(false);
    const [editing, setEditing] = useState(false);
    const [languageOpen, setLanguageOpen] = useState(false);
    const [editDraft, setEditDraft] = useState<EditDraft | null>(null);
    const [saving, setSaving] = useState(false);
    const [saveError, setSaveError] = useState(false);
    const [saveSuccess, setSaveSuccess] = useState(false);
    const [joinExpanded, setJoinExpanded] = useState<boolean | null>(null);
    const locale =
        sharedProfile?.profile?.preferredLanguage ??
        patientProfile?.preferredLanguage ??
        "en-US";
    const copy = profileCopy(locale);
    const genderLabels = profileGenderLabels(locale);
    const hasActiveTeam = careTeam.some((member) => member.status === "active");
    const forceJoinOpen = searchParams.get("joinClinic") === "1";
    const showJoinClinicPrompt = forceJoinOpen && !hasActiveTeam;

    async function fetchCareTeam(token: string) {
        const response = await api.get<CareTeamResponse[]>(
            "/api/v1/patients/me/care-team",
            {
                token,
            },
        );
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
            setPageError(false);

            try {
                const [profileResponse, careTeamResponse] = await Promise.all([
                    api.get<PatientProfileResponse>("/api/v1/patients/me", {
                        token,
                    }),
                    fetchCareTeam(token),
                ]);

                if (!isMounted) {
                    return;
                }

                setPatientProfile(mapPatient(profileResponse));
                setCareTeam(careTeamResponse);
            } catch {
                if (isMounted) {
                    setPageError(true);
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
    }, [accessToken, replace]);

    function handleLogout() {
        clearStoredSession();
        dispatch(logout());
        replace("/login");
    }

    function startEditing() {
        if (!patientProfile) {
            return;
        }

        setEditDraft({
            firstName: patientProfile.firstName,
            gender: patientProfile.gender ?? "",
            lastName: patientProfile.lastName,
            preferredLanguage: locale,
        });
        setSaveError(false);
        setSaveSuccess(false);
        setEditing(true);
    }

    function cancelEditing() {
        setEditing(false);
        setEditDraft(null);
        setSaveError(false);
    }

    async function handleSaveProfile(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!accessToken || !editDraft) {
            return;
        }

        setSaving(true);
        setSaveError(false);
        setSaveSuccess(false);

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
            const mappedProfile = mapPatient(updated);
            setPatientProfile(mappedProfile);
            sharedProfile?.updateProfile({
                dateOfBirth: mappedProfile.dateOfBirth,
                email: mappedProfile.email,
                firstName: mappedProfile.firstName,
                lastName: mappedProfile.lastName,
                id: mappedProfile.id,
                preferredLanguage: mappedProfile.preferredLanguage,
                timezone: mappedProfile.timezone ?? "UTC",
            });
            setSaveSuccess(true);
            setEditing(false);
            setEditDraft(null);
        } catch {
            setSaveError(true);
        } finally {
            setSaving(false);
        }
    }

    async function handleJoinClinic(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();

        if (!accessToken) {
            replace("/login");
            return;
        }

        if (!inviteCode.trim()) {
            setJoinError("enterCode");
            return;
        }

        setJoinError("");
        setJoinSuccess(false);
        setJoinExpanded(true);
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
            setJoinSuccess(true);
        } catch (error) {
            setJoinError(
                /invalid or expired invite code/i.test((error as Error).message)
                    ? "invalidCode"
                    : "joinError",
            );
        } finally {
            setJoining(false);
        }
    }

    return (
        <div className="patient-page space-y-4 pb-8">
            <PageHeader subtitle={copy.subtitle} title={copy.title} />
            <div className="patient-stack -mt-4 space-y-4 px-5">
                {(loading || pageError) ? (
                    <button type="button" onClick={() => setLanguageOpen(true)} className="min-h-11 w-full rounded-xl border border-line bg-surface px-4 text-left font-semibold text-brand">
                        {copy.language}
                    </button>
                ) : null}
                {loading ? (
                    <div className="space-y-4">
                        <Skeleton className="h-32 w-full rounded-3xl" />
                        <Skeleton className="h-48 w-full rounded-3xl" />
                        <Skeleton className="h-56 w-full rounded-3xl" />
                    </div>
                ) : null}

                {!loading && pageError ? (
                    <ErrorState
                        description={copy.loadError}
                        action={
                            <Button onClick={() => window.location.reload()}>
                                {copy.retry}
                            </Button>
                        }
                        title={copy.loadTitle}
                    />
                ) : null}

                {!loading && !pageError && patientProfile ? (
                    <>
                        {showJoinClinicPrompt ? (
                            <Card className="border-yellow-200 bg-yellow-100 text-yellow-800">
                                <p className="text-sm font-medium">
                                    {copy.onboarding}
                                </p>
                            </Card>
                        ) : null}

                        <Card className="overflow-hidden">
                            <div className="flex items-center gap-4">
                                <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-blue-100 text-2xl font-semibold text-blue-800">
                                    {patientProfile.firstName.charAt(0)}
                                </div>
                                <div className="min-w-0">
                                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                                        {copy.patientAccount}
                                    </p>
                                    <h2 className="break-words text-xl font-semibold text-gray-900">
                                        {patientProfile.firstName}{" "}
                                        {patientProfile.lastName}
                                    </h2>
                                    <p className="mt-1 break-all text-sm text-gray-700">
                                        {patientProfile.email}
                                    </p>
                                </div>
                            </div>
                        </Card>

                        <Card className="space-y-4">
                            <div className="flex items-center justify-between gap-3">
                                <div>
                                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                                        {copy.details}
                                    </p>
                                    <h3 className="mt-1 text-xl font-semibold text-gray-900">
                                        {copy.personal}
                                    </h3>
                                </div>
                                {editing ? (
                                    <Badge variant="info">{copy.editing}</Badge>
                                ) : (
                                    <button
                                        aria-label={copy.editProfile}
                                        className="flex min-h-10 items-center gap-1.5 rounded-2xl border border-gray-200 bg-blue-100 px-3 py-2 text-sm font-semibold text-blue-800 transition hover:bg-blue-100"
                                        onClick={startEditing}
                                        type="button"
                                    >
                                        <HiOutlinePencilSquare className="h-4 w-4" />
                                        {copy.edit}
                                    </button>
                                )}
                            </div>
                            {saveSuccess && !editing ? (
                                <div
                                    role="status"
                                    className="flex items-center gap-2 rounded-2xl bg-green-100 px-4 py-3 text-sm font-medium text-green-800"
                                >
                                    <HiOutlineCheck className="h-4 w-4 shrink-0" />
                                    {copy.saved}
                                </div>
                            ) : null}
                            {editing && editDraft ? (
                                <form
                                    className="space-y-4"
                                    onSubmit={handleSaveProfile}
                                >
                                    <div className="grid gap-3 sm:grid-cols-2">
                                        <Input
                                            label={copy.firstName}
                                            onChange={(event) =>
                                                setEditDraft((draft) =>
                                                    draft
                                                        ? {
                                                              ...draft,
                                                              firstName:
                                                                  event.target
                                                                      .value,
                                                          }
                                                        : draft,
                                                )
                                            }
                                            required
                                            value={editDraft.firstName}
                                        />
                                        <Input
                                            label={copy.lastName}
                                            onChange={(event) =>
                                                setEditDraft((draft) =>
                                                    draft
                                                        ? {
                                                              ...draft,
                                                              lastName:
                                                                  event.target
                                                                      .value,
                                                          }
                                                        : draft,
                                                )
                                            }
                                            required
                                            value={editDraft.lastName}
                                        />
                                    </div>
                                    <div className="space-y-1">
                                        <label
                                            className="block text-[0.95rem] font-semibold text-gray-700"
                                            htmlFor="preferred-language"
                                        >
                                            {copy.language}
                                        </label>
                                        <select
                                            className="min-h-[3.25rem] w-full rounded-2xl border border-gray-300 bg-white/90 px-4 py-3 text-base text-gray-900 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/15"
                                            aria-describedby="profile-language-help"
                                            id="preferred-language"
                                            onChange={(event) =>
                                                setEditDraft((draft) =>
                                                    draft
                                                        ? {
                                                              ...draft,
                                                              preferredLanguage:
                                                                  event.target
                                                                      .value as Locale,
                                                          }
                                                        : draft,
                                                )
                                            }
                                            value={editDraft.preferredLanguage}
                                        >
                                            {SUPPORTED_LOCALES.map((locale) => (
                                                <option
                                                    key={locale}
                                                    value={locale}
                                                >
                                                    {locale === "es-MX"
                                                        ? "Español (México)"
                                                        : "English (US)"}
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                    <p
                                        className="text-sm text-gray-500"
                                        id="profile-language-help"
                                    >
                                        {copy.languageHelp}
                                    </p>
                                    <div className="space-y-1">
                                        <label
                                            className="block text-[0.95rem] font-semibold text-gray-700"
                                            htmlFor="gender"
                                        >
                                            {copy.gender}{" "}
                                            <span className="font-normal text-gray-500">
                                                {copy.optional}
                                            </span>
                                        </label>
                                        <select
                                            className="min-h-[3.25rem] w-full rounded-2xl border border-gray-300 bg-white/90 px-4 py-3 text-base text-gray-900 outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/15"
                                            id="gender"
                                            onChange={(event) =>
                                                setEditDraft((draft) =>
                                                    draft
                                                        ? {
                                                              ...draft,
                                                              gender: event
                                                                  .target
                                                                  .value as
                                                                  | Patient["gender"]
                                                                  | "",
                                                          }
                                                        : draft,
                                                )
                                            }
                                            value={editDraft.gender}
                                        >
                                            <option value="">
                                                {copy.unspecified}
                                            </option>
                                            {Object.entries(genderLabels).map(
                                                ([value, label]) => (
                                                    <option
                                                        key={value}
                                                        value={value}
                                                    >
                                                        {label}
                                                    </option>
                                                ),
                                            )}
                                        </select>
                                    </div>
                                    {saveError ? (
                                        <div
                                            role="alert"
                                            className="rounded-2xl bg-red-100 px-4 py-3 text-sm font-medium text-red-800"
                                        >
                                            {copy.saveError}
                                        </div>
                                    ) : null}
                                    <div className="grid grid-cols-2 gap-3">
                                        <Button
                                            disabled={saving}
                                            fullWidth
                                            size="lg"
                                            type="submit"
                                        >
                                            {saving ? copy.saving : copy.save}
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
                                            {copy.cancel}
                                        </Button>
                                    </div>
                                </form>
                            ) : (
                                <div className="grid gap-3 text-sm text-gray-700">
                                    <div className="rounded-2xl bg-gray-50 px-4 py-3 ring-1 ring-gray-200">
                                        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                                            {copy.dob}
                                        </p>
                                        <p className="mt-1 font-semibold text-gray-700">
                                            {patientProfile.dateOfBirth}
                                        </p>
                                    </div>
                                    <div className="rounded-2xl bg-gray-50 px-4 py-3 ring-1 ring-gray-200">
                                        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                                            {copy.language}
                                        </p>
                                        <button type="button" onClick={() => setLanguageOpen(true)} className="mt-1 min-h-11 w-full text-left font-semibold text-brand underline-offset-4 hover:underline">
                                            {locale === "es-MX"
                                                ? "Español (México)"
                                                : "English (US)"}
                                        </button>
                                    </div>
                                    {patientProfile.gender ? (
                                        <div className="rounded-2xl bg-gray-50 px-4 py-3 ring-1 ring-gray-200">
                                            <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                                                {copy.gender}
                                            </p>
                                            <p className="mt-1 font-semibold text-gray-700">
                                                {genderLabels[
                                                    patientProfile.gender
                                                ] ?? copy.unspecified}
                                            </p>
                                        </div>
                                    ) : null}
                                    <div className="rounded-2xl bg-gray-50 px-4 py-3 ring-1 ring-gray-200">
                                        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                                            {copy.timezone}
                                        </p>
                                        <p className="mt-1 font-semibold text-gray-700">
                                            {patientProfile.timezone ?? "UTC"}
                                        </p>
                                    </div>
                                </div>
                            )}
                        </Card>

                        <Card className="space-y-4">
                            <div className="flex items-center justify-between gap-3">
                                <div>
                                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                                        {copy.reminders}
                                    </p>
                                    <h3 className="mt-1 text-xl font-semibold text-gray-900">
                                        {copy.reminderTitle}
                                    </h3>
                                    <p className="mt-1 text-base leading-7 text-gray-700">
                                        {copy.reminderHelp}
                                    </p>
                                </div>
                                <Badge variant="info">
                                    {copy.patientControlled}
                                </Badge>
                            </div>
                            <Link
                                className="flex min-h-11 items-center justify-center rounded-lg bg-blue-600 px-4 py-3 font-semibold text-white hover:bg-blue-700 focus-visible:ring-2 focus-visible:ring-blue-500"
                                href="/reminders"
                            >
                                {copy.manageReminders}
                            </Link>
                        </Card>

                        <Card className="space-y-4">
                            <div>
                                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">
                                    {copy.connected}
                                </p>
                                <h3 className="mt-1 text-xl font-semibold text-gray-900">
                                    {copy.teams}
                                </h3>
                            </div>
                            {hasActiveTeam ? (
                                <div className="space-y-2">
                                    <Link
                                        className="inline-flex min-h-11 items-center rounded-lg px-3 py-2 font-semibold text-blue-600 focus-visible:ring-2 focus-visible:ring-blue-500"
                                        href="/chat"
                                    >
                                        {copy.messages}
                                    </Link>
                                    <p className="text-sm text-gray-500">
                                        {copy.messageHelp}
                                    </p>
                                </div>
                            ) : null}
                            {careTeam.length ? (
                                <div className="space-y-3">
                                    {careTeam.map((member) => (
                                        <div
                                            className="rounded-2xl border border-gray-200 bg-gray-50 px-4 py-4"
                                            key={member.id}
                                        >
                                            <div className="flex items-start justify-between gap-3">
                                                <div className="min-w-0">
                                                    <p className="break-words font-semibold text-gray-900">
                                                        {
                                                            member.clinicianFirstName
                                                        }{" "}
                                                        {
                                                            member.clinicianLastName
                                                        }
                                                    </p>
                                                    <p className="mt-1 text-sm text-gray-500">
                                                        {careTeamRoleLabel(
                                                            member.role,
                                                            locale,
                                                        )}
                                                    </p>
                                                </div>
                                                <Badge
                                                    variant={
                                                        member.status ===
                                                        "active"
                                                            ? "success"
                                                            : "warning"
                                                    }
                                                >
                                                    {member.status === "active"
                                                        ? copy.active
                                                        : member.status ===
                                                            "inactive"
                                                          ? copy.inactive
                                                          : member.status ===
                                                              "transferred"
                                                            ? copy.transferred
                                                            : copy.unknownStatus}
                                                </Badge>
                                            </div>
                                            <p className="mt-3 text-sm text-gray-700">
                                                {member.clinicName ||
                                                    member.specialtyContext ||
                                                    copy.teamFallback}
                                            </p>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <EmptyState
                                    description={copy.noTeamsHelp}
                                    icon={<HiOutlineBuildingOffice2 />}
                                    title={copy.noTeams}
                                />
                            )}
                        </Card>

                        <Card className="space-y-4">
                            <details
                                open={
                                    forceJoinOpen ||
                                    (joinExpanded ?? !hasActiveTeam)
                                }
                                onToggle={(event) =>
                                    setJoinExpanded(event.currentTarget.open)
                                }
                            >
                                <summary className="min-h-11 cursor-pointer py-2 font-semibold text-gray-900">
                                    {copy.joinAnother}
                                </summary>
                                <div>
                                    <h3 className="mt-1 text-xl font-semibold text-gray-900">
                                        {copy.addTeam}
                                    </h3>
                                    <p className="mt-1 text-base leading-7 text-gray-700">
                                        {copy.joinHelp}
                                    </p>
                                </div>
                                <form
                                    className="space-y-3"
                                    onSubmit={handleJoinClinic}
                                >
                                    <Input
                                        aria-describedby="profile-invite-help"
                                        label={copy.inviteCode}
                                        onChange={(event) => {
                                            setInviteCode(event.target.value);
                                            if (joinError) {
                                                setJoinError("");
                                            }
                                            if (joinSuccess) {
                                                setJoinSuccess(false);
                                            }
                                        }}
                                        placeholder="CITY-8832"
                                        value={inviteCode}
                                    />
                                    <p
                                        className="text-sm text-gray-500"
                                        id="profile-invite-help"
                                    >
                                        {copy.inviteHelp}
                                    </p>
                                    {joinError ? (
                                        <div
                                            role="alert"
                                            className="rounded-2xl bg-red-100 px-4 py-3 text-sm font-medium text-red-800"
                                        >
                                            {copy[joinError]}
                                        </div>
                                    ) : null}
                                    {joinSuccess ? (
                                        <div
                                            role="status"
                                            className="rounded-2xl bg-green-100 px-4 py-3 text-sm font-medium text-green-800"
                                        >
                                            {copy.joined}
                                        </div>
                                    ) : null}
                                    <Button
                                        disabled={joining}
                                        fullWidth
                                        size="lg"
                                        type="submit"
                                    >
                                        {joining ? copy.joining : copy.join}
                                    </Button>
                                </form>
                            </details>
                        </Card>

                        <Card className="space-y-3 border-red-100 bg-red-50/70">
                            <div>
                                <p className="text-xs font-semibold uppercase tracking-wide text-red-400">
                                    {copy.account}
                                </p>
                                <h3 className="mt-1 text-lg font-semibold text-slate-900">
                                    {copy.signOutTitle}
                                </h3>
                                <p className="mt-1 text-sm text-slate-600">
                                    {copy.signOutHelp}
                                </p>
                            </div>
                            <Button
                                fullWidth
                                onClick={handleLogout}
                                size="lg"
                                variant="danger"
                            >
                                {copy.signOut}
                            </Button>
                        </Card>
                    </>
                ) : null}
            </div>
            <Modal keepMounted open={languageOpen} onClose={() => setLanguageOpen(false)} title={copy.language} closeLabel={locale === "es-MX" ? "Cerrar" : "Close"}>
                <PatientLanguageControl />
            </Modal>
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
