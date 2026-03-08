/**
 * Shared constants.
 */

// ── API Routes ────────────────────────────────────
export const API_V1_PREFIX = "/api/v1";

export const API_ROUTES = {
    AUTH: {
        SIGNUP: `${API_V1_PREFIX}/auth/signup`,
        LOGIN: `${API_V1_PREFIX}/auth/login`,
        REFRESH: `${API_V1_PREFIX}/auth/refresh`,
    },
    PATIENTS: {
        ME: `${API_V1_PREFIX}/patients/me`,
        CARE_TEAM: `${API_V1_PREFIX}/patients/me/care-team`,
    },
    DOCUMENTS: {
        BASE: `${API_V1_PREFIX}/documents`,
        UPLOAD: `${API_V1_PREFIX}/documents/upload`,
    },
    MEDICATIONS: {
        BASE: `${API_V1_PREFIX}/medications`,
    },
    FEED: {
        TODAY: `${API_V1_PREFIX}/feed/today`,
    },
    CHAT: {
        HISTORY: (patientId: string) => `${API_V1_PREFIX}/chat/history/${patientId}`,
        WS: (patientId: string) => `/ws/chat/${patientId}`,
    },
    ADR: {
        ASSESSMENTS: `${API_V1_PREFIX}/adr/assessments`,
        MEDWATCH: `${API_V1_PREFIX}/adr/medwatch`,
    },
} as const;

// ── Clinical Thresholds ───────────────────────────
export const NARANJO_THRESHOLD = {
    DEFINITE: 9,
    PROBABLE: 5,
    POSSIBLE: 1,
    DOUBTFUL: 0,
} as const;

export const RISK_LEVELS = {
    LOW: "low",
    MEDIUM: "medium",
    HIGH: "high",
} as const;
