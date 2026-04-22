import { createAsyncThunk, createSlice, type PayloadAction } from "@reduxjs/toolkit";
import { api } from "@/services/api";
import { FeedTaskStatus, type FeedSummary, type FeedTask, type TodayFeedResponse } from "@/types";

interface FeedState {
    tasks: FeedTask[];
    summary: FeedSummary;
    loading: boolean;
    error: string | null;
    usingMockData: boolean;
}

export const defaultFeedSummary: FeedSummary = {
    completed: 0,
    missed: 0,
    pending: 0,
    skipped: 0,
    total: 0,
};

const initialState: FeedState = {
    tasks: [],
    summary: defaultFeedSummary,
    loading: false,
    error: null,
    usingMockData: false,
};

export const fetchTodayFeed = createAsyncThunk<
    TodayFeedResponse,
    { token?: string | null } | undefined,
    { rejectValue: string }
>("feed/fetchToday", async (payload, { rejectWithValue }) => {
    try {
        return await api.get<TodayFeedResponse>("/api/v1/feed/today", {
            token: payload?.token ?? undefined,
        });
    } catch (error) {
        return rejectWithValue((error as Error).message);
    }
});

export const feedSlice = createSlice({
    name: "feed",
    initialState,
    reducers: {
        loadMockFeed: (
            state,
            action: PayloadAction<{ summary: FeedSummary; tasks: FeedTask[] }>,
        ) => {
            state.tasks = action.payload.tasks;
            state.summary = action.payload.summary;
            state.loading = false;
            state.error = null;
            state.usingMockData = true;
        },
        markTaskComplete: (
            state,
            action: PayloadAction<{ completedAt: string; taskId: string }>,
        ) => {
            state.tasks = state.tasks.map((task) =>
                task.id === action.payload.taskId
                    ? {
                          ...task,
                          completedAt: action.payload.completedAt,
                          status: FeedTaskStatus.COMPLETED,
                      }
                    : task,
            );

            state.summary.completed = state.tasks.filter((task) => task.status === FeedTaskStatus.COMPLETED).length;
            state.summary.missed = state.tasks.filter((task) => task.status === FeedTaskStatus.MISSED).length;
            state.summary.pending = state.tasks.filter((task) => task.status === FeedTaskStatus.PENDING).length;
        },
        setMissedTasks: (state, action: PayloadAction<string[]>) => {
            const missedIds = new Set(action.payload);
            state.tasks = state.tasks.map((task) =>
                missedIds.has(task.id) && task.status === FeedTaskStatus.PENDING
                    ? { ...task, status: FeedTaskStatus.MISSED }
                    : task,
            );
            state.summary.missed = state.tasks.filter((task) => task.status === FeedTaskStatus.MISSED).length;
            state.summary.pending = state.tasks.filter((task) => task.status === FeedTaskStatus.PENDING).length;
        },
    },
    extraReducers: (builder) => {
        builder
            .addCase(fetchTodayFeed.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(fetchTodayFeed.fulfilled, (state, action) => {
                state.tasks = action.payload.tasks;
                state.summary = action.payload.summary;
                state.loading = false;
                state.error = null;
                state.usingMockData = false;
            })
            .addCase(fetchTodayFeed.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload ?? "Unable to load today feed.";
            });
    },
});

export const { loadMockFeed, markTaskComplete, setMissedTasks } = feedSlice.actions;
