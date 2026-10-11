"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useDispatch, useSelector } from "react-redux";
import { PageHeader } from "@/components/layouts";
import { PatientLanguageControl } from "@/components/layouts/patient-language-control";
import { Modal } from "@/components/ui/modal";
import { Icon } from "@/components/ui/icons";
import { IconTile } from "@/components/ui/list";
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
    gender?: Patient["gender"] | null;
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
        gender: profile.gender ?? undefined,
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
                    // Always sent so "Not specified" clears a saved value.
                    gender: editDraft.gender || null,
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

    const languageName = locale === "es-MX" ? "Español (México)" : "English (US)";
    const rowClass = "flex min-h-[52px] items-center justify-between gap-3 px-4 py-3";
    const groupClass = "mx-4 overflow-hidden rounded-[22px] bg-surface [&>*+*]:border-t [&>*+*]:border-line";
    const eyebrowClass = "px-[22px] pt-5 pb-2 font-mono text-xs uppercase tracking-[0.08em] text-muted";
    const chevron = <Icon name="chevron" className="h-[18px] w-[18px] shrink-0 text-faint" />;
    const initialsOf = (first?: string, last?: string) => `${first?.charAt(0) ?? ""}${last?.charAt(0) ?? ""}`.toUpperCase() || "?";
    // "America/Los_Angeles" reads as "Pacific Time · Los Angeles"; unknown zones fall back to the raw name.
    const formatTimezone = (zone: string) => {
        try {
            const name = new Intl.DateTimeFormat(locale, { timeZone: zone, timeZoneName: "longGeneric" })
                .formatToParts(new Date())
                .find((part) => part.type === "timeZoneName")?.value;
            const city = zone.includes("/") ? zone.split("/").pop()?.replaceAll("_", " ") : null;
            return name && city ? `${name} · ${city}` : name ?? zone;
        } catch {
            return zone;
        }
    };
    const formatBirthDate = (value: string) => {
        const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
        if (!match) return value;
        const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
        return date.toLocaleDateString(locale, { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
    };

    return (
        <div className="patient-page pb-8">
            <PageHeader title={copy.title} />
            <div className="patient-stack">
                {loading || pageError ? (
                    <div className="px-4 pt-2">
                        <button
                            type="button"
                            onClick={() => setLanguageOpen(true)}
                            className={`${rowClass} w-full rounded-[22px] bg-surface text-left text-[15px] font-semibold text-brand`}
                        >
                            <span className="flex items-center gap-3"><Icon name="globe" className="h-5 w-5" />{copy.language}</span>
                            {chevron}
                        </button>
                    </div>
                ) : null}
                {loading ? (
                    <div className="space-y-4 px-4 pt-4" aria-hidden="true">
                        <Skeleton className="h-[84px] w-full" />
                        <Skeleton className="h-48 w-full" />
                        <Skeleton className="h-40 w-full" />
                    </div>
                ) : null}
                {!loading && pageError ? (
                    <div className="px-4 pt-4">
                        <ErrorState
                            description={copy.loadError}
                            action={
                                <Button size="sm" onClick={() => window.location.reload()}>
                                    {copy.retry}
                                </Button>
                            }
                            title={copy.loadTitle}
                        />
                    </div>
                ) : null}
                {!loading && !pageError && patientProfile ? (
                    <>
                        <div className="mx-4 mt-2 flex items-center gap-3.5 rounded-[22px] bg-surface px-4 py-4">
                            <div
                                aria-hidden="true"
                                className="flex h-[52px] w-[52px] shrink-0 items-center justify-center rounded-full bg-brand-tint text-xl font-semibold text-brand"
                            >
                                {patientProfile.firstName.charAt(0)}
                            </div>
                            <div className="min-w-0">
                                <p className="sr-only">{copy.patientAccount}</p>
                                <h2 className="break-words text-[20px] font-semibold leading-tight text-ink">
                                    {patientProfile.firstName}{" "}
                                    {patientProfile.lastName}
                                </h2>
                                <p className="mt-0.5 break-all text-[13px] text-muted">
                                    {patientProfile.email}
                                </p>
                            </div>
                        </div>
                        {showJoinClinicPrompt ? (
                            <p className="mx-4 mt-3 flex items-start gap-2.5 rounded-[18px] bg-note-tint px-4 py-3 text-sm font-medium text-note-ink">
                                <Icon name="info" className="mt-px h-[18px] w-[18px] shrink-0" />
                                {copy.onboarding}
                            </p>
                        ) : null}
                        <section aria-labelledby="profile-personal">
                            <div className="flex items-end justify-between gap-3 pr-4">
                                <p className="sr-only">{copy.details}</p>
                                <h3 id="profile-personal" className={eyebrowClass}>
                                    {copy.personal}
                                </h3>
                                <button
                                    aria-label={copy.editProfile}
                                    className="ma-press mb-0.5 inline-flex min-h-11 min-w-11 items-center justify-center gap-1.5 rounded-xl px-2.5 text-sm font-semibold text-brand hover:bg-brand-tint/60"
                                    onClick={startEditing}
                                    type="button"
                                >
                                    {copy.edit}
                                </button>
                            </div>
                            {saveSuccess && !editing ? (
                                <p
                                    role="status"
                                    className="ma-enter mx-4 mb-2 flex items-center gap-2 rounded-2xl bg-brand-tint px-4 py-3 text-sm font-medium text-brand-ink"
                                >
                                    <Icon name="check" className="h-4 w-4 shrink-0" />
                                    {copy.saved}
                                </p>
                            ) : null}
                            <dl className={`${groupClass} text-[15px]`}>
                                <div className={rowClass}>
                                    <dt className="text-ink-2">{copy.dob}</dt>
                                    <dd className="text-right font-medium text-ink">
                                        <time dateTime={patientProfile.dateOfBirth}>{formatBirthDate(patientProfile.dateOfBirth)}</time>
                                    </dd>
                                </div>
                                <div className={`relative ${rowClass}`}>
                                    <dt className="flex items-center gap-2.5 text-ink-2">
                                        <Icon name="globe" className="h-[18px] w-[18px] text-muted" />
                                        {copy.language}
                                    </dt>
                                    <dd>
                                        <button
                                            type="button"
                                            onClick={() =>
                                                setLanguageOpen(true)
                                            }
                                            className="ma-press inline-flex min-h-11 items-center gap-1.5 rounded-xl text-right font-medium text-ink after:absolute after:inset-0 after:content-[''] hover:text-brand"
                                        >
                                            {languageName}
                                            {chevron}
                                        </button>
                                    </dd>
                                </div>
                                {patientProfile.gender ? (
                                    <div className={rowClass}>
                                        <dt className="text-ink-2">
                                            {copy.gender}
                                        </dt>
                                        <dd className="text-right font-medium text-ink">
                                            {genderLabels[
                                                patientProfile.gender
                                            ] ?? copy.unspecified}
                                        </dd>
                                    </div>
                                ) : null}
                                <div className={rowClass}>
                                    <dt className="text-ink-2">
                                        {copy.timezone}
                                    </dt>
                                    <dd className="min-w-0 text-right font-medium text-ink" title={patientProfile.timezone ?? "UTC"}>
                                        {formatTimezone(patientProfile.timezone ?? "UTC")}
                                    </dd>
                                </div>
                            </dl>
                        </section>
                        <section aria-labelledby="profile-reminders">
                            <h3 id="profile-reminders" className={eyebrowClass}>
                                {copy.reminders}
                            </h3>
                            <div className={groupClass}>
                                <Link
                                    aria-label={copy.manageReminders}
                                    className="flex min-h-11 items-center gap-3 px-[14px] py-3 text-left hover:bg-[#FBF7F0]"
                                    href="/reminders"
                                >
                                    <IconTile icon="bell" tone="brand" />
                                    <div className="min-w-0 flex-1">
                                        <p className="break-words text-[15px] font-semibold text-ink">{copy.reminderTitle}</p>
                                        <p className="mt-0.5 break-words text-[13px] text-muted">
                                            {copy.reminderHelp}
                                        </p>
                                    </div>
                                    {chevron}
                                </Link>
                            </div>
                        </section>
                        <section aria-labelledby="profile-team">
                            <p className="sr-only">{copy.connected}</p>
                            <h3 id="profile-team" className={eyebrowClass}>
                                {copy.teams}
                            </h3>
                            <div className={groupClass}>
                                {careTeam.length ? (
                                    careTeam.map((member) => (
                                        <div
                                            className="flex items-center gap-3 px-[14px] py-3"
                                            key={member.id}
                                        >
                                            <span aria-hidden="true" className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-note-tint text-sm font-semibold text-note-ink">{initialsOf(member.clinicianFirstName, member.clinicianLastName)}</span>
                                            <div className="min-w-0 flex-1">
                                                <p className="break-words text-[15px] font-semibold text-ink">
                                                    {member.clinicianFirstName}{" "}
                                                    {member.clinicianLastName}
                                                </p>
                                                <p className="mt-0.5 break-words text-[13px] text-muted">
                                                    <span>{careTeamRoleLabel(
                                                        member.role,
                                                        locale,
                                                    )}</span>
                                                    <span aria-hidden="true"> · </span>
                                                    <span>{member.clinicName ||
                                                        member.specialtyContext ||
                                                        copy.teamFallback}</span>
                                                </p>
                                            </div>
                                            <span
                                                className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${member.status === "active" ? "bg-brand-tint text-brand-ink" : "bg-surface-2 text-ink-2"}`}
                                            >
                                                {member.status === "active" ? <Icon name="check" className="h-3 w-3" /> : null}
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
                                    ))
                                ) : (
                                    <div>
                                        <EmptyState
                                            description={copy.noTeamsHelp}
                                            icon={<Icon name="building" />}
                                            title={copy.noTeams}
                                        />
                                    </div>
                                )}
                                {hasActiveTeam ? (
                                    <Link
                                        className="flex min-h-11 items-center gap-3 px-[14px] py-3 text-[15px] font-semibold text-brand hover:bg-[#FBF7F0]"
                                        href="/chat"
                                    >
                                        <IconTile icon="chat" tone="brand" />
                                        <span className="min-w-0 flex-1">{copy.messages}</span>
                                        {chevron}
                                    </Link>
                                ) : null}
                                <button
                                    className="flex min-h-11 w-full items-center gap-3 px-[14px] py-3 text-left text-[15px] font-semibold text-ink hover:bg-[#FBF7F0]"
                                    type="button"
                                    onClick={() => setJoinExpanded(true)}
                                >
                                    <IconTile icon="plus" tone="neutral" />
                                    <span className="min-w-0 flex-1 break-words">
                                        {careTeam.length
                                            ? copy.joinAnother
                                            : copy.connectClinic}
                                    </span>
                                    {chevron}
                                </button>
                            </div>
                            {hasActiveTeam ? (
                                <p className="px-[22px] pt-2 text-[13px] leading-relaxed text-muted">
                                    {copy.messageHelp}
                                </p>
                            ) : null}
                        </section>
                        <section aria-labelledby="profile-account">
                            <h3 className={eyebrowClass}>{copy.account}</h3>
                            <div className={groupClass}>
                                <button
                                    aria-label={copy.signOut}
                                    className="flex min-h-11 w-full items-center gap-3 px-[14px] py-3 text-left hover:bg-danger-tint/40"
                                    type="button"
                                    onClick={handleLogout}
                                >
                                    <IconTile icon="logout" tone="danger" />
                                    <span className="min-w-0 flex-1">
                                        <span
                                            id="profile-account"
                                            className="block break-words text-[15px] font-semibold text-danger-ink"
                                        >
                                            {copy.signOut}
                                        </span>
                                        <span className="mt-0.5 block break-words text-[13px] font-normal text-muted">
                                            {copy.signOutHelp}
                                        </span>
                                    </span>
                                </button>
                            </div>
                        </section>
                    </>
                ) : null}
            </div>
            <Modal
                open={editing}
                onClose={() => {
                    if (!saving) cancelEditing();
                }}
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
                            <div className="rounded-2xl bg-surface-2 px-4 py-3" aria-describedby="profile-dob-help">
                                <p className="flex items-center justify-between gap-3 text-[15px]">
                                    <span className="font-semibold text-ink-2">{copy.dob}</span>
                                    <time className="flex items-center gap-1.5 font-medium text-ink" dateTime={patientProfile?.dateOfBirth}>
                                        <Icon name="lock" className="h-4 w-4 text-muted" />
                                        {patientProfile ? formatBirthDate(patientProfile.dateOfBirth) : ""}
                                    </time>
                                </p>
                                <p className="mt-1 text-[13px] leading-5 text-muted" id="profile-dob-help">{copy.dobLocked}</p>
                            </div>
                            <div className="space-y-1">
                                <label
                                    className="block text-[0.95rem] font-semibold text-ink-2"
                                    htmlFor="preferred-language"
                                >
                                    {copy.language}
                                </label>
                                <select
                                    className="min-h-[3.25rem] min-w-0 w-full rounded-2xl border border-line-strong bg-surface pl-4 pr-10 py-3 text-base text-ink outline-none focus:border-brand focus:ring-4 focus:ring-brand/15"
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
                                    className="min-h-[3.25rem] min-w-0 w-full rounded-2xl border border-line-strong bg-surface pl-4 pr-10 py-3 text-base text-ink outline-none focus:border-brand focus:ring-4 focus:ring-brand/15"
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
                title={careTeam.length ? copy.addTeam : copy.connectClinic}
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
                <div>
                    <PatientLanguageControl />
                </div>
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
