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

interface Props {
  token: string;
  appointmentId: string;
  patientId: string;
  patientName?: string;
  showClinic: boolean;
  onClose: () => void;
  onRepropose: (visit: Appointment) => void;
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
}: Props) {
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
