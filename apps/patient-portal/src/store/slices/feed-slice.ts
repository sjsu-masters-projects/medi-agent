import { createAsyncThunk, createSlice, type PayloadAction } from "@reduxjs/toolkit";
import { api } from "@/services/api";
import { FeedTaskStatus, type CareTeamFilterOption, type FeedSummary, type PlanOwner, type FeedTask, type TodayFeedResponse } from "@/types";
import type { Locale } from "@/types";
import { ApiTransportError } from "../../../../../packages/shared/src/utils/api-transport";

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
    content_locale?: string | null;
    provider?: ApiFeedProvider | null;
    care_plan_item_id?: string | null;
    carePlanItemId?: string | null;
    care_plan?: {
        version_number: number;
        category: string;
        effective_start_date?: string | null;
        effective_end_date?: string | null;
    } | null;
    plan_owner?: PlanOwner | null;
    plan_owners?: PlanOwner[] | null;
    combined_item_ids?: string[] | null;
}

interface ApiTodayFeedResponse {
    date: string;
    timezone: string;
    tasks: ApiFeedTask[];
    summary: FeedSummary;
    care_team_filters?: CareTeamFilterOption[] | null;
    contact_clinic?: boolean | null;
}

interface FeedState {
    tasks: FeedTask[];
    summary: FeedSummary;
    careTeamFilters: CareTeamFilterOption[];
    contactClinic: boolean;
    loading: boolean;
    error: string | null;
    locale: Locale | null;
    currentRequestId: string | null;
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
    careTeamFilters: [],
    contactClinic: false,
    loading: false,
    error: null,
    locale: null,
    currentRequestId: null,
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
        carePlanItemId: task.carePlanItemId ?? task.care_plan_item_id ?? undefined,
        contentLocale: task.content_locale === "en-US" || task.content_locale === "es-MX" ? task.content_locale : undefined,
        carePlan: task.care_plan
            ? {
                  versionNumber: task.care_plan.version_number,
                  category: task.care_plan.category,
                  effectiveStartDate: task.care_plan.effective_start_date ?? undefined,
                  effectiveEndDate: task.care_plan.effective_end_date ?? undefined,
              }
            : undefined,
        description: task.description ?? undefined,
        frequency: task.frequency,
        id: task.id,
        ...(task.plan_owner !== undefined ? { planOwner: task.plan_owner } : {}),
        ...(task.plan_owners?.length ? { planOwners: task.plan_owners } : {}),
        ...(task.combined_item_ids?.length ? { combinedItemIds: task.combined_item_ids } : {}),
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
        careTeamFilters: response.care_team_filters ?? [],
        contactClinic: Boolean(response.contact_clinic),
    };
}

export const fetchTodayFeed = createAsyncThunk<
    TodayFeedResponse,
    { token?: string | null; locale?: Locale } | undefined,
    { rejectValue: string }
>("feed/fetchToday", async (payload, { rejectWithValue }) => {
    try {
        const response = await api.get<ApiTodayFeedResponse>("/api/v1/feed/today", {
            token: payload?.token ?? undefined,
        });
        return mapTodayFeedResponse(response);
    } catch (error) {
        return rejectWithValue(error instanceof ApiTransportError
            ? "offline"
            : "load");
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
        markTaskSkipped: (state, action: PayloadAction<{ taskId: string }>) => {
            state.tasks = state.tasks.map((task) =>
                task.id === action.payload.taskId ? { ...task, status: FeedTaskStatus.SKIPPED } : task,
            );
            state.summary.completed = state.tasks.filter((task) => task.status === FeedTaskStatus.COMPLETED).length;
            state.summary.skipped = state.tasks.filter((task) => task.status === FeedTaskStatus.SKIPPED).length;
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
            .addCase(fetchTodayFeed.pending, (state, action) => {
                state.loading = true;
                state.error = null;
                state.currentRequestId = action.meta.requestId;
            })
            .addCase(fetchTodayFeed.fulfilled, (state, action) => {
                if (state.currentRequestId !== action.meta.requestId) return;
                state.tasks = action.payload.tasks;
                state.summary = action.payload.summary;
                state.careTeamFilters = action.payload.careTeamFilters ?? [];
                state.contactClinic = Boolean(action.payload.contactClinic);
                state.locale = action.meta.arg?.locale ?? "en-US";
                state.currentRequestId = null;
                state.loading = false;
                state.error = null;
            })
            .addCase(fetchTodayFeed.rejected, (state, action) => {
                if (state.currentRequestId !== action.meta.requestId) return;
                const locale = action.meta.arg?.locale ?? "en-US";
                if (state.locale !== locale) {
                    state.tasks = [];
                    state.summary = { ...defaultFeedSummary };
                    state.careTeamFilters = [];
                    state.contactClinic = false;
                }
                state.locale = locale;
                state.currentRequestId = null;
                state.loading = false;
                state.error = action.payload ?? "load";
            });
    },
});

export const { markTaskComplete, markTaskSkipped, setMissedTasks } = feedSlice.actions;
