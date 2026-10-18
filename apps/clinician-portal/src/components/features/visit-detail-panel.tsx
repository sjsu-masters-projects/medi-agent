"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge, ErrorState, Modal, Skeleton } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import {
  fetchPatientAppointments,
  fetchSchedulingProfile,
} from "@/services/appointments";
import type { Appointment } from "@/types";
import { formatSchedulingTime, resolveSchedulingTimezone } from "@/utils/appointment-times";
import {
  AppointmentOfferHistory,
  STATUS_LABELS,
  STATUS_TONES,
} from "./appointment-offer-history";
import { ClinicChip } from "./clinic-chip";
import { CANCEL_REASONS, VisitActions } from "./visit-actions";

interface Props {
  token: string;
  appointmentId: string;
  patientId: string;
  patientName?: string;
  showClinic: boolean;
  onClose: () => void;
  onRepropose: (visit: Appointment) => void;
  /** A change was saved (cancel, complete, no-show or edit): refresh what shows it. */
  onChanged?: () => void;
}

/** One visit or offer: who, where, when, its status, the offer and response history, actions. */
export function VisitDetailPanel({
  token,
  appointmentId,
  patientId,
  patientName,
  showClinic,
  onClose,
  onRepropose,
  onChanged,
}: Props) {
  const [now] = useState(() => Date.now());
  const [rows, setRows] = useState<Appointment[] | null>(null);
  const [timezone, setTimezone] = useState<string>("UTC");
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    void Promise.all([
      fetchPatientAppointments(token, patientId),
      fetchSchedulingProfile(token, patientId).catch(() => ({ timezone: null })),
    ])
      .then(([visits, profile]) => {
        if (!live) return;
        setTimezone(resolveSchedulingTimezone(profile.timezone).timezone);
        setRows(visits);
      })
      .catch(() => {
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
  }, [token, patientId, attempt]);

  const current = rows?.find((row) => row.id === appointmentId);
  function changed(row: Appointment) {
    setRows((existing) => existing?.map((item) => (item.id === row.id ? { ...item, ...row } : item)) ?? existing);
    onChanged?.();
  }
  return (
    <Modal contentClassName="!p-0" onClose={onClose} open placement="side" title="Visit">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="space-y-2 border-b border-line px-5 py-4">
          <p className="flex flex-wrap items-center gap-2">
            <Link
              className="text-base font-semibold text-ink underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              href={`/patients/${patientId}`}
            >
              {patientName ?? "Patient record"}
            </Link>
            {showClinic && <ClinicChip name={current?.clinicName} />}
          </p>
          {current && (
            <p className="flex flex-wrap items-center gap-2 text-[13px] text-ink-2">
              <span className="font-mono font-semibold text-ink">
                {formatSchedulingTime(current.scheduledAt, timezone)}
              </span>
              <span className="text-muted">· {timezone}</span>
              <Badge variant={STATUS_TONES[current.status]}>{STATUS_LABELS[current.status]}</Badge>
            </p>
          )}
        </div>
        {current && (
          <VisitActions
            now={now}
            onChanged={changed}
            onRepropose={onRepropose}
            token={token}
            visit={current}
          />
        )}
        {current?.status === "cancelled" && (
          <p className="mx-5 mt-3 rounded-xl bg-sunken px-3.5 py-2.5 text-[13px] text-ink-2" role="note">
            {current.cancelledBy === "clinician" ? "Cancelled by your team." : "Cancelled by the patient."}
            {current.cancelReasonCode
              ? ` ${CANCEL_REASONS.find((reason) => reason.value === current.cancelReasonCode)?.label ?? ""}${current.cancelReason ? ` — ${current.cancelReason}` : ""}`
              : ""}
          </p>
        )}
        {failed ? (
          <div className="px-5 py-5">
            <ErrorState
              title="Could not load this visit"
              description="Retry to see its history."
              onRetry={() => {
                setFailed(false);
                setAttempt((value) => value + 1);
              }}
            />
          </div>
        ) : !rows ? (
          <div className="space-y-3 px-5 py-5">
            <p role="status" className="text-sm text-muted">Loading visit…</p>
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : !current ? (
          <p role="status" className="flex items-start gap-2 px-5 py-5 text-sm text-muted">
            <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0" />
            This appointment is unavailable. It may belong to a clinic where you have no link to this patient.
          </p>
        ) : null}
        {rows && (
          <AppointmentOfferHistory
            appointmentId={appointmentId}
            appointments={rows}
            disabled={false}
            onRepropose={onRepropose}
            showClinic={showClinic}
            timezone={timezone}
            token={token}
          />
        )}
      </div>
    </Modal>
  );
}
