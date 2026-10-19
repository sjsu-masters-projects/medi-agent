"use client";

import { useEffect, useState } from "react";
import { useSelector } from "react-redux";

import { createSharedPoll } from "@/lib/shared-poll";
import { fetchADRInformationRequests } from "@/services/adr-follow-up";
import type { RootState } from "@/store/store";

/** The same background cadence as the notification centre: at most once a minute. */
export const ADR_REQUESTS_POLL_MS = 60_000;

export interface PendingADRFollowUps {
  /** Pending information requests waiting on the patient. */
  count: number;
  /** False until the first result (success or failure) for the current session. */
  loaded: boolean;
}

/** One poller per tab, shared by every entry row, so two rows never double the requests. */
const poll = createSharedPoll<number>(
  async (token) => (await fetchADRInformationRequests(token)).length,
  { intervalMs: ADR_REQUESTS_POLL_MS, fallback: 0 },
);

interface PendingState extends PendingADRFollowUps {
  token: string | null;
}

const emptyState: PendingState = { token: null, count: 0, loaded: false };

/**
 * Counts the patient's pending ADR follow-up requests for the entry rows.
 *
 * Reads from the tab's shared poller: one fetch on first use, then at most one a minute
 * while the tab is visible and none while it is hidden. It never throws. A failed load
 * reports `{ count: 0, loaded: true }` because the destination view shows the error itself.
 */
export function usePendingADRFollowUps(): PendingADRFollowUps {
  const accessToken = useSelector((state: RootState) => state.auth.accessToken);
  const [state, setState] = useState<PendingState>(emptyState);
  useEffect(() => {
    if (!accessToken) return;
    return poll.subscribe(accessToken, (snapshot) =>
      setState({ token: snapshot.token, count: snapshot.value, loaded: snapshot.loaded }),
    );
  }, [accessToken]);

  // Results belong to the token that produced them, so sign-out clears at once.
  if (!accessToken || state.token !== accessToken) {
    return { count: 0, loaded: false };
  }
  return { count: state.count, loaded: state.loaded };
}
