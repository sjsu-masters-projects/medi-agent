"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSelector } from "react-redux";
import {
  applyAppointmentResponse,
  fetchVisits,
  respondToVisit,
  type AppointmentResponseAction,
} from "@/services/appointments";
import type { RootState } from "@/store/store";
import type { Appointment } from "@/types";
import { getAppointmentErrorCode } from "../../../../packages/shared/src/utils/appointment-errors";

interface VisitsState {
  token: string | null;
  visits: Appointment[];
  loading: boolean;
  error: string | null;
  actionError: string | null;
  respondingId: string | null;
}
const emptyState: VisitsState = {
  token: null,
  visits: [],
  loading: true,
  error: null,
  actionError: null,
  respondingId: null,
};

export function useVisitsData() {
  const accessToken = useSelector((state: RootState) => state.auth.accessToken);
  const [state, setState] = useState<VisitsState>(emptyState);
  const sessionVersion = useRef(0);
  const loadVersion = useRef(0);
  const pendingResponse = useRef<number | null>(null);

  const loadVisits = useCallback(async () => {
    const session = sessionVersion.current;
    if (pendingResponse.current === session) return;
    const request = ++loadVersion.current;
    setState((current) => ({
      ...(current.token === accessToken ? current : emptyState),
      token: accessToken,
      loading: Boolean(accessToken),
      error: null,
    }));
    if (!accessToken) return;
    try {
      const visits = await fetchVisits(accessToken);
      if (session === sessionVersion.current && request === loadVersion.current)
        setState((current) => ({ ...current, visits }));
    } catch {
      if (session === sessionVersion.current && request === loadVersion.current)
        setState((current) => ({ ...current, error: "LOAD_FAILED" }));
    } finally {
      if (session === sessionVersion.current && request === loadVersion.current)
        setState((current) => ({ ...current, loading: false }));
    }
  }, [accessToken]);

  useEffect(() => {
    const session = ++sessionVersion.current;
    void loadVisits();
    return () => {
      sessionVersion.current = session + 1;
    };
  }, [loadVisits]);

  const current = state.token === accessToken ? state : emptyState;
  // Ask the server to persist expiration at the first pending deadline and on return.
  useEffect(() => {
    if (!accessToken || current.respondingId) return;
    const deadlines = current.visits
      .filter((visit) => visit.status === "proposed" && visit.proposalExpiresAt)
      .map((visit) => Date.parse(visit.proposalExpiresAt!))
      .filter(Number.isFinite);
    const delay = Math.min(...deadlines) - Date.now();
    // A failed refresh must not start a tight retry loop for an elapsed deadline.
    const timer =
      Number.isFinite(delay) && !current.error
        ? setTimeout(
            () => {
              void loadVisits();
            },
            delay <= 0 ? 60000 : Math.min(delay, 2147483647),
          )
        : undefined;
    const onFocus = () => {
      void loadVisits();
    };
    window.addEventListener("focus", onFocus);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("focus", onFocus);
    };
  }, [
    accessToken,
    current.visits,
    current.error,
    current.respondingId,
    loadVisits,
  ]);

  const respond = useCallback(
    async (
      appointmentId: string,
      action: AppointmentResponseAction,
      note?: string,
    ) => {
      if (!accessToken) {
        return;
      }
      const session = sessionVersion.current;
      if (pendingResponse.current === session) return;
      pendingResponse.current = session;
      loadVersion.current++;
      setState((current) => ({
        ...current,
        respondingId: appointmentId,
        actionError: null,
      }));
      try {
        const updated = await respondToVisit(
          appointmentId,
          action,
          accessToken,
          note,
        );
        if (session !== sessionVersion.current) return;
        setState((current) => ({
          ...current,
          visits: applyAppointmentResponse(current.visits, updated, action),
        }));
        // The server may have expired an unchosen sibling in the same transaction.
        try {
          const visits = await fetchVisits(accessToken);
          if (session === sessionVersion.current)
            setState((current) => ({ ...current, visits }));
        } catch {
          if (session === sessionVersion.current)
            setState((current) => ({
              ...current,
              actionError: "RESPONSE_SAVED_REFRESH_FAILED",
            }));
        }
      } catch (err) {
        if (session !== sessionVersion.current) return;
        const actionError = getAppointmentErrorCode(err) ?? "UNKNOWN";
        setState((current) => ({ ...current, actionError }));
        if (
          actionError === "APPOINTMENT_EXPIRED" ||
          actionError === "APPOINTMENT_UNAVAILABLE"
        ) {
          try {
            const visits = await fetchVisits(accessToken);
            if (session === sessionVersion.current)
              setState((current) => ({ ...current, visits }));
          } catch {
            /* Keep the list and localized notice available for manual refresh. */
          }
        }
      } finally {
        if (session === sessionVersion.current) {
          pendingResponse.current = null;
          setState((current) => ({
            ...current,
            respondingId: null,
            loading: false,
          }));
        }
      }
    },
    [accessToken],
  );

  return {
    accessToken,
    visits: current.visits,
    loading: current.loading,
    error: current.error,
    actionError: current.actionError,
    respond,
    respondingId: current.respondingId,
    refresh: loadVisits,
  };
}
