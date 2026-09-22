"use client";

import { useCallback, useEffect, useState } from "react";
import { useSelector } from "react-redux";
import {
  fetchVisits,
  respondToVisit,
  type AppointmentResponseAction,
} from "@/services/appointments";
import type { RootState } from "@/store/store";
import type { Appointment } from "@/types";

export function useVisitsData() {
  const accessToken = useSelector((state: RootState) => state.auth.accessToken);
  const [visits, setVisits] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [respondingId, setRespondingId] = useState<string | null>(null);

  const loadVisits = useCallback(async () => {
    if (!accessToken) {
      setVisits([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      setVisits(await fetchVisits(accessToken));
    } catch (err) {
      setError((err as Error).message || "Could not load your visits.");
    } finally {
      setLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    void loadVisits();
  }, [loadVisits]);

  const respond = useCallback(
    async (appointmentId: string, action: AppointmentResponseAction) => {
      if (!accessToken) {
        return;
      }
      setRespondingId(appointmentId);
      setError(null);
      try {
        const updated = await respondToVisit(
          appointmentId,
          action,
          accessToken,
        );
        setVisits((current) =>
          current.map((visit) => (visit.id === updated.id ? updated : visit)),
        );
      } catch (err) {
        setError((err as Error).message || "Could not update the visit.");
      } finally {
        setRespondingId(null);
      }
    },
    [accessToken],
  );

  return { visits, loading, error, respond, respondingId, refresh: loadVisits };
}
