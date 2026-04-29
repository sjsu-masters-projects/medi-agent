import { api } from "@/services/api";
import { PortalUserRole } from "@/types";
import type { PatientAuthSession } from "@/store/slices/auth-slice";

interface RefreshResponse {
    tokens: {
        access_token: string;
        refresh_token: string;
        expires_at: number;
    };
    user: {
        email: string;
        id: string;
        role: typeof PortalUserRole[keyof typeof PortalUserRole];
    };
}

export async function refreshPatientSession(refreshToken: string): Promise<PatientAuthSession> {
    const response = await api.post<RefreshResponse>("/api/v1/auth/refresh", {
        expected_role: PortalUserRole.PATIENT,
        refresh_token: refreshToken,
    });

    if (response.user.role !== PortalUserRole.PATIENT) {
        throw new Error("This session belongs to a clinician account.");
    }

    return {
        accessToken: response.tokens.access_token,
        expiresAt: response.tokens.expires_at,
        refreshToken: response.tokens.refresh_token,
        user: {
            email: response.user.email,
            id: response.user.id,
            role: PortalUserRole.PATIENT,
        },
    } satisfies PatientAuthSession;
}
