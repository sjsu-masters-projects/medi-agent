"use client";

import { useEffect, useState } from "react";
import type { PatientDeepDive } from "@/services/clinicians";
import { Icon } from "@/components/ui/icons";
import { AdherenceChart } from "./adherence-chart";

const BARRIER_LABELS: Record<string, string> = {
  side_effects: "Side effects",
  cost: "Cost",
  access: "Access",
  schedule: "Schedule",
  confusion: "Instructions unclear",
  other: "Other",
};

function formatDay(day: string) {
  return new Date(`${day}T12:00:00Z`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

function barrierTarget(
  patient: PatientDeepDive,
  barrier: NonNullable<PatientDeepDive["adherence_barriers"]>[number],
) {
  const name =
    barrier.target_type === "medication"
      ? patient.medications.find((med) => med.id === barrier.target_id)?.name
      : patient.obligations?.find((item) => item.id === barrier.target_id)
          ?.description;
  return name ?? "Earlier record — not in the current activity list";
}

function Summary({ patient }: { patient: PatientDeepDive }) {
  const recorded = patient.adherence_series.reduce(
    (sum, day) => sum + day.expected,
    0,
  );
  const completed = patient.adherence_series.reduce(
    (sum, day) => sum + day.completed,
    0,
  );
  const days = patient.adherence_series.filter(
    (day) => day.expected > 0,
  ).length;
  const metrics = [
    [
      "Recorded completion",
      recorded ? `${Math.round((completed / recorded) * 100)}%` : "No data",
      `${completed} completed / ${recorded} responses`,
    ],
    [
      "Days with responses",
      `${days} / ${patient.adherence_series.length}`,
      "Days without responses are unknown",
    ],
    [
      "Current medications",
      String(patient.medications.filter((med) => med.isActive).length),
      "Active records, not expected doses",
    ],
    [
      "Current activities",
      String(patient.obligations?.filter((item) => item.is_active).length ?? 0),
      "Active care-team instructions",
    ],
  ];
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {metrics.map(([label, value, detail]) => (
        <div
          key={label}
          className="rounded-2xl border border-line bg-surface px-5 py-4 shadow-[var(--shadow-card)]"
        >
          <p className="text-[13px] text-muted">{label}</p>
          <p className="mt-1.5 font-mono text-[28px] font-medium leading-none tracking-[-0.01em] text-ink">{value}</p>
          <p className="mt-2 text-xs text-muted">{detail}</p>
        </div>
      ))}
    </div>
  );
}

const CARD = "rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]";
const CARD_HEADER = "flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4";
const CARD_TITLE = "text-[15px] font-semibold text-ink";

function Barriers({ patient, activityId }: { patient: PatientDeepDive; activityId?: string | null }) {
  const barriers = patient.adherence_barriers ?? [];
  return (
    <section className={CARD}>
      <div className="border-b border-line px-5 py-4">
        <h3 className={CARD_TITLE}>
          Patient-reported barriers{" "}
          <span className="font-mono text-[13px] font-normal text-muted">
            ({barriers.length})
          </span>
        </h3>
        <p className="mt-0.5 text-[13px] text-muted">
          Latest 20 reports, including earlier plan versions. Patient statements,
          not reviewed ADR findings.
        </p>
      </div>
      {barriers.length === 0 ? (
        <p className="px-5 py-5 text-sm text-muted">
          No patient-reported barriers returned. This does not establish that
          all tasks were completed.
        </p>
      ) : (
        <ul>
          {barriers.map((barrier, index) => (
            <li
              key={`${barrier.target_id}-${barrier.logged_at}-${index}`}
              id={`barrier-${barrier.target_id}-${index}`}
              tabIndex={barrier.target_id === activityId ? -1 : undefined}
              className={`scroll-mt-6 border-b border-line px-5 py-4 last:border-b-0 hover:bg-[rgba(100,116,139,.05)] ${barrier.target_id === activityId ? "ring-2 ring-inset ring-primary" : ""}`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-[7px] bg-warn-tint px-2 py-1 text-xs font-medium text-warn-ink">
                  <span aria-hidden="true" className="h-[7px] w-[7px] rounded-full bg-warn" />
                  {BARRIER_LABELS[barrier.barrier_code] ?? "Reported barrier"}
                </span>
                <time
                  className="font-mono text-xs text-muted"
                  dateTime={barrier.logged_at}
                >
                  {new Date(barrier.logged_at).toLocaleString("en-US", {
                    timeZone: patient.timezone ?? "America/Los_Angeles",
                  })}
                </time>
              </div>
              <p className="mt-2 text-sm font-semibold text-ink">
                {barrierTarget(patient, barrier)}
              </p>
              <p className="mt-0.5 text-xs text-muted">
                {barrier.target_type === "medication"
                  ? "Medication"
                  : "Care activity"}{" "}
                · Report time in {patient.timezone ?? "America/Los_Angeles"}
              </p>
              {barrier.notes ? (
                <p className="mt-2 max-w-[80ch] whitespace-pre-wrap break-words rounded-[10px] bg-surface-2 px-3 py-2 text-sm text-ink-2">
                  {barrier.notes}
                </p>
              ) : (
                <p className="mt-2 text-xs text-muted">
                  No additional note provided.
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function DailyResponses({ patient }: { patient: PatientDeepDive }) {
  const [showUnknown, setShowUnknown] = useState(false);
  const rows = [...patient.adherence_series]
    .reverse()
    .filter((day) => showUnknown || day.expected > 0);
  return (
    <section className={CARD}>
      <div className={CARD_HEADER}>
        <h3 className={CARD_TITLE}>
          Daily response detail
        </h3>
        <label className="flex min-h-8 cursor-pointer items-center gap-2 text-[13px] text-ink-2">
          <input
            type="checkbox"
            className="h-4 w-4 accent-[var(--color-primary)]"
            checked={showUnknown}
            onChange={(event) => setShowUnknown(event.target.checked)}
          />
          Show days without responses
        </label>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <caption className="px-5 pb-3 pt-3 text-left text-xs text-muted">
            Dates use UTC, matching the existing reporting API. Non-completed
            responses may include barriers; they are not automatically missed
            doses.
          </caption>
          <thead className="border-y border-line">
            <tr>
              {[
                "Date (UTC)",
                "Completed",
                "Other responses",
                "Total recorded",
                "Completion",
              ].map((label) => (
                <th className="px-5 py-3 font-mono text-[11px] font-normal uppercase tracking-[0.06em] text-muted" scope="col" key={label}>
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((day) => (
              <tr className="border-b border-line last:border-b-0 hover:bg-[rgba(100,116,139,.05)]" key={day.date}>
                <th
                  className="whitespace-nowrap px-5 py-3 font-medium text-ink"
                  scope="row"
                >
                  {formatDay(day.date)}
                </th>
                <td className="px-5 py-3 font-mono text-[13px] text-ink-2">{day.completed}</td>
                <td className="px-5 py-3 font-mono text-[13px] text-ink-2">{day.expected - day.completed}</td>
                <td className="px-5 py-3 font-mono text-[13px] text-ink-2">{day.expected}</td>
                <td className={`px-5 py-3 text-[13px] ${day.expected ? `font-mono ${day.score < 0.6 ? "text-risk-ink" : "text-ink"}` : "text-muted"}`}>
                  {day.expected
                    ? `${Math.round(day.score * 100)}%`
                    : "No response"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length === 0 && (
        <p className="px-5 pb-5 pt-2 text-sm text-muted">
          No recorded responses in this reporting window.
        </p>
      )}
    </section>
  );
}

function CurrentActivities({ patient, activityId }: { patient: PatientDeepDive; activityId?: string | null }) {
  const rows = [
    ...patient.medications
      .filter((med) => med.isActive)
      .map((med) => ({
        id: med.id,
        name: med.name,
        kind: "Medication",
        detail: `${med.dosage} · ${med.frequency}`,
      })),
    ...(patient.obligations ?? [])
      .filter((item) => item.is_active)
      .map((item) => ({
        id: item.id,
        name: item.description,
        kind: "Care activity",
        detail: item.frequency,
      })),
  ];
  return (
    <details open={activityId && rows.some((row) => row.id === activityId) ? true : undefined} className={`ma-disclosure ${CARD} px-5 py-2`}>
      <summary className="min-h-9 py-1.5 text-[13px] font-medium text-ink">
        Current medication & activity context ({rows.length})
      </summary>
      <p className="mt-1 text-xs text-muted">
        Current records only; these are not a historical task list or evidence
        of missed doses.
      </p>
      <ul className="mt-2 pb-2">
        {rows.map((row) => (
          <li id={`activity-${row.id}`} tabIndex={row.id === activityId ? -1 : undefined} className={`flex scroll-mt-6 flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-line py-3 last:border-b-0 ${row.id === activityId ? "ring-2 ring-primary" : ""}`} key={`${row.kind}-${row.id}`}>
            <p className="text-sm font-medium text-ink">{row.name}</p>
            <p className="text-xs text-muted">
              {row.kind} · {row.detail}
            </p>
          </li>
        ))}
      </ul>
      {rows.length === 0 && (
        <p className="pb-3 text-sm text-muted">
          No active records returned.
        </p>
      )}
    </details>
  );
}

export function PatientAdherencePanel({
  patient,
  activityId,
}: {
  patient: PatientDeepDive;
  activityId?: string | null;
}) {
  const barrierIndex = patient.adherence_barriers?.findIndex((barrier) => barrier.target_id === activityId) ?? -1;
  const currentActivity = patient.medications.some((med) => med.id === activityId && med.isActive) || patient.obligations?.some((item) => item.id === activityId && item.is_active);
  useEffect(() => {
    if (!activityId) return;
    const target = document.getElementById(barrierIndex >= 0 ? `barrier-${activityId}-${barrierIndex}` : `activity-${activityId}`);
    target?.scrollIntoView?.({ block: "center" });
    target?.focus({ preventScroll: true });
  }, [activityId, barrierIndex, patient]);
  return (
    <div className="space-y-5">
      {activityId && barrierIndex < 0 && !currentActivity && <p role="status" className="text-sm text-muted">The linked activity is not in the returned reports or current records. Earlier barriers may fall outside the latest 20 reports.</p>}
      <div>
        <h2 className="text-lg font-semibold tracking-[-0.01em] text-ink">
          Adherence & patient follow-up
        </h2>
        <p className="mt-1 text-sm text-muted">
          Review recorded responses, practical barriers, and current care
          context.
        </p>
      </div>
      <Summary patient={patient} />
      <section className="flex items-start gap-2.5 rounded-xl border border-primary-line bg-primary-tint px-4 py-3 text-sm">
        <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
        <div>
          <h3 className="text-[13px] font-semibold text-ink">
            How to read these numbers
          </h3>
          <p className="mt-0.5 max-w-[80ch] text-sm text-ink-2">
            Completion is calculated from recorded responses, not all scheduled
            doses or activities. Unrecorded days are unknown, not 0% adherence.
            This view does not determine medication safety or an ADR.
          </p>
        </div>
      </section>
      <section className={CARD}>
        <div className="border-b border-line px-5 py-4">
          <h3 className={CARD_TITLE}>
            30-day recorded completion trend
          </h3>
          <p className="mt-0.5 font-mono text-[11px] uppercase tracking-[0.06em] text-muted">
            UTC daily buckets · gaps mean no responses · dots show days with
            records
          </p>
        </div>
        <div className="px-3 pb-4 pt-4 sm:px-5">
          <AdherenceChart data={patient.adherence_series} />
        </div>
      </section>
      <Barriers patient={patient} activityId={activityId} />
      <DailyResponses patient={patient} />
      <CurrentActivities patient={patient} activityId={activityId} />
    </div>
  );
}
