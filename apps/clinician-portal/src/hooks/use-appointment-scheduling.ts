"use client";

import { useEffect, useState } from "react";
import {
  fetchSchedulingAppointments,
  fetchSchedulingPatients,
  type AssignedSchedulingPatient,
} from "@/services/appointments";
import type { Appointment } from "@/types";

export function useAppointmentScheduling(token: string) {
  const [patients, setPatients] = useState<AssignedSchedulingPatient[]>([]);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    void Promise.all([
      fetchSchedulingPatients(token),
      fetchSchedulingAppointments(token),
    ])
      .then(([roster, visits]) => {
        if (active) {
          setPatients(roster);
          setAppointments(visits);
        }
      })
      .catch(() => {
        if (active) setError(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token, attempt]);

  function addOffer(rows: Appointment[]) {
    setAppointments((current) => {
      const ids = new Set(rows.map((row) => row.id));
      return [...current.filter((row) => !ids.has(row.id)), ...rows];
    });
  }
  function refresh() {
    setLoading(true);
    setError(false);
    setAttempt((value) => value + 1);
  }
  return { patients, appointments, loading, error, addOffer, refresh };
}
