import {
    createClient,
    type RealtimeChannel,
    type RealtimePostgresChangesPayload,
    type SupabaseClient,
} from "@supabase/supabase-js";
import { readStoredSession } from "@/services/auth-session";

const DASHBOARD_REALTIME_TABLES = ["adherence_logs", "symptom_reports", "adr_assessments"] as const;

type DashboardRealtimeTable = (typeof DASHBOARD_REALTIME_TABLES)[number];

interface PostgresChangePayload {
    new: { patient_id?: string } | null;
    old: { patient_id?: string } | null;
}

interface SubscribeDashboardRealtimeParams {
    onPatientChanged: (patientId: string, table: DashboardRealtimeTable) => void;
}

function getAccessToken(): string {
    if (typeof window === "undefined") {
        return "";
    }

    return (
        readStoredSession()?.accessToken ??
        window.localStorage.getItem("access_token") ??
        ""
    );
}

function createRealtimeClient(): SupabaseClient | null {
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    const token = getAccessToken();

    if (!supabaseUrl || !supabaseAnonKey || !token) {
        return null;
    }

    return createClient(supabaseUrl, supabaseAnonKey, {
        accessToken: async () => getAccessToken(),
        auth: {
            autoRefreshToken: false,
            detectSessionInUrl: false,
            persistSession: false,
        },
    });
}

function patientIdFromPayload(payload: PostgresChangePayload): string | null {
    const fromNew = payload.new?.patient_id;
    if (fromNew && typeof fromNew === "string") {
        return fromNew;
    }

    const fromOld = payload.old?.patient_id;
    if (fromOld && typeof fromOld === "string") {
        return fromOld;
    }

    return null;
}

export function subscribeDashboardRealtime({
    onPatientChanged,
}: SubscribeDashboardRealtimeParams): () => void {
    const client = createRealtimeClient();
    if (!client) {
        return () => {};
    }

    const channel: RealtimeChannel = client.channel("clinician-dashboard-realtime");

    for (const table of DASHBOARD_REALTIME_TABLES) {
        channel.on(
            "postgres_changes",
            {
                event: "*",
                schema: "public",
                table,
            },
            (payload: RealtimePostgresChangesPayload<{ patient_id?: string }>) => {
                const patientId = patientIdFromPayload(payload as PostgresChangePayload);
                if (!patientId) {
                    return;
                }
                onPatientChanged(patientId, table);
            },
        );
    }

    channel.subscribe();

    return () => {
        void client.removeChannel(channel);
    };
}
