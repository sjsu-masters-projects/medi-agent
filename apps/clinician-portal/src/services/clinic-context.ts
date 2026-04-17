export interface ClinicContext {
    clinicCode: string;
    clinicId: string;
    clinicName: string;
    status: "active" | "suspended";
}

const CLINIC_CONTEXT_STORAGE_KEY = "mediagent-clinician-clinic-context";

function isBrowser(): boolean {
    return typeof window !== "undefined";
}

export function readStoredClinicContext(): ClinicContext | null {
    if (!isBrowser()) {
        return null;
    }

    const raw =
        window.localStorage.getItem(CLINIC_CONTEXT_STORAGE_KEY) ||
        window.sessionStorage.getItem(CLINIC_CONTEXT_STORAGE_KEY);
    if (!raw) {
        return null;
    }

    try {
        const parsed = JSON.parse(raw) as ClinicContext;
        if (!parsed?.clinicCode || !parsed?.clinicName || !parsed?.clinicId) {
            return null;
        }

        window.localStorage.setItem(CLINIC_CONTEXT_STORAGE_KEY, JSON.stringify(parsed));
        window.sessionStorage.removeItem(CLINIC_CONTEXT_STORAGE_KEY);
        return parsed;
    } catch {
        return null;
    }
}

export function writeStoredClinicContext(context: ClinicContext): void {
    if (!isBrowser()) {
        return;
    }

    window.localStorage.setItem(CLINIC_CONTEXT_STORAGE_KEY, JSON.stringify(context));
    window.sessionStorage.removeItem(CLINIC_CONTEXT_STORAGE_KEY);
}

export function clearStoredClinicContext(): void {
    if (!isBrowser()) {
        return;
    }

    window.localStorage.removeItem(CLINIC_CONTEXT_STORAGE_KEY);
    window.sessionStorage.removeItem(CLINIC_CONTEXT_STORAGE_KEY);
}
