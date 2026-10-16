"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useSelector } from "react-redux";
import { fetchActiveIntake, fetchIntake, mutateIntake, startIntake } from "@/services/symptom-intakes";
import type { RootState } from "@/store/store";
import type { SymptomIntake } from "@/types";
import { ApiClientError } from "@/services/api";

type Pending = { id: string; action: string; payload: Record<string, unknown> };
function errorCode(failure: unknown, fallback: string) {
    const details = failure instanceof ApiClientError ? failure.details as { error?: { code?: string } } | null : null;
    return details?.error?.code ?? fallback;
}
export function useSymptomIntake(sessionId = "default") {
    const { accessToken: token, user } = useSelector((state: RootState) => state.auth);
    const scope = `${user?.id ?? ""}:${token ?? ""}:${sessionId}`;
    const latest = useRef(scope);
    useLayoutEffect(() => { latest.current = scope; }, [scope]);
    const controller = useRef<AbortController | null>(null);
    const pending = useRef<Pending | null>(null);
    const running = useRef(false);
    const [pendingScope, setPendingScope] = useState<string | null>(null);
    const [state, setState] = useState<{ scope: string; draft: SymptomIntake | null; error: string | null; busy: boolean }>({ scope, draft: null, error: null, busy: true });
    const draft = state.scope === scope ? state.draft : null;
    const busy = Boolean(token && (state.scope !== scope || state.busy));
    const error = state.scope === scope && state.error;
    const [signal, setSignal] = useState(0);
    useEffect(() => {
        pending.current = null; running.current = false;
        return () => { controller.current?.abort(); pending.current = null; running.current = false; };
    }, [scope]);
    useEffect(() => {
        if (!token || !user) return;
        const request = new AbortController(); controller.current = request;
        const timer = setTimeout(() => {
            if (latest.current === scope && !request.signal.aborted) {
                request.abort();
                setState((previous) => ({ scope, draft: previous.scope === scope ? previous.draft : null,
                    error: "INTAKE_RECOVERY_UNAVAILABLE", busy: false }));
            }
        }, 12000);
        fetchActiveIntake(token, sessionId, request.signal).then((result) => {
            if (latest.current === scope && !request.signal.aborted) {
                if (result && !["collecting", "ready_for_confirmation"].includes(result.status)) {
                    pending.current = null; setPendingScope(null);
                }
                setState({ scope, draft: result, error: null, busy: false });
            }
        }).catch((failure) => {
            if (latest.current === scope && !request.signal.aborted) {
                const code = errorCode(failure, "INTAKE_RECOVERY_UNAVAILABLE");
                setState((previous) => ({ scope, draft: previous.scope === scope ? previous.draft : null,
                    error: code === "INTAKE_PERSISTENCE_UNAVAILABLE" ? "INTAKE_RECOVERY_UNAVAILABLE" : code, busy: false }));
            }
        }).finally(() => clearTimeout(timer));
        return () => { clearTimeout(timer); request.abort(); };
    }, [scope, token, user, signal, sessionId]);
    useEffect(() => {
        const recover = () => {
            if (running.current) return;
            setState((previous) => ({ ...previous, error: null, busy: true }));
            setSignal((n) => n + 1);
        };
        window.addEventListener("symptom-intake-updated", recover);
        return () => window.removeEventListener("symptom-intake-updated", recover);
    }, []);

    async function execute(operation: (signal: AbortSignal) => Promise<SymptomIntake>) {
        if (!token || busy || running.current) return;
        running.current = true;
        const request = new AbortController(); controller.current = request;
        let timedOut = false;
        const timer = setTimeout(() => { timedOut = true; request.abort(); }, 12000);
        setState({ scope, draft, error: null, busy: true });
        try {
            const result = await operation(request.signal);
            if (latest.current !== scope || request.signal.aborted) return;
            if (result.persistence_status !== "uncertain") { pending.current = null; setPendingScope(null); }
            setState({ scope, draft: result, error: null, busy: false });
            return result;
        } catch (failure) {
            if (latest.current !== scope || (request.signal.aborted && !timedOut)) return;
            const code = errorCode(failure, "INTAKE_PERSISTENCE_UNAVAILABLE");
            if (failure instanceof ApiClientError && failure.status < 500 && code !== "INTAKE_PERSISTENCE_UNAVAILABLE") {
                pending.current = null; setPendingScope(null);
            }
            setState({ scope, draft, error: code, busy: false });
        } finally { clearTimeout(timer); if (latest.current === scope) running.current = false; }
    }
    function mutate(action: string, payload: Record<string, unknown>) {
        if (!token || !draft || busy || running.current || pending.current) return;
        const request = { id: draft.intake_id, action, payload: { expected_revision: draft.revision, ...payload } };
        pending.current = request;
        setPendingScope(scope);
        void execute((signal) => mutateIntake(token, request.id, action, request.payload, signal));
    }
    async function reload() {
        if (!token) return;
        if (pending.current) {
            const request = pending.current;
            const recovered = await execute((signal) => fetchIntake(token, request.id, signal));
            // Recovery reads must not discard an uncertain mutation identity.
            if (latest.current === scope && (!recovered || ["collecting", "ready_for_confirmation"].includes(recovered.status))
                && !(request.action === "preview" && recovered?.preview)) { pending.current = request; setPendingScope(scope); }
        } else {
            setState((previous) => ({ ...previous, error: null, busy: true }));
            setSignal((n) => n + 1);
        }
    }
    function retry() {
        const request = pending.current;
        if (token && request) void execute((signal) => mutateIntake(token, request.id, request.action, request.payload, signal));
    }
    return { draft, busy, error, pending: pendingScope === scope, mutate, reload, retry,
        start: (source: string) => token && execute((signal) => startIntake(token, source, sessionId, signal)) };
}
