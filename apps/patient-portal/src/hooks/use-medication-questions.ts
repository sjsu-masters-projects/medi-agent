"use client";

import { useCallback, useEffect, useState } from "react";
import { useSelector } from "react-redux";

import { createSharedPoll } from "@/lib/shared-poll";
import { fetchMedicationQuestions, type MedicationQuestion } from "@/services/medication-confirmations";
import type { RootState } from "@/store/store";

/** The notification centre's background cadence: at most one request a minute. */
export const MEDICATION_QUESTIONS_POLL_MS = 60_000;

const poll = createSharedPoll<MedicationQuestion[]>(
  (token) => fetchMedicationQuestions(token),
  { intervalMs: MEDICATION_QUESTIONS_POLL_MS, fallback: [] },
);

interface State {
  token: string | null;
  items: MedicationQuestion[];
  loaded: boolean;
}

const empty: State = { token: null, items: [], loaded: false };

export interface MedicationQuestions {
  items: MedicationQuestion[];
  loaded: boolean;
  refresh: () => void;
}

/**
 * The patient's open medication questions from the care team. One poller per tab; a failed
 * load reports no questions rather than an error, because Today must not break over it.
 */
export function useMedicationQuestions(): MedicationQuestions {
  const accessToken = useSelector((state: RootState) => state.auth.accessToken);
  const [state, setState] = useState<State>(empty);
  useEffect(() => {
    if (!accessToken) return;
    return poll.subscribe(accessToken, (snapshot) =>
      setState({ token: snapshot.token, items: snapshot.value, loaded: snapshot.loaded }),
    );
  }, [accessToken]);
  const refresh = useCallback(() => poll.refresh(), []);
  if (!accessToken || state.token !== accessToken) return { items: [], loaded: false, refresh };
  return { items: state.items, loaded: state.loaded, refresh };
}
