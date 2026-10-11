"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
    HiOutlineBuildingOffice2,
    HiOutlineCheck,
    HiOutlineChevronRight,
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
    Button,
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
            <div className="patient-stack space-y-4 px-4">
                {loading || pageError ? (
                    <button
                        type="button"
                        onClick={() => setLanguageOpen(true)}
                        className="min-h-11 w-full rounded-group bg-surface px-[14px] py-[13px] text-left font-semibold text-brand"
                    >
                        {copy.language}
                    </button>
                ) : null}
                {loading ? (
                    <div className="space-y-4">
                        <Skeleton className="h-32 w-full rounded-group" />
                        <Skeleton className="h-48 w-full rounded-group" />
                        <Skeleton className="h-56 w-full rounded-group" />
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
                        <div className="flex items-center gap-3 rounded-group bg-surface px-4 py-4">
                            <div
                                aria-hidden="true"
                                className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-brand-tint text-2xl font-semibold text-brand"
                            >
                                {patientProfile.firstName.charAt(0)}
                            </div>
                            <div className="min-w-0">
                                <p className="text-xs text-muted">
                                    {copy.patientAccount}
                                </p>
                                <h2 className="break-words text-xl font-semibold text-ink">
                                    {patientProfile.firstName}{" "}
                                    {patientProfile.lastName}
                                </h2>
                                <p className="mt-1 break-all text-sm text-ink-2">
                                    {patientProfile.email}
                                </p>
                            </div>
                        </div>
                        {showJoinClinicPrompt ? (
                            <p className="rounded-group bg-note-tint px-4 py-3 text-sm font-medium text-note-ink">
                                {copy.onboarding}
                            </p>
                        ) : null}
                        <section
                            aria-labelledby="profile-personal"
                            className="space-y-2"
                        >
                            <div className="flex flex-wrap items-center justify-between gap-3 px-1">
                                <div>
                                    <p className="sr-only">
                                        {copy.details}
                                    </p>
                                    <h3
                                        id="profile-personal"
                                        className="font-mono text-xs uppercase tracking-[0.08em] text-muted"
                                    >
                                        {copy.personal}
                                    </h3>
                                </div>
                                <button
                                    aria-label={copy.editProfile}
                                    className="inline-flex min-h-11 min-w-11 items-center gap-1.5 rounded-xl bg-brand-tint px-3 text-sm font-semibold text-brand"
                                    onClick={startEditing}
                                    type="button"
                                >
                                    <HiOutlinePencilSquare
                                        aria-hidden="true"
                                        className="h-4 w-4"
                                    />
                                    {copy.edit}
                                </button>
                            </div>
                            {saveSuccess && !editing ? (
                                <p
                                    role="status"
                                    className="flex items-center gap-2 bg-brand-tint px-[14px] py-[13px] text-sm font-medium text-brand-ink"
                                >
                                    <HiOutlineCheck
                                        aria-hidden="true"
                                        className="h-4 w-4 shrink-0"
                                    />
                                    {copy.saved}
                                </p>
                            ) : null}
                            <dl className="overflow-hidden rounded-group bg-surface text-[15px]">
                                <div className="flex flex-wrap justify-between gap-2 border-b border-line px-[14px] py-[13px]">
                                    <dt className="text-muted">{copy.dob}</dt>
                                    <dd className="text-ink-2">
                                        {patientProfile.dateOfBirth}
                                    </dd>
                                </div>
                                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-[14px] py-[13px]">
                                    <dt className="text-muted">
                                        {copy.language}
                                    </dt>
                                    <dd>
                                        <button
                                            type="button"
                                            onClick={() =>
                                                setLanguageOpen(true)
                                            }
                                            className="min-h-11 min-w-11 text-left font-semibold text-brand underline-offset-4 hover:underline"
                                        >
                                            {locale === "es-MX"
                                                ? "Español (México)"
                                                : "English (US)"}
                                        </button>
                                    </dd>
                                </div>
                                {patientProfile.gender ? (
                                    <div className="flex flex-wrap justify-between gap-2 border-b border-line px-[14px] py-[13px]">
                                        <dt className="text-muted">
                                            {copy.gender}
                                        </dt>
                                        <dd className="text-ink-2">
                                            {genderLabels[
                                                patientProfile.gender
                                            ] ?? copy.unspecified}
                                        </dd>
                                    </div>
                                ) : null}
                                <div className="flex flex-wrap justify-between gap-2 px-[14px] py-[13px]">
                                    <dt className="text-muted">
                                        {copy.timezone}
                                    </dt>
                                    <dd className="break-all text-ink-2">
                                        {patientProfile.timezone ?? "UTC"}
                                    </dd>
                                </div>
                            </dl>
                        </section>
                        <section
                            aria-labelledby="profile-reminders"
                            className="overflow-hidden rounded-group bg-surface"
                        >
                            <div className="border-b border-line px-[14px] py-[13px]">
                                <h3
                                    id="profile-reminders"
                                    className="text-[17px] font-semibold text-ink"
                                >
                                    {copy.reminders}
                                </h3>
                                <p className="mt-1 text-[15px] text-ink-2">
                                    {copy.reminderTitle}
                                </p>
                                <p className="mt-1 text-sm text-muted">
                                    {copy.reminderHelp}
                                </p>
                                <p className="mt-1 text-sm text-brand-ink">
                                    {copy.patientControlled}
                                </p>
                            </div>
                            <Link
                                className="flex min-h-11 items-center justify-between gap-3 px-[14px] py-[13px] text-[15px] font-semibold text-brand"
                                href="/reminders"
                            >
                                {copy.manageReminders}
                                <HiOutlineChevronRight
                                    aria-hidden="true"
                                    className="h-5 w-5 shrink-0"
                                />
                            </Link>
                        </section>
                        <section
                            aria-labelledby="profile-team"
                            className="overflow-hidden rounded-group bg-surface"
                        >
                            <div className="border-b border-line px-[14px] py-[13px]">
                                <p className="text-xs text-muted">
                                    {copy.connected}
                                </p>
                                <h3
                                    id="profile-team"
                                    className="text-[17px] font-semibold text-ink"
                                >
                                    {copy.teams}
                                </h3>
                            </div>
                            {careTeam.length ? (
                                careTeam.map((member) => (
                                    <div
                                        className="border-b border-line px-[14px] py-[13px]"
                                        key={member.id}
                                    >
                                        <div className="flex flex-wrap items-start justify-between gap-2">
                                            <div className="min-w-0">
                                                <p className="break-words text-[15px] font-semibold text-ink">
                                                    {member.clinicianFirstName}{" "}
                                                    {member.clinicianLastName}
                                                </p>
                                                <p className="mt-1 text-sm text-muted">
                                                    {careTeamRoleLabel(
                                                        member.role,
                                                        locale,
                                                    )}
                                                </p>
                                            </div>
                                            <span
                                                className={`rounded-full px-2.5 py-1 text-xs font-semibold ${member.status === "active" ? "bg-brand-tint text-brand-ink" : "bg-surface-2 text-ink-2"}`}
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
                                            </span>
                                        </div>
                                        <p className="mt-1 break-words text-sm text-ink-2">
                                            {member.clinicName ||
                                                member.specialtyContext ||
                                                copy.teamFallback}
                                        </p>
                                    </div>
                                ))
                            ) : (
                                <div className="px-[14px] py-[13px]">
                                    <EmptyState
                                        description={copy.noTeamsHelp}
                                        icon={
                                            <HiOutlineBuildingOffice2 aria-hidden="true" />
                                        }
                                        title={copy.noTeams}
                                    />
                                </div>
                            )}
                            {hasActiveTeam ? (
                                <div>
                                    <Link
                                        className="flex min-h-11 items-center justify-between gap-3 px-[14px] py-[13px] text-[15px] font-semibold text-brand"
                                        href="/chat"
                                    >
                                        {copy.messages}
                                        <HiOutlineChevronRight
                                            aria-hidden="true"
                                            className="h-5 w-5 shrink-0"
                                        />
                                    </Link>
                                    <p className="px-[14px] pb-[13px] text-sm text-muted">
                                        {copy.messageHelp}
                                    </p>
                                </div>
                            ) : null}
                        </section>
                        <div className="overflow-hidden rounded-group bg-surface">
                            <button
                                className="flex min-h-11 w-full items-center justify-between gap-3 px-[14px] py-[13px] text-left text-[15px] font-semibold text-ink"
                                type="button"
                                onClick={() => setJoinExpanded(true)}
                            >
                                {copy.joinAnother}
                                <HiOutlineChevronRight
                                    aria-hidden="true"
                                    className="h-5 w-5 shrink-0"
                                />
                            </button>
                        </div>
                        <section
                            aria-labelledby="profile-account"
                            className="overflow-hidden rounded-group bg-surface"
                        >
                            <div className="border-b border-line px-[14px] py-[13px]">
                                <p className="text-xs text-muted">
                                    {copy.account}
                                </p>
                                <h3
                                    id="profile-account"
                                    className="text-[17px] font-semibold text-ink"
                                >
                                    {copy.signOutTitle}
                                </h3>
                                <p className="mt-1 text-sm text-muted">
                                    {copy.signOutHelp}
                                </p>
                            </div>
                            <button
                                className="min-h-11 w-full px-[14px] py-[13px] text-left text-[15px] font-semibold text-danger-ink"
                                type="button"
                                onClick={handleLogout}
                            >
                                {copy.signOut}
                            </button>
                        </section>
                    </>
                ) : null}
            </div>
            <Modal
                open={editing}
                onClose={() => { if (!saving) cancelEditing(); }}
                title={copy.personal}
                closeLabel={locale === "es-MX" ? "Cerrar" : "Close"}
            >
                {editDraft ? (
                    <div className="[&_label>span]:text-ink-2">
                        <p className="mb-4 text-sm text-muted">
                            {copy.editing}
                        </p>
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
                                                          event.target.value,
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
                                                          event.target.value,
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
                                    className="block text-[0.95rem] font-semibold text-ink-2"
                                    htmlFor="preferred-language"
                                >
                                    {copy.language}
                                </label>
                                <select
                                    className="min-h-[3.25rem] w-full rounded-2xl border border-line-strong bg-surface px-4 py-3 text-base text-ink outline-none focus:border-brand focus:ring-4 focus:ring-brand/15"
                                    aria-describedby="profile-language-help"
                                    id="preferred-language"
                                    onChange={(event) =>
                                        setEditDraft((draft) =>
                                            draft
                                                ? {
                                                      ...draft,
                                                      preferredLanguage: event
                                                          .target
                                                          .value as Locale,
                                                  }
                                                : draft,
                                        )
                                    }
                                    value={editDraft.preferredLanguage}
                                >
                                    {SUPPORTED_LOCALES.map((locale) => (
                                        <option key={locale} value={locale}>
                                            {locale === "es-MX"
                                                ? "Español (México)"
                                                : "English (US)"}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <p
                                className="text-sm text-muted"
                                id="profile-language-help"
                            >
                                {copy.languageHelp}
                            </p>
                            <div className="space-y-1">
                                <label
                                    className="block text-[0.95rem] font-semibold text-ink-2"
                                    htmlFor="gender"
                                >
                                    {copy.gender}{" "}
                                    <span className="font-normal text-muted">
                                        {copy.optional}
                                    </span>
                                </label>
                                <select
                                    className="min-h-[3.25rem] w-full rounded-2xl border border-line-strong bg-surface px-4 py-3 text-base text-ink outline-none focus:border-brand focus:ring-4 focus:ring-brand/15"
                                    id="gender"
                                    onChange={(event) =>
                                        setEditDraft((draft) =>
                                            draft
                                                ? {
                                                      ...draft,
                                                      gender: event.target
                                                          .value as
                                                          | Patient["gender"]
                                                          | "",
                                                  }
                                                : draft,
                                        )
                                    }
                                    value={editDraft.gender}
                                >
                                    <option value="">{copy.unspecified}</option>
                                    {Object.entries(genderLabels).map(
                                        ([value, label]) => (
                                            <option key={value} value={value}>
                                                {label}
                                            </option>
                                        ),
                                    )}
                                </select>
                            </div>
                            {saveError ? (
                                <div
                                    role="alert"
                                    className="rounded-2xl bg-danger-tint px-4 py-3 text-sm font-medium text-danger-ink"
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
                    </div>
                ) : null}
            </Modal>
            <Modal
                open={
                    !loading &&
                    !pageError &&
                    Boolean(patientProfile) &&
                    (joinExpanded ?? forceJoinOpen)
                }
                onClose={() => setJoinExpanded(false)}
                title={copy.addTeam}
                closeLabel={locale === "es-MX" ? "Cerrar" : "Close"}
            >
                <p className="mb-4 text-[15px] text-muted">{copy.joinHelp}</p>
                <div className="[&_label>span]:text-ink-2">
                    <form className="space-y-3" onSubmit={handleJoinClinic}>
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
                            className="text-sm text-muted"
                            id="profile-invite-help"
                        >
                            {copy.inviteHelp}
                        </p>
                        {joinError ? (
                            <div
                                role="alert"
                                className="rounded-2xl bg-danger-tint px-4 py-3 text-sm font-medium text-danger-ink"
                            >
                                {copy[joinError]}
                            </div>
                        ) : null}
                        {joinSuccess ? (
                            <div
                                role="status"
                                className="rounded-2xl bg-brand-tint px-4 py-3 text-sm font-medium text-brand-ink"
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
                </div>
            </Modal>
            <Modal
                keepMounted
                open={languageOpen}
                onClose={() => setLanguageOpen(false)}
                title={copy.language}
                closeLabel={locale === "es-MX" ? "Cerrar" : "Close"}
            >
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
