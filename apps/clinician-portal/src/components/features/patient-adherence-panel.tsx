"use client";

import { useState } from "react";
import type { PatientDeepDive } from "@/services/clinicians";
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
          className="rounded-xl border border-gray-200 bg-gray-50 p-4"
        >
          <p className="text-xs font-medium text-gray-500">{label}</p>
          <p className="mt-2 text-2xl font-bold text-gray-900">{value}</p>
          <p className="mt-1 text-xs text-gray-500">{detail}</p>
        </div>
      ))}
    </div>
  );
}

function Barriers({ patient }: { patient: PatientDeepDive }) {
  const barriers = patient.adherence_barriers ?? [];
  return (
    <section className="rounded-xl border border-gray-200 p-4">
      <h3 className="text-base font-semibold text-gray-900">
        Patient-reported barriers{" "}
        <span className="text-sm font-normal text-gray-500">
          ({barriers.length})
        </span>
      </h3>
      <p className="mt-1 text-xs text-gray-500">
        Latest 20 reports, including earlier plan versions. Patient statements,
        not reviewed ADR findings.
      </p>
      {barriers.length === 0 ? (
        <p className="mt-4 text-sm text-gray-500">
          No patient-reported barriers returned. This does not establish that
          all tasks were completed.
        </p>
      ) : (
        <ul className="mt-4 space-y-3">
          {barriers.map((barrier, index) => (
            <li
              key={`${barrier.target_id}-${barrier.logged_at}-${index}`}
              className="rounded-lg border border-gray-200 bg-gray-50 p-3"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="rounded-full bg-yellow-100 px-2.5 py-0.5 text-xs font-medium text-yellow-800">
                  {BARRIER_LABELS[barrier.barrier_code] ?? "Reported barrier"}
                </span>
                <time
                  className="text-xs text-gray-500"
                  dateTime={barrier.logged_at}
                >
                  {new Date(barrier.logged_at).toLocaleString("en-US", {
                    timeZone: patient.timezone ?? "America/Los_Angeles",
                  })}
                </time>
              </div>
              <p className="mt-2 text-sm font-semibold text-gray-900">
                {barrierTarget(patient, barrier)}
              </p>
              <p className="mt-1 text-xs text-gray-500">
                {barrier.target_type === "medication"
                  ? "Medication"
                  : "Care activity"}{" "}
                · Report time in {patient.timezone ?? "America/Los_Angeles"}
              </p>
              {barrier.notes ? (
                <p className="mt-2 whitespace-pre-wrap break-words text-sm text-gray-700">
                  {barrier.notes}
                </p>
              ) : (
                <p className="mt-2 text-xs text-gray-500">
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
    <section className="rounded-xl border border-gray-200 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-base font-semibold text-gray-900">
          Daily response detail
        </h3>
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input
            type="checkbox"
            checked={showUnknown}
            onChange={(event) => setShowUnknown(event.target.checked)}
          />
          Show days without responses
        </label>
      </div>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <caption className="mb-3 text-left text-xs text-gray-500">
            Dates use UTC, matching the existing reporting API. Non-completed
            responses may include barriers; they are not automatically missed
            doses.
          </caption>
          <thead className="border-y border-gray-200 bg-gray-50 text-xs text-gray-500">
            <tr>
              {[
                "Date (UTC)",
                "Completed",
                "Other responses",
                "Total recorded",
                "Completion",
              ].map((label) => (
                <th className="px-3 py-2 font-semibold" scope="col" key={label}>
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((day) => (
              <tr className="border-b border-gray-100" key={day.date}>
                <th
                  className="whitespace-nowrap px-3 py-3 font-medium"
                  scope="row"
                >
                  {formatDay(day.date)}
                </th>
                <td className="px-3 py-3">{day.completed}</td>
                <td className="px-3 py-3">{day.expected - day.completed}</td>
                <td className="px-3 py-3">{day.expected}</td>
                <td className="px-3 py-3">
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
        <p className="mt-4 text-sm text-gray-500">
          No recorded responses in this reporting window.
        </p>
      )}
    </section>
  );
}

function CurrentActivities({ patient }: { patient: PatientDeepDive }) {
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
    <details className="rounded-xl border border-gray-200 p-4">
      <summary className="cursor-pointer text-sm font-semibold text-gray-900">
        Current medication & activity context ({rows.length})
      </summary>
      <p className="mt-2 text-xs text-gray-500">
        Current records only; these are not a historical task list or evidence
        of missed doses.
      </p>
      <ul className="mt-3 divide-y divide-gray-100">
        {rows.map((row) => (
          <li className="py-3" key={`${row.kind}-${row.id}`}>
            <p className="text-sm font-medium text-gray-900">{row.name}</p>
            <p className="mt-1 text-xs text-gray-500">
              {row.kind} · {row.detail}
            </p>
          </li>
        ))}
      </ul>
      {rows.length === 0 && (
        <p className="mt-3 text-sm text-gray-500">
          No active records returned.
        </p>
      )}
    </details>
  );
}

export function PatientAdherencePanel({
  patient,
}: {
  patient: PatientDeepDive;
}) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">
          Adherence & patient follow-up
        </h2>
        <p className="mt-1 text-sm text-gray-500">
          Review recorded responses, practical barriers, and current care
          context.
        </p>
      </div>
      <Summary patient={patient} />
      <section className="rounded-xl border border-blue-100 bg-blue-50 p-4">
        <h3 className="text-sm font-semibold text-gray-900">
          How to read these numbers
        </h3>
        <p className="mt-1 text-sm text-gray-700">
          Completion is calculated from recorded responses, not all scheduled
          doses or activities. Unrecorded days are unknown, not 0% adherence.
          This view does not determine medication safety or an ADR.
        </p>
      </section>
      <section>
        <h3 className="mb-1 text-base font-semibold text-gray-900">
          30-day recorded completion trend
        </h3>
        <p className="mb-4 text-xs text-gray-500">
          UTC daily buckets · gaps mean no responses · dots show days with
          records
        </p>
        <AdherenceChart data={patient.adherence_series} />
      </section>
      <Barriers patient={patient} />
      <DailyResponses patient={patient} />
      <CurrentActivities patient={patient} />
    </div>
  );
}
