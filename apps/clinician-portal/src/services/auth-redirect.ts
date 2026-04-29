import { buildLoginRedirectUrl } from "../../../../packages/shared/src/utils/return-path";
import { clearStoredSession } from "@/services/auth-session";

export type AuthRedirectReason = "session_expired" | "unauthorized" | "logged_out";

interface RedirectToLoginParams {
    reason?: AuthRedirectReason;
    returnPath?: string;
}

function getCurrentReturnPath(): string {
    if (typeof window === "undefined") {
        return "/";
    }

    return `${window.location.pathname}${window.location.search}`;
}

export function redirectToLogin({ reason, returnPath }: RedirectToLoginParams = {}) {
    if (typeof window === "undefined") {
        return;
    }

    if (window.location.pathname === "/login") {
        return;
    }

    clearStoredSession();

    const loginUrl = buildLoginRedirectUrl({
        loginPath: "/login",
        reason,
        returnPath: returnPath ?? getCurrentReturnPath(),
    });

    window.location.assign(loginUrl);
}
