"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/layouts";
import { Badge, Button, Card, ErrorState, Skeleton } from "@/components/ui";
import { api } from "@/services/api";
import { getBrowserTimezone, getSupportedTimezones } from "@/services/timezones";
import type { RootState } from "@/store/store";
import type { ReminderDayOfWeek, ReminderSchedule, ReminderTarget } from "@/types";
import { useSelector } from "react-redux";

const DAYS: ReminderDayOfWeek[] = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
];

interface PatientProfileResponse {
    timezone?: string;
}

interface ReminderScheduleResponse {
    id: string;
    patient_id: string;
    target_type: ReminderTarget["targetType"];
    target_id: string;
    timezone: string;
    times_of_day: string[];
    days_of_week: ReminderDayOfWeek[];
    is_enabled: boolean;
    created_at: string;
    updated_at?: string;
}

interface ReminderTargetResponse {
    target_type: ReminderTarget["targetType"];
    target_id: string;
    name: string;
    description?: string;
    frequency: string;
    provider_name?: string;
    reminder_schedule?: ReminderScheduleResponse | null;
    guidance: {
        supports_automatic_reminders: boolean;
        recommended_times_per_day?: number | null;
        recommended_days_per_week?: number | null;
        guidance_text?: string | null;
    };
}

interface ScheduleDraft {
    timezone: string;
    timesOfDay: string[];
    daysOfWeek: ReminderDayOfWeek[];
}

function normalizeReminderSchedule(schedule?: ReminderScheduleResponse | null): ReminderSchedule | null {
    if (!schedule) {
        return null;
    }
    return {
        id: schedule.id,
        patientId: schedule.patient_id,
        targetType: schedule.target_type,
        targetId: schedule.target_id,
        timezone: schedule.timezone,
        timesOfDay: schedule.times_of_day,
        daysOfWeek: schedule.days_of_week,
        isEnabled: schedule.is_enabled,
        createdAt: schedule.created_at,
        updatedAt: schedule.updated_at,
    };
}

function normalizeTarget(target: ReminderTargetResponse): ReminderTarget {
    return {
        targetType: target.target_type,
        targetId: target.target_id,
        name: target.name,
        description: target.description,
        frequency: target.frequency,
        providerName: target.provider_name,
        reminderSchedule: normalizeReminderSchedule(target.reminder_schedule),
        guidance: {
            supportsAutomaticReminders: target.guidance.supports_automatic_reminders,
            recommendedTimesPerDay: target.guidance.recommended_times_per_day,
            recommendedDaysPerWeek: target.guidance.recommended_days_per_week,
            guidanceText: target.guidance.guidance_text,
        },
    };
}

function makeTargetKey(target: Pick<ReminderTarget, "targetId" | "targetType">) {
    return `${target.targetType}:${target.targetId}`;
}

function defaultDaysOfWeek(target: ReminderTarget): ReminderDayOfWeek[] {
    const count = target.guidance.recommendedDaysPerWeek;
    if (!count || count >= DAYS.length) {
        return DAYS;
    }
    return DAYS.slice(0, count);
}

function defaultTimesOfDay(target: ReminderTarget): string[] {
    switch (target.guidance.recommendedTimesPerDay) {
        case 3:
            return ["08:00", "13:00", "20:00"];
        case 2:
            return ["08:00", "20:00"];
        case 1:
            return ["08:00"];
        default:
            return ["08:00"];
    }
}

function buildDraft(target: ReminderTarget, timezone: string): ScheduleDraft {
    const schedule = target.reminderSchedule;
    if (schedule) {
        return {
            timezone: schedule.timezone,
            timesOfDay: schedule.timesOfDay.map((value) => value.slice(0, 5)),
            daysOfWeek: schedule.daysOfWeek.length ? schedule.daysOfWeek : DAYS,
        };
    }
    return {
        timezone,
        timesOfDay: defaultTimesOfDay(target),
        daysOfWeek: defaultDaysOfWeek(target),
    };
}

