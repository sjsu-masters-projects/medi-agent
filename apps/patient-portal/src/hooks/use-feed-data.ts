"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { api } from "@/services/api";
import { redirectToLogin } from "@/services/auth-redirect";
import { refreshPatientSession } from "@/services/auth-refresh";
import { writeStoredSession } from "@/services/auth-session";
import {
  inferDocumentType,
  type DocumentApiRecord,
} from "@/services/documents";
import { hashDocumentFile, uploadDocumentToStorage } from "@/services/storage";
import {
  hydrateSession,
  logout,
  type PatientAuthUser,
} from "@/store/slices/auth-slice";
import {
  fetchTodayFeed,
  markTaskComplete,
  markTaskSkipped,
} from "@/store/slices/feed-slice";
import type { AppDispatch, RootState } from "@/store/store";
import {
  FeedTaskType,
  type AdherenceStats,
  type FeedTask,
} from "@/types";
import { getEffectiveSessionExpiresAt } from "../../../../packages/shared/src/utils/jwt-expiry";

interface ApiAdherenceStats {
  current_streak_days?: number;
  currentStreakDays?: number;
  medication_score?: number;
  medicationScore?: number;
  obligation_score?: number;
  obligationScore?: number;
  overall_score?: number;
  overallScore?: number;
  patient_id?: string;
  patientId?: string;
  period_days?: number;
  periodDays?: number;
  total_completed?: number;
  totalCompleted?: number;
  total_expected?: number;
  totalExpected?: number;
}

const emptyAdherenceStats: AdherenceStats = {
  currentStreakDays: 0,
  medicationScore: 0,
  obligationScore: 0,
  overallScore: 0,
  patientId: "",
  periodDays: 30,
  totalCompleted: 0,
  totalExpected: 0,
};

const DOCUMENT_IMPORT_REFRESH_WINDOW_SECONDS = 2 * 60;

interface ActivePatientSession {
  accessToken: string;
  user: PatientAuthUser;
}

function mapAdherenceStats(stats: ApiAdherenceStats): AdherenceStats {
  return {
    currentStreakDays:
      stats.currentStreakDays ?? stats.current_streak_days ?? 0,
    medicationScore: stats.medicationScore ?? stats.medication_score ?? 0,
    obligationScore: stats.obligationScore ?? stats.obligation_score ?? 0,
    overallScore: stats.overallScore ?? stats.overall_score ?? 0,
    patientId: stats.patientId ?? stats.patient_id ?? "",
    periodDays: stats.periodDays ?? stats.period_days ?? 30,
    totalCompleted: stats.totalCompleted ?? stats.total_completed ?? 0,
    totalExpected: stats.totalExpected ?? stats.total_expected ?? 0,
  };
}

