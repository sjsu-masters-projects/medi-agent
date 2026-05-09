"use client";

import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { api } from "@/services/api";
import {
    fetchTodayFeed,
    loadMockFeed,
    markTaskComplete,
    setMissedTasks,
} from "@/store/slices/feed-slice";
import type { AppDispatch, RootState } from "@/store/store";
import { FeedTaskStatus, FeedTaskType, type AdherenceStats, type FeedSummary, type FeedTask } from "@/types";

/**
 * Raw shape of the adherence stats API response.
 * The FastAPI backend returns snake_case keys by default.
 */
interface AdherenceStatsRaw {
    patient_id: string;
    overall_score: number;
    medication_score: number;
    obligation_score: number;
    current_streak_days: number;
    period_days: number;
    total_expected: number;
    total_completed: number;
}

function normalizeAdherenceStats(raw: AdherenceStatsRaw): AdherenceStats {
    return {
        currentStreakDays: raw.current_streak_days ?? 0,
        medicationScore: raw.medication_score ?? 0,
        obligationScore: raw.obligation_score ?? 0,
        overallScore: raw.overall_score ?? 0,
        patientId: raw.patient_id,
        periodDays: raw.period_days ?? 30,
        totalCompleted: raw.total_completed ?? 0,
        totalExpected: raw.total_expected ?? 0,
    };
}

const mockFeedTasks: FeedTask[] = [
    {
        completedAt: new Date().toISOString(),
        description: "Take with breakfast.",
        frequency: "daily",
        id: "demo-1",
        name: "Metformin 500mg",
        provider: {
            clinicName: "City Health",
            id: "provider-1",
            name: "Dr. Smith",
            specialty: "Primary Care",
        },
        scheduledTime: "08:00:00",
        status: FeedTaskStatus.COMPLETED,
        targetId: "target-1",
        type: FeedTaskType.MEDICATION,
    },
    {
        description: "30 minutes of low-impact walking.",
        frequency: "daily",
        id: "demo-2",
        name: "Daily walk",
        provider: {
            clinicName: "City Health",
            id: "provider-2",
            name: "Dr. Patel",
            specialty: "Cardiology",
        },
        scheduledTime: "12:00:00",
        status: FeedTaskStatus.PENDING,
        targetId: "target-2",
        type: FeedTaskType.OBLIGATION,
    },
    {
        description: "Take with dinner.",
        frequency: "daily",
        id: "demo-3",
        name: "Lisinopril 10mg",
        provider: {
            clinicName: "City Health",
            id: "provider-2",
            name: "Dr. Patel",
            specialty: "Cardiology",
        },
        scheduledTime: "18:00:00",
        status: FeedTaskStatus.PENDING,
        targetId: "target-3",
        type: FeedTaskType.MEDICATION,
    },
];

const mockFeedSummary: FeedSummary = {
    completed: 1,
    missed: 0,
    pending: 2,
    skipped: 0,
    total: 3,
};

const mockAdherenceStats: AdherenceStats = {
    currentStreakDays: 4,
    medicationScore: 0.83,
    obligationScore: 0.67,
    overallScore: 0.75,
    patientId: "demo-patient",
    periodDays: 30,
    totalCompleted: 18,
    totalExpected: 24,
};

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
    const [adherenceStats, setAdherenceStats] = useState<AdherenceStats>(mockAdherenceStats);

    useEffect(() => {
        dispatch(fetchTodayFeed({ token: accessToken }))
            .unwrap()
            .catch(() => {
                dispatch(loadMockFeed({ summary: mockFeedSummary, tasks: mockFeedTasks }));
            });
    }, [accessToken, dispatch]);

    useEffect(() => {
        api.get<AdherenceStatsRaw>("/api/v1/adherence/stats", { token: accessToken ?? undefined })
            .then((response) => setAdherenceStats(normalizeAdherenceStats(response)))
            .catch(() => setAdherenceStats(mockAdherenceStats));
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

    return {
        adherenceStats,
        error: feed.error,
        loading: feed.loading,
        markComplete,
        summary: feed.summary,
        tasks: feed.tasks,
        usingMockData: feed.usingMockData,
    };
}
