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
import { Icon } from "@/components/ui/icons";
import { IconTile } from "@/components/ui/list";
import {
  Button,
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
  content_locale?: string | null;
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
    contentLocale: target.content_locale === "en-US" || target.content_locale === "es-MX" ? target.content_locale : undefined,
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
    <div className="patient-page space-y-4 pb-6">
      <PageHeader
        rightAction={
          <Button
            aria-label={copy(loading ? "Refreshing..." : "Refresh reminders")}
            title={copy("Refresh reminders")}
            disabled={
              loading ||
              savingTargetKey !== null ||
              savingTimezone ||
              editingKey !== null
            }
            onClick={() => void loadData()}
            variant="ghost"
            className="h-11 w-11 rounded-[14px] p-0 text-ink-2 hover:bg-surface"
          >
            <Icon
              name="refresh"
              className={
                loading
                  ? "h-5 w-5 shrink-0 motion-safe:animate-spin"
                  : "h-5 w-5 shrink-0"
              }
            />
          </Button>
        }
        subtitle={copy(
          "Choose the exact days and times you want reminder nudges.",
        )}
        title={copy("Reminder Settings")}
        backButton
      />
      <div className="patient-stack space-y-4 px-4">
        {loading && targets.length === 0 ? (
          <div className="space-y-4">
            <Skeleton className="h-16 w-full rounded-[22px]" />
            <Skeleton className="h-32 w-full rounded-[22px]" />
            <Skeleton className="h-32 w-full rounded-[22px]" />
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
            <section className="rounded-[22px] bg-surface">
              <details className="group">
                <summary className="flex min-h-[56px] cursor-pointer list-none items-center gap-3 px-[14px] py-2 [&::-webkit-details-marker]:hidden">
                  <span aria-hidden="true" className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-surface-2 text-ink-2"><Icon name="globe" className="h-5 w-5" /></span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[15px] font-semibold text-ink">{copy("Advanced settings")}</span>
                    <span className="block break-words text-[13px] text-muted">{patientTimezone.replaceAll("_", " ")}</span>
                  </span>
                  <Icon name="chevronDown" className="h-[18px] w-[18px] shrink-0 text-muted transition-transform duration-[240ms] group-open:rotate-180" />
                </summary>
                <div className="border-t border-line px-[14px] pt-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-mono text-xs uppercase tracking-[0.08em] text-muted">
                      {copy("Timezone")}
                    </p>
                    <h2 className="mt-1 text-[17px] font-semibold text-ink">
                      {copy("Your local schedule")}
                    </h2>
                    <p className="mt-1 text-sm leading-6 text-muted">
                      {copy("Reminder times are interpreted in this timezone.")}
                    </p>
                  </div>
                </div>
                <select
                  aria-label={copy("Profile timezone")}
                  className="mt-3 min-h-[52px] min-w-0 w-full rounded-2xl border border-line-strong bg-surface px-4 py-2 text-base text-ink outline-none focus:border-brand focus:ring-4 focus:ring-brand/15"
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
                  className="my-3"
                  disabled={savingTimezone || editingKey !== null}
                  onClick={saveTimezone}
                  fullWidth
                >
                  {savingTimezone
                    ? copy("Saving timezone...")
                    : copy("Save timezone")}
                </Button>
                </div>
              </details>
            </section>

            {actionMessage ? (
              <p role="status" className="ma-enter flex items-start gap-2.5 rounded-2xl bg-brand-tint px-4 py-3 text-sm font-medium text-brand-ink">
                <Icon name="check" className="mt-px h-4 w-4 shrink-0" />{actionMessage}
              </p>
            ) : null}
            {actionError ? (
              <p
                role="alert"
                className="rounded-2xl bg-danger-tint p-4 text-sm text-danger-ink"
              >
                {actionError}
              </p>
            ) : null}

            {targets.length === 0 ? (
              <div className="rounded-[22px] bg-surface"><EmptyState
                icon={<Icon name="bell" />}
                title={copy("No reminders to set")}
                description={copy(
                  "Reminders will appear here when your care team adds eligible medications or activities.",
                )}
              /></div>
            ) : null}
            <div className="space-y-3">
              {targets.map((target) => {
                const key = makeTargetKey(target);
                const draft =
                  drafts[key] ?? buildDraft(target, patientTimezone);
                const disableAutomatic =
                  !target.guidance.supportsAutomaticReminders;
                const isSaving = savingTargetKey === key;
                const isEditing = editingKey === key;

                return (
                  <article
                    className={`space-y-3 rounded-[22px] bg-surface p-4 transition-shadow duration-[240ms] ${isEditing ? "shadow-[var(--shadow-raised)] ring-1 ring-brand/20" : ""}`}
                    key={key}
                  >
                    <div className="flex items-start gap-3">
                      <IconTile icon={target.targetType === "medication" ? "pill" : "check"} tone={target.targetType === "medication" ? "med" : "neutral"} />
                      <div className="min-w-0 flex-1">
                        <p className="font-mono text-xs uppercase tracking-[0.08em] text-muted">
                          {target.targetType === "medication"
                            ? copy("Medication")
                            : copy("Care activity")}
                        </p>
                        <h3 lang={target.contentLocale} className="mt-0.5 break-words text-[17px] font-semibold leading-snug text-ink [overflow-wrap:anywhere]">
                          {target.name}
                        </h3>
                        {target.contentLocale && target.contentLocale !== locale ? (
                          <p className="mt-0.5 flex items-center gap-1.5 text-[12px] font-medium text-muted">
                            <Icon name="globe" className="h-3.5 w-3.5 shrink-0" />
                            {copy(target.contentLocale === "es-MX" ? "Written in Spanish by your care team" : "Written in English by your care team")}
                          </p>
                        ) : null}
                        <p className="mt-0.5 break-words text-[13px] leading-5 text-muted">
                          {target.frequency}
                          {target.providerName
                            ? ` · ${target.providerName}`
                            : ""}
                        </p>
                      </div>
                      <span
                        className={`max-w-[40%] shrink-0 rounded-full px-2.5 py-1 text-center text-xs font-semibold ${
                          target.reminderSchedule &&
                          !disableAutomatic &&
                          target.reminderSchedule.isEnabled
                            ? "bg-brand-tint text-brand-ink"
                            : "bg-note-tint text-note-ink"
                        }`}
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
                      </span>
                    </div>

                    {target.description &&
                    target.description.trim() !== target.name.trim() ? (
                      <p className="break-words text-[15px] leading-6 text-ink-2">
                        {target.description}
                      </p>
                    ) : null}
                    {target.reminderSchedule ? (
                      <div className="flex items-start gap-3 rounded-2xl bg-surface-2/70 px-3.5 py-3">
                        <Icon name="bell" className="mt-0.5 h-[18px] w-[18px] shrink-0 text-brand" />
                        <div className="min-w-0 flex-1 space-y-1.5">
                          <p className="break-words text-sm text-ink-2">
                            {target.reminderSchedule.daysOfWeek
                              .map((day) => { const label = reminderDayLabel(locale, day); return label.charAt(0).toLocaleUpperCase(locale) + label.slice(1); })
                              .join(", ")}
                          </p>
                          <p className="flex flex-wrap gap-1.5">
                            {target.reminderSchedule.timesOfDay.map((value, index) => (
                              <span key={`${value}-${index}`} className="rounded-lg bg-surface px-2 py-0.5 font-mono text-[13px] font-medium text-ink">{value.slice(0, 5)}</span>
                            ))}
                          </p>
                          <p className="break-words text-xs text-muted">
                            {target.reminderSchedule.timezone.replaceAll("_", " ")}
                          </p>
                        </div>
                      </div>
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
                      <div className="border-t border-line text-sm leading-6 text-muted">
                        <details className="group">
                          <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 py-2 font-semibold text-ink-2 [&::-webkit-details-marker]:hidden">
                            <Icon name="info" className="h-4 w-4 text-muted" />
                            <span className="flex-1">{copy("Schedule help")}</span>
                            <Icon name="chevronDown" className="h-4 w-4 text-muted transition-transform duration-[240ms] group-open:rotate-180" />
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
                      <p className="rounded-xl bg-note-tint p-3 text-sm leading-6 text-note-ink">
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
                        <p className="text-sm leading-6 text-ink-2">
                          {copy(
                            "Choose times that match the instruction above, including meal or activity timing. These are reminders, not changes to your care plan.",
                          )}
                        </p>
                        <p className="break-words text-sm text-muted">
                          {copy("Reminder timezone:")}{" "}
                          {draft.timezone.replaceAll("_", " ")}
                        </p>
                        <div>
                          <p className="mb-3 text-[15px] font-semibold text-ink">
                            {copy("Days")}
                          </p>
                          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                            {DAYS.map((day) => {
                              const checked = draft.daysOfWeek.includes(day);
                              return (
                                <label
                                  className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-xl border px-3 py-2 text-[15px] font-medium transition-colors duration-[160ms] has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-70 ${checked ? "border-brand bg-brand-tint text-brand-ink" : "border-line-strong bg-surface text-ink-2 hover:border-brand/40"}`}
                                  key={day}
                                >
                                  <input
                                    checked={checked}
                                    disabled={Boolean(
                                      target.guidance.requiredDaysOfWeek
                                        ?.length,
                                    )}
                                    className="h-5 w-5 accent-brand"
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
                            <p className="text-[15px] font-semibold text-ink">
                              {copy("Reminder times")}
                            </p>
                            <button
                              className="min-h-11 rounded-full px-3 text-sm font-semibold text-brand-ink hover:bg-brand-tint"
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
                                className="min-h-12 min-w-0 w-full rounded-2xl border border-line-strong bg-surface px-4 py-2 font-mono text-base text-ink outline-none focus:border-brand focus:ring-4 focus:ring-brand/15"
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
                                className="min-h-11 rounded-full px-3 text-sm font-semibold text-danger-ink hover:bg-danger-tint"
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

                    <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 empty:hidden">
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
                          variant="ghost"
                          className="!text-danger-ink hover:!bg-danger-tint"
                        >
                          {copy("Clear schedule")}
                        </Button>
                      ) : null}
                    </div>
                  </article>
                );
              })}
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