export function useFeedData() {
  const dispatch = useDispatch<AppDispatch>();
  const feed = useSelector((state: RootState) => state.feed);
  const { accessToken, expiresAt, refreshToken, user } = useSelector(
    (state: RootState) => state.auth,
  );
  const [adherenceStats, setAdherenceStats] =
    useState<AdherenceStats>(emptyAdherenceStats);
  const [documentImportError, setDocumentImportError] = useState<string | null>(
    null,
  );
  const [documentImporting, setDocumentImporting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const submissionInFlight = useRef(false);

  const refreshFeed = useCallback(() => {
    if (!accessToken) {
      return;
    }

    void dispatch(fetchTodayFeed({ token: accessToken }));
  }, [accessToken, dispatch]);

  useEffect(() => {
    refreshFeed();
  }, [refreshFeed]);

  useEffect(() => {
    if (!accessToken) {
      setAdherenceStats(emptyAdherenceStats);
      return;
    }

    api
      .get<ApiAdherenceStats>("/api/v1/adherence/stats", {
        token: accessToken,
      })
      .then((response) => setAdherenceStats(mapAdherenceStats(response)))
      .catch(() => setAdherenceStats(emptyAdherenceStats));
  }, [accessToken]);

  async function submitAdherence(task: FeedTask, status: string, barrierCode?: string, notes?: string): Promise<boolean> {
    if (submissionInFlight.current) return false;
    setActionError(null);
    if (!accessToken) {
      setActionError("Please sign in again. Your response has not been saved.");
      return false;
    }
    submissionInFlight.current = true;
    setSubmitting(true);
    try {
      await api.post(
        "/api/v1/adherence/",
        {
          scheduled_time: task.scheduledAt,
          status,
          target_id: task.targetId,
          target_type: task.type,
          barrier_code: barrierCode,
          notes: notes?.trim() || undefined,
        },
        { token: accessToken },
      );
      // Only acknowledge a response that the service actually saved.
      if (status === "skipped") dispatch(markTaskSkipped({ taskId: task.id }));
      else dispatch(markTaskComplete({ completedAt: new Date().toISOString(), taskId: task.id }));
      refreshFeed();
      void api.get<ApiAdherenceStats>("/api/v1/adherence/stats", { token: accessToken })
        .then((response) => setAdherenceStats(mapAdherenceStats(response)))
        .catch(() => { /* A statistics refresh must not undo a saved response. */ });
      return true;
    } catch {
      setActionError("We couldn’t confirm that your response was saved. Refresh before retrying; your schedule has not been marked complete.");
      return false;
    } finally {
      submissionInFlight.current = false;
      setSubmitting(false);
    }
  }

  async function markComplete(task: FeedTask) {
    return submitAdherence(task, task.type === FeedTaskType.MEDICATION ? "taken" : "completed");
  }

  async function reportBarrier(
    task: FeedTask,
    barrierCode: "side_effects" | "cost" | "access" | "schedule" | "confusion" | "other",
    notes?: string,
  ) {
    return submitAdherence(task, "skipped", barrierCode, notes);
  }

  async function getDocumentImportSession(): Promise<ActivePatientSession | null> {
    if (!accessToken || !user) {
      setDocumentImportError(
        "Please sign in again before importing a clinical document.",
      );
      return null;
    }

    const effectiveExpiresAt = getEffectiveSessionExpiresAt(
      expiresAt,
      accessToken,
    );
    const shouldRefresh =
      !effectiveExpiresAt ||
      effectiveExpiresAt - Math.floor(Date.now() / 1000) <=
        DOCUMENT_IMPORT_REFRESH_WINDOW_SECONDS;

    if (!shouldRefresh) {
      return {
        accessToken,
        user,
      };
    }

    if (!refreshToken) {
      dispatch(logout());
      redirectToLogin({ reason: "session_expired" });
      setDocumentImportError(
        "Your session expired. Please sign in again before importing a clinical document.",
      );
      return null;
    }

    try {
      const session = await refreshPatientSession(refreshToken);
      writeStoredSession(session);
      dispatch(hydrateSession(session));
      return session;
    } catch {
      dispatch(logout());
      redirectToLogin({ reason: "session_expired" });
      setDocumentImportError(
        "Your session expired. Please sign in again before importing a clinical document.",
      );
      return null;
    }
  }

  async function importDocumentFile(file: File) {
    setDocumentImporting(true);
    setDocumentImportError(null);
    try {
      const session = await getDocumentImportSession();
      if (!session) {
        return;
      }

      const [filePath, contentHash] = await Promise.all([
        uploadDocumentToStorage({
          file,
          patientId: session.user.id,
          token: session.accessToken,
        }),
        hashDocumentFile(file),
      ]);
      await api.post<DocumentApiRecord>(
        "/api/v1/documents/",
        {
          document_type: inferDocumentType(file),
          file_name: file.name,
          file_path: filePath,
          file_size_bytes: file.size,
          mime_type: file.type || "application/octet-stream",
          source_clinic: "Patient uploaded document",
          content_hash: contentHash,
          start_ingestion: true,
        },
        { token: session.accessToken },
      );
    } catch (error) {
      setDocumentImportError(
        (error as Error).message || "Document import failed.",
      );
    } finally {
      setDocumentImporting(false);
    }
  }

  return {
    actionError,
    submitting,
    adherenceStats,
    documentImportError,
    documentImporting,
    error: feed.error,
    importDocumentFile,
    loading: feed.loading,
    markComplete,
    reportBarrier,
    refreshFeed,
    summary: feed.summary,
    tasks: feed.tasks,
  };
}
