"use client";

import { useCallback, useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { api } from "@/services/api";
import {
    fetchTodayFeed,
    markTaskComplete,
    setMissedTasks,
} from "@/store/slices/feed-slice";
import type { AppDispatch, RootState } from "@/store/store";
import { FeedTaskStatus, FeedTaskType, type AdherenceStats, type FeedTask } from "@/types";

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

function mapAdherenceStats(stats: ApiAdherenceStats): AdherenceStats {
    return {
        currentStreakDays: stats.currentStreakDays ?? stats.current_streak_days ?? 0,
        medicationScore: stats.medicationScore ?? stats.medication_score ?? 0,
        obligationScore: stats.obligationScore ?? stats.obligation_score ?? 0,
        overallScore: stats.overallScore ?? stats.overall_score ?? 0,
        patientId: stats.patientId ?? stats.patient_id ?? "",
        periodDays: stats.periodDays ?? stats.period_days ?? 30,
        totalCompleted: stats.totalCompleted ?? stats.total_completed ?? 0,
        totalExpected: stats.totalExpected ?? stats.total_expected ?? 0,
    };
}

function getMissedTaskIds(tasks: FeedTask[]) {
    const now = new Date();
    const currentMinutes = now.getHours() * 60 + now.getMinutes();

    return tasks
        .filter((task) => task.status === FeedTaskStatus.PENDING && task.scheduledTime)
        .filter((task) => {
            const [hours, minutes] = task.scheduledTime?.split(":").map((value) => Number.parseInt(value, 10)) ?? [];
            return Number.isFinite(hours) && Number.isFinite(minutes) && hours * 60 + minutes < currentMinutes;
        })
        .map((task) => task.id);
}

export function useFeedData() {
    const dispatch = useDispatch<AppDispatch>();
    const feed = useSelector((state: RootState) => state.feed);
    const accessToken = useSelector((state: RootState) => state.auth.accessToken);
    const [adherenceStats, setAdherenceStats] = useState<AdherenceStats>(emptyAdherenceStats);
    const [documentImportError, setDocumentImportError] = useState<string | null>(null);
    const [documentImporting, setDocumentImporting] = useState(false);

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

        api.get<ApiAdherenceStats>("/api/v1/adherence/stats", { token: accessToken ?? undefined })
            .then((response) => setAdherenceStats(mapAdherenceStats(response)))
            .catch(() => setAdherenceStats(emptyAdherenceStats));
    }, [accessToken]);

    useEffect(() => {
        const missedIds = getMissedTaskIds(feed.tasks);
        if (missedIds.length > 0) {
            dispatch(setMissedTasks(missedIds));
        }
    }, [dispatch, feed.tasks]);

    async function markComplete(task: FeedTask) {
        const completedAt = new Date().toISOString();
        dispatch(markTaskComplete({ completedAt, taskId: task.id }));

        if (!accessToken) {
            return;
        }

        try {
            await api.post(
                "/api/v1/adherence",
                {
                    scheduled_time: task.scheduledAt,
                    status: task.type === FeedTaskType.MEDICATION ? "taken" : "completed",
                    target_id: task.targetId,
                    target_type: task.type,
                },
                { token: accessToken },
            );
        } catch {
            // Keep optimistic UI state even when backend is unavailable.
        }
    }

    async function importDemoDocument() {
        if (!accessToken) {
            setDocumentImportError("Please sign in again before importing a clinical document.");
            return;
        }

        setDocumentImporting(true);
        setDocumentImportError(null);
        try {
            await api.post("/api/v1/documents/extractions/import", undefined, {
                token: accessToken,
            });
            await dispatch(fetchTodayFeed({ token: accessToken })).unwrap();
        } catch (error) {
            setDocumentImportError((error as Error).message || "Document import failed.");
        } finally {
            setDocumentImporting(false);
        }
    }

    return {
        adherenceStats,
        documentImportError,
        documentImporting,
        error: feed.error,
        importDemoDocument,
        loading: feed.loading,
        markComplete,
        refreshFeed,
        summary: feed.summary,
        tasks: feed.tasks,
    };
}
