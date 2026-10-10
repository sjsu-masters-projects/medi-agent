"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  usePatientProfile,
  useSharedPatientProfile,
} from "@/hooks/use-patient-profile";
import {
  reminderDayLabel,
  remindersCopy,
} from "@/components/features/reminders-copy";
import { PageHeader } from "@/components/layouts";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Skeleton,
} from "@/components/ui";
import { api } from "@/services/api";
import {
  getBrowserTimezone,
  getSupportedTimezones,
} from "@/services/timezones";
import type { RootState } from "@/store/store";
import type {
  ReminderDayOfWeek,
  ReminderSchedule,
  ReminderTarget,
} from "@/types";
import { useSelector } from "react-redux";
import { HiArrowPath } from "react-icons/hi2";

const DAYS: ReminderDayOfWeek[] = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
];

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
    required_days_of_week?: ReminderDayOfWeek[] | null;
    guidance_text?: string | null;
  };
}

interface ScheduleDraft {
  timezone: string;
  timesOfDay: string[];
  daysOfWeek: ReminderDayOfWeek[];
}

function normalizeReminderSchedule(
  schedule?: ReminderScheduleResponse | null,
): ReminderSchedule | null {
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
      requiredDaysOfWeek: target.guidance.required_days_of_week,
      guidanceText: target.guidance.guidance_text,
    },
  };
}

function makeTargetKey(
  target: Pick<ReminderTarget, "targetId" | "targetType">,
) {
  return `${target.targetType}:${target.targetId}`;
}

function defaultDaysOfWeek(target: ReminderTarget): ReminderDayOfWeek[] {
  if (target.guidance.requiredDaysOfWeek?.length)
    return [...target.guidance.requiredDaysOfWeek];
  const count = target.guidance.recommendedDaysPerWeek;
  if (count === DAYS.length) {
    return DAYS;
  }
  return [];
}

function defaultTimesOfDay(target: ReminderTarget): string[] {
  return Array.from(
    { length: target.guidance.recommendedTimesPerDay || 1 },
    () => "",
  );
}

function buildDraft(target: ReminderTarget, timezone: string): ScheduleDraft {
  const schedule = target.reminderSchedule;
  if (schedule) {
    return {
      timezone: schedule.timezone,
      timesOfDay: schedule.timesOfDay.map((value) => value.slice(0, 5)),
      daysOfWeek: target.guidance.requiredDaysOfWeek?.length
        ? [...target.guidance.requiredDaysOfWeek]
        : schedule.daysOfWeek.length
          ? schedule.daysOfWeek
          : DAYS,
    };
  }
  return {
    timezone,
    timesOfDay: defaultTimesOfDay(target),
    daysOfWeek: defaultDaysOfWeek(target),
  };
}

