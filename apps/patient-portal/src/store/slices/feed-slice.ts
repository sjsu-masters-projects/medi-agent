import { createAsyncThunk, createSlice, type PayloadAction } from "@reduxjs/toolkit";
import { api } from "@/services/api";
import { FeedTaskStatus, type FeedSummary, type FeedTask, type TodayFeedResponse } from "@/types";

interface ApiFeedProvider {
    id: string;
    name: string;
    specialty: string;
    clinic_name?: string;
    clinicName?: string;
}

interface ApiFeedTask {
    id: string;
    type: FeedTask["type"];
    target_id?: string;
    targetId?: string;
    name: string;
    description?: string | null;
    frequency: string;
    scheduled_time?: string | null;
    scheduledTime?: string | null;
    scheduled_at?: string | null;
    scheduledAt?: string | null;
    status: FeedTask["status"];
    completed_at?: string | null;
    completedAt?: string | null;
    requires_schedule_configuration?: boolean;
    requiresScheduleConfiguration?: boolean;
    provider?: ApiFeedProvider | null;
}

interface ApiTodayFeedResponse {
    date: string;
    timezone: string;
    tasks: ApiFeedTask[];
    summary: FeedSummary;
}

interface FeedState {
    tasks: FeedTask[];
    summary: FeedSummary;
    loading: boolean;
    error: string | null;
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
};

function mapApiProvider(provider?: ApiFeedProvider | null): FeedTask["provider"] {
    if (!provider) {
        return undefined;
    }

    return {
        clinicName: provider.clinicName ?? provider.clinic_name ?? "",
        id: provider.id,
        name: provider.name,
        specialty: provider.specialty,
    };
}

function mapApiTask(task: ApiFeedTask): FeedTask {
    return {
        completedAt: task.completedAt ?? task.completed_at ?? undefined,
        description: task.description ?? undefined,
        frequency: task.frequency,
        id: task.id,
        name: task.name,
        provider: mapApiProvider(task.provider),
        requiresScheduleConfiguration: Boolean(
            task.requiresScheduleConfiguration ?? task.requires_schedule_configuration ?? false,
        ),
        scheduledAt: task.scheduledAt ?? task.scheduled_at ?? undefined,
        scheduledTime: task.scheduledTime ?? task.scheduled_time ?? undefined,
        status: task.status,
        targetId: task.targetId ?? task.target_id ?? "",
        type: task.type,
    };
}

function mapTodayFeedResponse(response: ApiTodayFeedResponse): TodayFeedResponse {
    return {
        date: response.date,
        summary: {
            ...defaultFeedSummary,
            ...response.summary,
        },
        tasks: response.tasks.map(mapApiTask),
        timezone: response.timezone,
    };
}

export const fetchTodayFeed = createAsyncThunk<
    TodayFeedResponse,
    { token?: string | null } | undefined,
    { rejectValue: string }
>("feed/fetchToday", async (payload, { rejectWithValue }) => {
    try {
        const response = await api.get<ApiTodayFeedResponse>("/api/v1/feed/today", {
            token: payload?.token ?? undefined,
        });
        return mapTodayFeedResponse(response);
    } catch (error) {
        return rejectWithValue((error as Error).message);
    }
});

export const feedSlice = createSlice({
    name: "feed",
    initialState,
    reducers: {
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
            })
            .addCase(fetchTodayFeed.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload ?? "Unable to load today feed.";
            });
    },
});

export const { markTaskComplete, setMissedTasks } = feedSlice.actions;
