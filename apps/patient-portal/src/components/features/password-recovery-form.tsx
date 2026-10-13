"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api } from "@/services/api";
import { createRecoveryClient } from "@/services/password-recovery";
import {
    readRecoveryTokenHash,
    readRecoveryTokens,
    recoveryCopy,
    withoutRecoveryQuery,
} from "../../../../../packages/shared/src/utils/password-recovery";

type Client = NonNullable<ReturnType<typeof createRecoveryClient>>;
type State = "checking" | "confirm" | "ready" | "invalid" | "unavailable" | "success";
type Recovery = { client: Client | null; state: State };

export function PasswordRecoveryForm({ mode, locale = "en-US", portal }: {
    mode: "request" | "reset";
    locale?: string;
    portal: "patient" | "clinician";
}) {
    const copy = recoveryCopy(locale);
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [confirm, setConfirm] = useState("");
    const [sent, setSent] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [state, setState] = useState<State>("checking");
    const recovery = useRef<Promise<Recovery> | null>(null);
    const tokenHash = useRef<string | null>(null);
    const started = useRef(false);
    const client = useRef<Client | null>(null);
    const statusRef = useRef<HTMLParagraphElement | null>(null);
    const statusVisible = (mode === "request" && sent) ||
        (mode === "reset" && state !== "ready" && state !== "checking" && state !== "confirm");

    // The form is replaced by a status message; move focus there so it is announced
    // and keyboard users are not left on a removed control.
    useEffect(() => {
        if (statusVisible) statusRef.current?.focus();
    }, [statusVisible]);

    useEffect(() => {
        if (mode !== "reset") return;
        let active = true;
        if (!started.current) {
            started.current = true;
            const tokens = readRecoveryTokens(window.location.hash);
            tokenHash.current = readRecoveryTokenHash(window.location.search);
            // Do this before SDK/network work: secrets must not remain in browser history.
            window.history.replaceState(null, "", window.location.pathname + withoutRecoveryQuery(window.location.search));
            // A query token is redeemed only after an explicit click (see `redeem`), so a
            // mail scanner opening the link cannot consume it. Older links use the fragment.
            if (!tokenHash.current) recovery.current = (async (): Promise<Recovery> => {
                if (!tokens) return { client: null, state: "invalid" };
                const auth = createRecoveryClient();
                if (!auth) return { client: null, state: "unavailable" };
                try {
                    const session = await auth.auth.setSession(tokens);
                    if (session.error || !session.data.session) return { client: null, state: "invalid" };
                    const user = await auth.auth.getUser();
                    if (user.error || !user.data.user) return { client: null, state: "invalid" };
                    return { client: auth, state: "ready" };
                } catch {
                    return { client: null, state: "invalid" };
                }
            })();
        }
        if (!recovery.current) setState("confirm");
        else void recovery.current.then((result) => {
            if (active) { client.current = result.client; setState(result.state); }
        });
        return () => { active = false; };
    }, [mode]);

    function redeem() {
        const token_hash = tokenHash.current;
        if (recovery.current || !token_hash) return;
        tokenHash.current = null;
        setState("checking");
        recovery.current = (async (): Promise<Recovery> => {
            const auth = createRecoveryClient();
            if (!auth) return { client: null, state: "unavailable" };
            try {
                const result = await auth.auth.verifyOtp({ token_hash, type: "recovery" });
                if (result.error || !result.data.session) return { client: null, state: "invalid" };
                return { client: auth, state: "ready" };
            } catch {
                return { client: null, state: "invalid" };
            }
        })();
        void recovery.current.then((result) => { client.current = result.client; setState(result.state); });
    }

    async function submit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (busy) return;
        setError("");
        if (mode === "reset" && (password !== confirm || password.length < 8 || password.length > 128)) {
            setError(copy.mismatch); return;
        }
        setBusy(true);
        try {
            if (mode === "request") {
                await api.post("/api/v1/auth/password-reset", { email, portal, locale });
                setSent(true);
            } else {
                if (state !== "ready" || !client.current) { setState("invalid"); return; }
                const result = await client.current.auth.updateUser({ password });
                if (result.error) { setError(copy.failure); return; }
                setPassword(""); setConfirm(""); setState("success");
                // End every session for this account, including this recovery one, so a
                // stolen session cannot outlive the reset. Normal login (and MFA) follows.
                await client.current.auth.signOut({ scope: "global" }).catch(() => undefined);
                client.current = null;
                recovery.current = null;
            }
        } catch {
            setError(copy.failure);
        } finally {
            setBusy(false);
        }
    }

    const action = portal === "patient" ? "bg-brand hover:bg-brand-hover" : "bg-primary hover:bg-primary-hover";
    const input = "mt-2 min-h-12 w-full rounded-xl border border-line-strong bg-surface px-4 text-base text-ink";
    const link = portal === "patient" ? "text-brand" : "text-primary";
    const resetReady = mode === "reset" && state === "ready";
    const errorId = `${portal}-recovery-error`;
    return <section className="space-y-6" lang={locale}>
        <header>
            <h1 className="text-2xl font-semibold text-ink">{mode === "request" ? copy.forgot : copy.reset}</h1>
            <p className="mt-2 text-sm leading-relaxed text-muted">{mode === "request" ? copy.intro : copy.resetIntro}</p>
        </header>
        {mode === "request" && sent ? <p ref={statusRef} tabIndex={-1} role="status" className="rounded-xl bg-surface-2 p-4 text-ink-2 outline-none">{copy.sent}</p> : null}
        {mode === "reset" && state === "confirm" ?
            <button className={`min-h-12 w-full rounded-xl px-4 font-semibold text-white ${action}`} type="button" onClick={redeem}>{copy.continue}</button> : null}
        {mode === "reset" && state !== "ready" && state !== "confirm" ? <p ref={statusRef} tabIndex={-1} role="status" className="rounded-xl bg-surface-2 p-4 text-ink-2 outline-none">{copy[state]}</p> : null}
        {(mode === "request" && !sent) || resetReady ? <form onSubmit={submit} className="space-y-5">
            {mode === "request" ? <label className="block text-sm font-medium text-ink-2">
                {copy.email}<input autoComplete="email" aria-describedby={error ? errorId : undefined} aria-invalid={error ? true : undefined} className={input} type="email" required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} />
            </label> : <>
                <label className="block text-sm font-medium text-ink-2">{copy.password}
                    <input autoComplete="new-password" aria-describedby={error ? errorId : undefined} aria-invalid={error ? true : undefined} className={input} type="password" required minLength={8} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} />
                </label>
                <label className="block text-sm font-medium text-ink-2">{copy.confirm}
                    <input autoComplete="new-password" aria-describedby={error ? errorId : undefined} aria-invalid={error ? true : undefined} className={input} type="password" required minLength={8} maxLength={128} value={confirm} onChange={(event) => setConfirm(event.target.value)} />
                </label>
            </>}
            {error ? <p id={errorId} role="alert" className="text-sm text-ink">{error}</p> : null}
            <button className={`min-h-12 w-full rounded-xl px-4 font-semibold text-white disabled:opacity-50 ${action}`} disabled={busy} type="submit">
                {mode === "request" ? busy ? copy.sending : copy.send : busy ? copy.saving : copy.save}
            </button>
        </form> : null}
        {mode === "reset" && (state === "invalid" || state === "unavailable") ?
            <Link className={`inline-flex min-h-11 items-center font-semibold ${link}`} href={`/forgot-password?lang=${locale}`}>{copy.retry}</Link> : null}
        <Link className={`flex min-h-11 items-center text-sm font-medium ${link}`} href={`/login?lang=${locale}`}>{copy.back}</Link>
    </section>;
}
