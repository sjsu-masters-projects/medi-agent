"use client";

import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import { Button, ErrorState, Skeleton } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { useClinicMemberships } from "@/hooks/use-clinic-filter";
import {
  fetchPatientAppointments,
  fetchSchedulingPatients,
  fetchSchedulingProfile,
  type AssignedSchedulingPatient,
} from "@/services/appointments";
import type { RootState } from "@/store/store";
import type { Appointment } from "@/types";
import { resolveSchedulingTimezone } from "@/utils/appointment-times";
import { AppointmentOfferHistory } from "./appointment-offer-history";
import { NewOfferPanel } from "./new-offer-panel";

/** This patient's visits and offers (scoped by the access rule), with a "New offer" action. */
export function PatientAppointmentsPanel({ patientId }: { patientId: string }) {
  const token = useSelector((state: RootState) => state.auth.accessToken);
  const { clinics } = useClinicMemberships();
  const [rows, setRows] = useState<Appointment[] | null>(null);
  const [roster, setRoster] = useState<AssignedSchedulingPatient[]>([]);
  const [timezone, setTimezone] = useState("UTC");
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [offer, setOffer] = useState<{ previous?: Appointment } | null>(null);
  const [sent, setSent] = useState(false);

  useEffect(() => {
    if (!token) return;
    let live = true;
    void Promise.all([
      fetchPatientAppointments(token, patientId),
      fetchSchedulingPatients(token).catch(() => []),
      fetchSchedulingProfile(token, patientId).catch(() => ({ timezone: null })),
    ])
      .then(([visits, people, profile]) => {
        if (!live) return;
        setRows(visits);
        setRoster(people.filter((person) => person.id === patientId));
        setTimezone(resolveSchedulingTimezone(profile.timezone).timezone);
      })
      .catch(() => {
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
  }, [token, patientId, attempt]);

  if (!token) return null;
  const multi = clinics.length >= 2;
  return (
    <section
      aria-labelledby="tab-btn-appointments"
      className="space-y-4"
      id="tab-panel-appointments"
      role="tabpanel"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-[15px] font-semibold text-ink">Appointments</h2>
          <p className="mt-0.5 text-[13px] text-muted">
            Visits and offers for this patient, with their responses.
          </p>
        </div>
        <Button
          disabled={!roster.length}
          onClick={() => {
            setSent(false);
            setOffer({});
          }}
        >
          <Icon name="plus" className="h-4 w-4" />
          New offer
        </Button>
      </div>
      {sent && (
        <p
          role="status"
          className="flex items-start gap-2.5 rounded-xl border border-ok-line bg-ok-soft px-4 py-3 text-sm text-ok-ink"
        >
          <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0" />
          <span>Appointment offer sent. The patient can choose a time in Visits.</span>
        </p>
      )}
      {failed ? (
        <ErrorState
          title="Could not load appointments"
          description="Retry to see this patient's visits and offers."
          onRetry={() => {
            setFailed(false);
            setAttempt((value) => value + 1);
          }}
        />
      ) : !rows ? (
        <div aria-label="Loading appointments" className="space-y-3">
          <p role="status" className="text-sm text-muted">Loading appointments…</p>
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-line">
          <AppointmentOfferHistory
            appointments={rows}
            disabled={false}
            onRepropose={(visit) => {
              setSent(false);
              setOffer({ previous: visit });
            }}
            showClinic={multi}
            timezone={timezone}
            token={token}
          />
        </div>
      )}
      {offer && (
        <NewOfferPanel
          onClose={() => setOffer(null)}
          onCreated={() => {
            setOffer(null);
            setSent(true);
            setRows(null);
            setAttempt((value) => value + 1);
          }}
          patientId={patientId}
          previous={offer.previous}
          roster={roster}
          showClinic={multi}
          token={token}
        />
      )}
    </section>
  );
}
