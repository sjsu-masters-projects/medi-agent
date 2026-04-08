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
import type { AdherenceStats, FeedSummary, FeedTask } from "@/types";

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
        status: "completed",
        targetId: "target-1",
        type: "medication",
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
        status: "pending",
        targetId: "target-2",
        type: "obligation",
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
        status: "pending",
        targetId: "target-3",
        type: "medication",
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
        .filter((task) => task.status === "pending" && task.scheduledTime)
        .filter((task) => {
            const [hours, minutes] = task.scheduledTime?.split(":").map((value) => Number.parseInt(value, 10)) ?? [];
            return Number.isFinite(hours) && Number.isFinite(minutes) && hours * 60 + minutes < currentMinutes;
        })
        .map((task) => task.id);
}

export function useFeedData() {
    const dispatch = useDispatch<AppDispatch>();
    const feed = useSelector((state: RootState) => state.feed);
    const token = useSelector((state: RootState) => state.auth.token);
    const [adherenceStats, setAdherenceStats] = useState<AdherenceStats>(mockAdherenceStats);

    useEffect(() => {
        dispatch(fetchTodayFeed({ token }))
            .unwrap()
            .catch(() => {
                dispatch(loadMockFeed({ summary: mockFeedSummary, tasks: mockFeedTasks }));
            });
    }, [dispatch, token]);

    useEffect(() => {
        api.get<AdherenceStats>("/api/v1/adherence/stats", { token: token ?? undefined })
            .then((response) => setAdherenceStats(response))
            .catch(() => setAdherenceStats(mockAdherenceStats));
    }, [token]);

    useEffect(() => {
        const missedIds = getMissedTaskIds(feed.tasks);
        if (missedIds.length > 0) {
            dispatch(setMissedTasks(missedIds));
        }
    }, [dispatch, feed.tasks]);

    async function markComplete(task: FeedTask) {
        const completedAt = new Date().toISOString();
        dispatch(markTaskComplete({ completedAt, taskId: task.id }));

        if (!token) {
            return;
        }

        try {
            await api.post(
                "/api/v1/adherence",
                {
                    status: task.type === "medication" ? "taken" : "completed",
                    target_id: task.targetId,
                    target_type: task.type,
                },
                { token },
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