export default function ReminderSettingsPage() {
    const accessToken = useSelector((state: RootState) => state.auth.accessToken);
    const [targets, setTargets] = useState<ReminderTarget[]>([]);
    const [patientTimezone, setPatientTimezone] = useState(getBrowserTimezone());
    const [drafts, setDrafts] = useState<Record<string, ScheduleDraft>>({});
    const [loading, setLoading] = useState(true);
    const [pageError, setPageError] = useState<string | null>(null);
    const [savingTimezone, setSavingTimezone] = useState(false);
    const [savingTargetKey, setSavingTargetKey] = useState<string | null>(null);
    const [actionMessage, setActionMessage] = useState<string | null>(null);
    const timezones = useMemo(() => getSupportedTimezones(), []);

    const loadData = useCallback(async () => {
        if (!accessToken) {
            return;
        }
        setLoading(true);
        setPageError(null);
        try {
            const [profile, reminderTargets] = await Promise.all([
                api.get<PatientProfileResponse>("/api/v1/patients/me", { token: accessToken }),
                api.get<ReminderTargetResponse[]>("/api/v1/reminders/targets", { token: accessToken }),
            ]);
            const timezone = profile.timezone ?? getBrowserTimezone();
            const normalizedTargets = reminderTargets.map(normalizeTarget);
            setPatientTimezone(timezone);
            setTargets(normalizedTargets);
            setDrafts(
                Object.fromEntries(
                    normalizedTargets.map((target) => [makeTargetKey(target), buildDraft(target, timezone)]),
                ),
            );
        } catch (error) {
            setPageError((error as Error).message);
        } finally {
            setLoading(false);
        }
    }, [accessToken]);

    useEffect(() => {
        void loadData();
    }, [loadData]);

    function updateDraft(
        target: ReminderTarget,
        updater: (current: ScheduleDraft) => ScheduleDraft,
    ) {
        const key = makeTargetKey(target);
        setDrafts((current) => ({
            ...current,
            [key]: updater(current[key] ?? buildDraft(target, patientTimezone)),
        }));
        setActionMessage(null);
    }

    async function saveTimezone() {
        if (!accessToken) {
            return;
        }
        setSavingTimezone(true);
        setActionMessage(null);
        try {
            await api.put(
                "/api/v1/patients/me",
                { timezone: patientTimezone },
                { token: accessToken },
            );
            setActionMessage("Timezone updated.");
            setDrafts((current) =>
                Object.fromEntries(
                    Object.entries(current).map(([key, draft]) => [
                        key,
                        { ...draft, timezone: patientTimezone },
                    ]),
                ),
            );
        } catch (error) {
            setPageError((error as Error).message);
        } finally {
            setSavingTimezone(false);
        }
    }

    async function saveSchedule(target: ReminderTarget) {
        if (!accessToken) {
            return;
        }
        const key = makeTargetKey(target);
        const draft = drafts[key];
        if (!draft) {
            return;
        }
        setSavingTargetKey(key);
        setActionMessage(null);
        try {
            await api.put(
                `/api/v1/reminders/${target.targetType}/${target.targetId}`,
                {
                    timezone: draft.timezone,
                    times_of_day: draft.timesOfDay,
                    days_of_week: draft.daysOfWeek,
                    is_enabled: true,
                },
                { token: accessToken },
            );
            await loadData();
            setActionMessage(`${target.name} reminder schedule saved.`);
        } catch (error) {
            setPageError((error as Error).message);
        } finally {
            setSavingTargetKey(null);
        }
    }

    async function clearSchedule(target: ReminderTarget) {
        if (!accessToken) {
            return;
        }
        const key = makeTargetKey(target);
        setSavingTargetKey(key);
        setActionMessage(null);
        try {
            await api.delete(`/api/v1/reminders/${target.targetType}/${target.targetId}`, {
                token: accessToken,
            });
            await loadData();
            setActionMessage(`${target.name} reminder schedule removed.`);
        } catch (error) {
            setPageError((error as Error).message);
        } finally {
            setSavingTargetKey(null);
        }
    }

    return (
        <div className="space-y-4 bg-gray-50 pb-8">
            <PageHeader
                subtitle="Choose the exact days and times you want reminder nudges."
                title="Reminder Settings"
            />
            <div className="-mt-4 space-y-4 px-5">
                {loading ? (
                    <div className="space-y-4">
                        <Skeleton className="h-40 w-full rounded-3xl" />
                        <Skeleton className="h-64 w-full rounded-3xl" />
                        <Skeleton className="h-64 w-full rounded-3xl" />
                    </div>
                ) : null}

                {!loading && pageError ? (
                    <ErrorState
                        description={pageError}
                        onRetry={() => void loadData()}
                        title="Unable to load reminder settings"
                    />
                ) : null}

                {!loading && !pageError ? (
                    <>
                        <Card className="space-y-4">
                            <div className="flex items-start justify-between gap-3">
                                <div>
                                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Timezone</p>
                                    <h2 className="mt-1 text-lg font-semibold text-slate-900">Your local schedule</h2>
                                    <p className="mt-1 text-sm text-slate-500">
                                        Reminder times are interpreted in this timezone.
                                    </p>
                                </div>
                                <Badge variant="info">Saved to profile</Badge>
                            </div>
                            <select
                                className="w-full rounded-xl border border-gray-300 bg-white px-3 py-2.5 text-sm text-gray-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                onChange={(event) => setPatientTimezone(event.target.value)}
                                value={patientTimezone}
                            >
                                {timezones.map((timezone) => (
                                    <option key={timezone} value={timezone}>
                                        {timezone}
                                    </option>
                                ))}
                            </select>
                            <Button disabled={savingTimezone} onClick={saveTimezone}>
                                {savingTimezone ? "Saving timezone..." : "Save timezone"}
                            </Button>
                        </Card>

                        {actionMessage ? (
                            <Card className="border-green-200 bg-green-50 text-sm text-green-800">
                                {actionMessage}
                            </Card>
                        ) : null}

                        {targets.map((target) => {
                            const key = makeTargetKey(target);
                            const draft = drafts[key] ?? buildDraft(target, patientTimezone);
                            const disableAutomatic = !target.guidance.supportsAutomaticReminders;
                            const isSaving = savingTargetKey === key;

                            return (
                                <Card className="space-y-4" key={key}>
                                    <div className="flex items-start justify-between gap-3">
                                        <div>
                                            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                                                {target.targetType}
                                            </p>
                                            <h3 className="mt-1 text-lg font-semibold text-slate-900">
                                                {target.name}
                                            </h3>
                                            <p className="mt-1 text-sm text-slate-500">
                                                {target.frequency}
                                                {target.providerName ? ` · ${target.providerName}` : ""}
                                            </p>
                                        </div>
                                        <Badge variant={target.reminderSchedule ? "success" : "warning"}>
                                            {target.reminderSchedule ? "Configured" : "Needs setup"}
                                        </Badge>
                                    </div>

                                    {target.description ? (
                                        <p className="text-sm text-slate-600">{target.description}</p>
                                    ) : null}

                                    {target.guidance.guidanceText ? (
                                        <div className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
                                            {target.guidance.guidanceText}
                                        </div>
                                    ) : null}

                                    {disableAutomatic ? (
                                        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                                            Automatic reminders are off for as-needed items. Keep this regimen available in Today, but only set reminders if your clinician specifically asked you to.
                                        </div>
                                    ) : (
                                        <>
                                            <div>
                                                <p className="mb-2 text-sm font-medium text-gray-700">Days</p>
                                                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                                                    {DAYS.map((day) => {
                                                        const checked = draft.daysOfWeek.includes(day);
                                                        return (
                                                            <label
                                                                className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-700"
                                                                key={day}
                                                            >
                                                                <input
                                                                    checked={checked}
                                                                    onChange={() =>
                                                                        updateDraft(target, (current) => ({
                                                                            ...current,
                                                                            daysOfWeek: checked
                                                                                ? current.daysOfWeek.filter((value) => value !== day)
                                                                                : [...current.daysOfWeek, day],
                                                                        }))
                                                                    }
                                                                    type="checkbox"
                                                                />
                                                                <span className="capitalize">{day.slice(0, 3)}</span>
                                                            </label>
                                                        );
                                                    })}
                                                </div>
                                            </div>

                                            <div className="space-y-3">
                                                <div className="flex items-center justify-between">
                                                    <p className="text-sm font-medium text-gray-700">Reminder times</p>
                                                    <button
                                                        className="text-sm font-medium text-sky-700"
                                                        onClick={() =>
                                                            updateDraft(target, (current) => ({
                                                                ...current,
                                                                timesOfDay: [...current.timesOfDay, "12:00"],
                                                            }))
                                                        }
                                                        type="button"
                                                    >
                                                        Add time
                                                    </button>
                                                </div>
                                                {draft.timesOfDay.map((value, index) => (
                                                    <div className="flex items-center gap-3" key={`${key}-time-${index}`}>
                                                        <input
                                                            className="w-full rounded-xl border border-gray-300 px-3 py-2.5 text-sm text-gray-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                                            onChange={(event) =>
                                                                updateDraft(target, (current) => ({
                                                                    ...current,
                                                                    timesOfDay: current.timesOfDay.map((entry, entryIndex) =>
                                                                        entryIndex === index ? event.target.value : entry,
                                                                    ),
                                                                }))
                                                            }
                                                            type="time"
                                                            value={value}
                                                        />
                                                        <button
                                                            className="text-sm font-medium text-red-600"
                                                            onClick={() =>
                                                                updateDraft(target, (current) => ({
                                                                    ...current,
                                                                    timesOfDay:
                                                                        current.timesOfDay.length === 1
                                                                            ? current.timesOfDay
                                                                            : current.timesOfDay.filter((_, entryIndex) => entryIndex !== index),
                                                                }))
                                                            }
                                                            type="button"
                                                        >
                                                            Remove
                                                        </button>
                                                    </div>
                                                ))}
                                            </div>
                                        </>
                                    )}

                                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                                        <Button
                                            disabled={
                                                isSaving
                                                || disableAutomatic
                                                || draft.daysOfWeek.length === 0
                                                || draft.timesOfDay.length === 0
                                            }
                                            onClick={() => void saveSchedule(target)}
                                        >
                                            {isSaving ? "Saving..." : "Save reminder schedule"}
                                        </Button>
                                        <Button
                                            disabled={isSaving || !target.reminderSchedule}
                                            onClick={() => void clearSchedule(target)}
                                            variant="secondary"
                                        >
                                            Clear schedule
                                        </Button>
                                    </div>
                                </Card>
                            );
                        })}
                    </>
                ) : null}
            </div>
        </div>
    );
}