export default function ReminderSettingsPage() {
  const profile = usePatientProfile();
  const sharedProfile = useSharedPatientProfile();
  const locale = profile?.preferredLanguage ?? "en-US";
  const savedTimezone = profile?.timezone;
  const copy = useCallback(
    (text: string) => remindersCopy(locale, text),
    [locale],
  );
  const accessToken = useSelector((state: RootState) => state.auth.accessToken);
  const [targets, setTargets] = useState<ReminderTarget[]>([]);
  const [patientTimezone, setPatientTimezone] = useState(getBrowserTimezone());
  const [drafts, setDrafts] = useState<Record<string, ScheduleDraft>>({});
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);
  const [savingTimezone, setSavingTimezone] = useState(false);
  const [savingTargetKey, setSavingTargetKey] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const timezones = useMemo(() => getSupportedTimezones(), []);

  const loadData = useCallback(async () => {
    if (!accessToken) {
      return;
    }
    setLoading(true);
    setPageError(null);
    try {
      const reminderTargets = await api.get<ReminderTargetResponse[]>(
        "/api/v1/reminders/targets",
        { token: accessToken },
      );
      const timezone = savedTimezone ?? getBrowserTimezone();
      const normalizedTargets = reminderTargets.map(normalizeTarget);
      setPatientTimezone(timezone);
      setTargets(normalizedTargets);
      setDrafts(
        Object.fromEntries(
          normalizedTargets.map((target) => [
            makeTargetKey(target),
            buildDraft(target, timezone),
          ]),
        ),
      );
    } catch {
      setPageError("We could not load your reminders. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [accessToken, savedTimezone]);

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
    setActionError(null);
  }

  async function saveTimezone() {
    if (!accessToken) {
      return;
    }
    setSavingTimezone(true);
    setActionMessage(null);
    setActionError(null);
    try {
      await api.put(
        "/api/v1/patients/me",
        { timezone: patientTimezone },
        { token: accessToken },
      );
      setActionMessage(copy("Timezone updated."));
      sharedProfile?.refresh();
      setDrafts((current) =>
        Object.fromEntries(
          Object.entries(current).map(([key, draft]) => [
            key,
            {
              ...draft,
              timezone: targets.find((target) => makeTargetKey(target) === key)
                ?.reminderSchedule
                ? draft.timezone
                : patientTimezone,
            },
          ]),
        ),
      );
    } catch {
      setActionError(
        copy(
          "We could not confirm your change. Refresh reminders before trying again. Your entered choices are kept here.",
        ),
      );
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
    setActionError(null);
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
      setEditingKey(null);
      setActionMessage(
        locale === "es-MX"
          ? `Recordatorio guardado: ${target.name}.`
          : `${target.name} reminder schedule saved.`,
      );
    } catch {
      setActionError(
        copy(
          "We could not confirm your change. Refresh reminders before trying again. Your entered choices are kept here.",
        ),
      );
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
    setActionError(null);
    try {
      await api.delete(
        `/api/v1/reminders/${target.targetType}/${target.targetId}`,
        {
          token: accessToken,
        },
      );
      await loadData();
      setActionMessage(
        locale === "es-MX"
          ? `Recordatorio eliminado: ${target.name}.`
          : `${target.name} reminder schedule removed.`,
      );
    } catch {
      setActionError(
        copy(
          "We could not confirm your change. Refresh reminders before trying again. Your entered choices are kept here.",
        ),
      );
    } finally {
      setSavingTargetKey(null);
    }
  }

  return (
    <div className="patient-page space-y-4 pb-8">
      <PageHeader
        rightAction={
          <Button
            disabled={
              loading ||
              savingTargetKey !== null ||
              savingTimezone ||
              editingKey !== null
            }
            onClick={() => void loadData()}
            variant="secondary"
            className="gap-2"
          >
            <HiArrowPath
              aria-hidden="true"
              className={
                loading
                  ? "h-5 w-5 shrink-0 motion-safe:animate-spin"
                  : "h-5 w-5 shrink-0"
              }
            />
            {copy(loading ? "Refreshing..." : "Refresh reminders")}
          </Button>
        }
        subtitle={copy(
          "Choose the exact days and times you want reminder nudges.",
        )}
        title={copy("Reminder Settings")}
      />
      <div className="patient-stack -mt-4 space-y-4 px-5">
        {loading && targets.length === 0 ? (
          <div className="space-y-4">
            <Skeleton className="h-40 w-full rounded-3xl" />
            <Skeleton className="h-64 w-full rounded-3xl" />
            <Skeleton className="h-64 w-full rounded-3xl" />
          </div>
        ) : null}

        {!loading && pageError ? (
          <ErrorState
            description={copy(pageError)}
            action={
              <Button onClick={() => void loadData()} variant="secondary">
                {copy("Try again")}
              </Button>
            }
            title={copy("Unable to load reminder settings")}
          />
        ) : null}

        {(!loading || targets.length > 0) &&
        (!pageError || targets.length > 0) ? (
          <>
            <Card className="space-y-4">
              <details>
                <summary className="min-h-11 cursor-pointer py-2 font-semibold">
                  {copy("Advanced settings")} ·{" "}
                  {patientTimezone.replaceAll("_", " ")}
                </summary>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-700">
                      {copy("Timezone")}
                    </p>
                    <h2 className="mt-1 text-xl font-semibold text-gray-700">
                      {copy("Your local schedule")}
                    </h2>
                    <p className="mt-1 text-base leading-7 text-gray-700">
                      {copy("Reminder times are interpreted in this timezone.")}
                    </p>
                  </div>
                </div>
                <select
                  aria-label={copy("Profile timezone")}
                  className="min-h-[3.25rem] min-w-0 w-full rounded-2xl border border-gray-200 bg-white/90 px-4 py-3 text-base text-gray-700 shadow-sm outline-none focus:border-blue-600 focus:ring-4 focus:ring-blue-500"
                  onChange={(event) => setPatientTimezone(event.target.value)}
                  value={patientTimezone}
                >
                  {timezones.map((timezone) => (
                    <option key={timezone} value={timezone}>
                      {timezone}
                    </option>
                  ))}
                </select>
                <Button
                  disabled={savingTimezone || editingKey !== null}
                  onClick={saveTimezone}
                  size="lg"
                >
                  {savingTimezone
                    ? copy("Saving timezone...")
                    : copy("Save timezone")}
                </Button>
              </details>
            </Card>

            {actionMessage ? (
              <Card className="border-green-100 bg-green-100 text-base font-medium text-green-800">
                <p role="status">{actionMessage}</p>
              </Card>
            ) : null}
            {actionError ? (
              <p
                role="alert"
                className="rounded-2xl bg-red-100 p-4 text-red-800"
              >
                {actionError}
              </p>
            ) : null}

            {targets.length === 0 ? (
              <EmptyState
                title={copy("No reminders to set")}
                description={copy(
                  "Reminders will appear here when your care team adds eligible medications or activities.",
                )}
              />
            ) : null}
            {targets.map((target) => {
              const key = makeTargetKey(target);
              const draft = drafts[key] ?? buildDraft(target, patientTimezone);
              const disableAutomatic =
                !target.guidance.supportsAutomaticReminders;
              const isSaving = savingTargetKey === key;
              const isEditing = editingKey === key;

              return (
                <Card className="space-y-4" key={key}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wide text-gray-700">
                        {target.targetType === "medication"
                          ? copy("Medication")
                          : copy("Care activity")}
                      </p>
                      <h3 className="mt-1 text-xl font-semibold text-gray-700">
                        {target.name}
                      </h3>
                      <p className="mt-1 text-base leading-7 text-gray-700">
                        {target.frequency}
                        {target.providerName ? ` · ${target.providerName}` : ""}
                      </p>
                    </div>
                    <Badge
                      variant={
                        target.reminderSchedule &&
                        !disableAutomatic &&
                        target.reminderSchedule.isEnabled
                          ? "success"
                          : "warning"
                      }
                    >
                      {target.reminderSchedule
                        ? disableAutomatic
                          ? copy("Review old reminder")
                          : copy(
                              target.reminderSchedule.isEnabled
                                ? "Configured"
                                : "Paused",
                            )
                        : disableAutomatic
                          ? copy("No routine reminder")
                          : copy("Not set")}
                    </Badge>
                  </div>

                  {target.description &&
                  target.description.trim() !== target.name.trim() ? (
                    <p className="text-base leading-7 text-gray-700">
                      {target.description}
                    </p>
                  ) : null}
                  {target.reminderSchedule ? (
                    <p className="text-sm text-gray-700">
                      {target.reminderSchedule.daysOfWeek
                        .map((day) => reminderDayLabel(locale, day))
                        .join(", ")}{" "}
                      ·{" "}
                      {target.reminderSchedule.timesOfDay
                        .map((value) => value.slice(0, 5))
                        .join(", ")}{" "}
                      · {target.reminderSchedule.timezone.replaceAll("_", " ")}
                    </p>
                  ) : null}
                  {!disableAutomatic && !isEditing ? (
                    <Button
                      onClick={() => {
                        setEditingKey(key);
                        setDrafts((current) =>
                          Object.fromEntries(
                            targets.map((entry) => [
                              makeTargetKey(entry),
                              makeTargetKey(entry) === key
                                ? (current[key] ??
                                  buildDraft(entry, patientTimezone))
                                : buildDraft(entry, patientTimezone),
                            ]),
                          ),
                        );
                      }}
                      disabled={editingKey !== null}
                      variant="secondary"
                    >
                      {target.reminderSchedule
                        ? copy("Edit reminder")
                        : copy("Set reminder")}
                    </Button>
                  ) : null}

                  {!disableAutomatic ? (
                    <div className="rounded-xl bg-gray-50 px-4 py-2 text-sm leading-7 text-gray-700 ring-1 ring-gray-200">
                      <details>
                        <summary className="min-h-11 cursor-pointer py-2 font-semibold">
                          {copy("Schedule help")}
                        </summary>
                        <p>
                          {copy(
                            target.guidance.guidanceText ??
                              "Follow the instruction above. Ask your care team if the timing is unclear.",
                          )}
                        </p>
                        {target.guidance.recommendedTimesPerDay ? (
                          <p>
                            {locale === "es-MX"
                              ? `Horas por día: ${target.guidance.recommendedTimesPerDay}`
                              : `Times per day: ${target.guidance.recommendedTimesPerDay}`}
                          </p>
                        ) : null}
                        {target.guidance.recommendedDaysPerWeek ? (
                          <p>
                            {locale === "es-MX"
                              ? `Días por semana: ${target.guidance.recommendedDaysPerWeek}`
                              : `Days per week: ${target.guidance.recommendedDaysPerWeek}`}
                          </p>
                        ) : null}
                      </details>
                    </div>
                  ) : null}

                  {disableAutomatic ? (
                    <p className="rounded-xl bg-yellow-100 p-4 text-sm text-yellow-800">
                      {target.guidance.guidanceText ? (
                        <span className="mb-2 block">
                          {copy(target.guidance.guidanceText)}
                        </span>
                      ) : null}
                      {copy(
                        "This item stays available in Today. Routine clock-time reminders require a clear care-team instruction.",
                      )}
                    </p>
                  ) : isEditing ? (
                    <>
                      <p className="text-sm text-gray-700">
                        {copy(
                          "Choose times that match the instruction above, including meal or activity timing. These are reminders, not changes to your care plan.",
                        )}
                      </p>
                      <p className="text-sm text-gray-700">
                        {copy("Reminder timezone:")}{" "}
                        {draft.timezone.replaceAll("_", " ")}
                      </p>
                      <div>
                        <p className="mb-3 text-base font-semibold text-gray-700">
                          {copy("Days")}
                        </p>
                        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                          {DAYS.map((day) => {
                            const checked = draft.daysOfWeek.includes(day);
                            return (
                              <label
                                className={`flex min-h-12 items-center gap-2 rounded-2xl border px-3 py-2 text-base font-medium transition ${checked ? "border-blue-100 bg-blue-100 text-blue-600" : "border-gray-200 bg-white/80 text-gray-700"}`}
                                key={day}
                              >
                                <input
                                  checked={checked}
                                  disabled={Boolean(
                                    target.guidance.requiredDaysOfWeek?.length,
                                  )}
                                  className="h-5 w-5 accent-blue-600"
                                  onChange={() =>
                                    updateDraft(target, (current) => ({
                                      ...current,
                                      daysOfWeek: checked
                                        ? current.daysOfWeek.filter(
                                            (value) => value !== day,
                                          )
                                        : [...current.daysOfWeek, day],
                                    }))
                                  }
                                  type="checkbox"
                                />
                                <span className="capitalize">
                                  {reminderDayLabel(locale, day)}
                                </span>
                              </label>
                            );
                          })}
                        </div>
                      </div>

                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <p className="text-base font-semibold text-gray-700">
                            {copy("Reminder times")}
                          </p>
                          <button
                            className="min-h-11 rounded-full px-3 text-sm font-semibold text-blue-600 hover:bg-blue-100"
                            onClick={() =>
                              updateDraft(target, (current) => ({
                                ...current,
                                timesOfDay: [...current.timesOfDay, ""],
                              }))
                            }
                            type="button"
                          >
                            {copy("Add time")}
                          </button>
                        </div>
                        {draft.timesOfDay.map((value, index) => (
                          <div
                            className="flex items-center gap-3"
                            key={`${key}-time-${index}`}
                          >
                            <input
                              aria-label={
                                locale === "es-MX"
                                  ? `Hora del recordatorio ${index + 1}`
                                  : `Reminder time ${index + 1}`
                              }
                              className="min-h-[3.25rem] min-w-0 w-full rounded-2xl border border-gray-200 bg-white/90 px-4 py-3 text-base text-gray-700 shadow-sm outline-none focus:border-blue-600 focus:ring-4 focus:ring-blue-500"
                              onChange={(event) =>
                                updateDraft(target, (current) => ({
                                  ...current,
                                  timesOfDay: current.timesOfDay.map(
                                    (entry, entryIndex) =>
                                      entryIndex === index
                                        ? event.target.value
                                        : entry,
                                  ),
                                }))
                              }
                              type="time"
                              value={value}
                            />
                            <button
                              className="min-h-11 rounded-full px-3 text-sm font-semibold text-red-800 hover:bg-red-100"
                              onClick={() =>
                                updateDraft(target, (current) => ({
                                  ...current,
                                  timesOfDay:
                                    current.timesOfDay.length === 1
                                      ? current.timesOfDay
                                      : current.timesOfDay.filter(
                                          (_, entryIndex) =>
                                            entryIndex !== index,
                                        ),
                                }))
                              }
                              type="button"
                            >
                              {copy("Remove")}
                            </button>
                          </div>
                        ))}
                      </div>
                    </>
                  ) : null}

                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {isEditing ? (
                      <Button
                        disabled={
                          isSaving ||
                          disableAutomatic ||
                          draft.daysOfWeek.length === 0 ||
                          draft.timesOfDay.length === 0 ||
                          draft.timesOfDay.some((value) => !value) ||
                          (target.guidance.recommendedTimesPerDay != null &&
                            draft.timesOfDay.length !==
                              target.guidance.recommendedTimesPerDay) ||
                          (target.guidance.recommendedDaysPerWeek != null &&
                            draft.daysOfWeek.length !==
                              target.guidance.recommendedDaysPerWeek)
                        }
                        onClick={() => void saveSchedule(target)}
                        size="lg"
                      >
                        {isSaving
                          ? copy("Saving...")
                          : copy("Save reminder schedule")}
                      </Button>
                    ) : null}
                    {isEditing ? (
                      <Button
                        disabled={isSaving}
                        variant="secondary"
                        onClick={() => {
                          setEditingKey(null);
                          setDrafts((current) => ({
                            ...current,
                            [key]: buildDraft(target, patientTimezone),
                          }));
                        }}
                      >
                        {copy("Cancel")}
                      </Button>
                    ) : null}
                    {target.reminderSchedule ? (
                      <Button
                        disabled={
                          isSaving ||
                          (editingKey !== null && editingKey !== key)
                        }
                        onClick={() => void clearSchedule(target)}
                        size="lg"
                        variant="secondary"
                      >
                        {copy("Clear schedule")}
                      </Button>
                    ) : null}
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
