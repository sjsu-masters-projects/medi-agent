import { getJwtExpiresAt } from "../../../../packages/shared/src/utils/jwt-expiry";
import { api } from "@/services/api";
import { PortalUserRole } from "@/types";
import type { ClinicianAuthSession } from "@/store/slices/auth-slice";

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

export async function refreshClinicianSession(refreshToken: string): Promise<ClinicianAuthSession> {
    const response = await api.post<RefreshResponse>("/api/v1/auth/refresh", {
        expected_role: PortalUserRole.CLINICIAN,
        refresh_token: refreshToken,
    });

    if (response.user.role !== PortalUserRole.CLINICIAN) {
        throw new Error("This session belongs to a patient account.");
    }

    return {
        accessToken: response.tokens.access_token,
        expiresAt:
            response.tokens.expires_at || getJwtExpiresAt(response.tokens.access_token) || 0,
        refreshToken: response.tokens.refresh_token,
        user: {
            email: response.user.email,
            id: response.user.id,
            role: PortalUserRole.CLINICIAN,
        },
    } satisfies ClinicianAuthSession;
}
