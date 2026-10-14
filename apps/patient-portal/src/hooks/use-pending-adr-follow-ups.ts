"use client";

import { useEffect, useState } from "react";
import { useSelector } from "react-redux";

import { fetchADRInformationRequests } from "@/services/adr-follow-up";
import type { RootState } from "@/store/store";

/** Focus and visibility often fire together; skip a refetch this soon after the last one. */
const MIN_REFETCH_INTERVAL_MS = 5_000;

export interface PendingADRFollowUps {
  /** Pending information requests waiting on the patient. */
  count: number;
  /** False until the first result (success or failure) for the current session. */
  loaded: boolean;
}

interface PendingState extends PendingADRFollowUps {
  token: string | null;
}

const emptyState: PendingState = { token: null, count: 0, loaded: false };

/**
 * Counts the patient's pending ADR follow-up requests for the entry rows.
 *
 * Fetches on mount and again when the window regains focus or the tab becomes
 * visible. It never polls, ignores responses from a previous session or request,
 * and never throws. A failed load reports `{ count: 0, loaded: true }` because
 * the destination view shows the error itself.
 */
export function usePendingADRFollowUps(): PendingADRFollowUps {
  const accessToken = useSelector((state: RootState) => state.auth.accessToken);
  const [state, setState] = useState<PendingState>(emptyState);
  useEffect(() => {
    if (!accessToken) return;
    const token = accessToken;
    // Only the newest request of this session may write; cleanup ends the session.
    let latest = 0;
    let active = true;
    let lastStartedAt = 0;

    const load = () => {
      const request = ++latest;
      lastStartedAt = Date.now();
      fetchADRInformationRequests(token)
        .then((requests) => requests.length)
        .catch(() => 0)
        .then((count) => {
          if (active && request === latest) {
            setState({ token, count, loaded: true });
          }
        });
    };
    const refetch = () => {
      if (document.visibilityState === "hidden") return;
      if (Date.now() - lastStartedAt < MIN_REFETCH_INTERVAL_MS) return;
      load();
    };

    load();
    window.addEventListener("focus", refetch);
    document.addEventListener("visibilitychange", refetch);
    return () => {
      active = false;
      window.removeEventListener("focus", refetch);
      document.removeEventListener("visibilitychange", refetch);
    };
  }, [accessToken]);

  // Results belong to the token that produced them, so sign-out clears at once.
  if (!accessToken || state.token !== accessToken) {
    return { count: 0, loaded: false };
  }
  return { count: state.count, loaded: state.loaded };
}
