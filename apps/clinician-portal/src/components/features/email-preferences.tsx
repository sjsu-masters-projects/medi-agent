"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button, Input } from "@/components/ui";
import { api } from "@/services/api";
import { emailPreferenceCopy, type EmailPreferenceKey, type EmailPreferenceState } from "../../../../../packages/shared/src/utils/email-preferences";

export function EmailPreferences({ token }: { token: string }) {
  const copy = emailPreferenceCopy["en-US"];
  const [account, setAccount] = useState<EmailPreferenceState | null>(null);
  const [draft, setDraft] = useState<Partial<Record<EmailPreferenceKey, boolean>>>({});
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const [notice, setNotice] = useState("");
  const generation = useRef(0);
  const load = useCallback(async () => {
    const current = generation.current;
    setError(false);
    try {
      const value = await api.get<EmailPreferenceState>("/api/v1/email/preferences", { token });
      if (current !== generation.current) return;
      setAccount(value); setDraft(value.preferences);
    } catch { if (current === generation.current) setError(true); }
  }, [token]);
  useEffect(() => { let active = true;
    generation.current += 1;
    setBusy(false);
    setAccount(null); setDraft({}); setCode(""); setNotice(""); setError(false);
    api.get<EmailPreferenceState>("/api/v1/email/preferences", { token })
      .then(value => { if (active) { setAccount(value); setDraft(value.preferences); } })
      .catch(() => { if (active) setError(true); });
    return () => { active = false; generation.current += 1; };
  }, [token]);
  async function action(kind: "request" | "verify" | "save") {
    const current = generation.current;
    setBusy(true); setError(false); setNotice("");
    try {
      if (kind === "request") {
        const result = await api.post<{ status: string }>("/api/v1/email/verify/request", {}, { token });
        if (current !== generation.current) return;
        setNotice(result.status === "wait" ? copy.wait : result.status === "synthetic" ? copy.synthetic : copy.queued);
      } else if (kind === "verify") {
        const result = await api.post<{ verified: boolean }>("/api/v1/email/verify", { code }, { token });
        if (current !== generation.current) return;
        setNotice(result.verified ? copy.verified : copy.invalid);
        if (result.verified) { setCode(""); await load(); }
      } else {
        const result = await api.put<EmailPreferenceState>("/api/v1/email/preferences", draft, { token });
        if (current !== generation.current) return;
        setAccount(result); setDraft(result.preferences); setNotice(copy.saved);
      }
    } catch { if (current === generation.current) setError(true); }
    finally { if (current === generation.current) setBusy(false); }
  }
  const keys: EmailPreferenceKey[] = ["messages", "appointments", "reviews"];
  return <section aria-labelledby="email-preferences-title" className="space-y-4 rounded-[22px] border border-line-strong bg-surface p-5">
    <h3 id="email-preferences-title" className="text-base font-semibold text-ink">{copy.title}</h3>
    <p className="text-sm leading-relaxed text-muted">{copy.help}</p>
    {error ? <div role="alert" className="space-y-2"><p>{copy.unavailable}</p><Button variant="secondary" onClick={() => void load()}>{copy.retry}</Button></div> : null}
    {!account && !error ? <p role="status">{copy.loading}</p> : null}
    {account ? <>
      <p className="break-all text-sm text-ink-2">{account.email}</p>
      {account.synthetic ? <p className="text-sm text-muted">{copy.synthetic}</p> : account.verified ? <>
        <p className="text-sm font-medium text-ok-ink">{copy.verified}</p>
        <fieldset disabled={busy} className="space-y-1">
          <legend className="sr-only">{copy.title}</legend>
          {keys.map(key => <label key={key} className="flex min-h-11 cursor-pointer items-center gap-3 text-sm text-ink">
            <input type="checkbox" checked={draft[key] ?? false} onChange={event => setDraft(current => ({ ...current, [key]: event.target.checked }))} />
            <span>{copy[key]}</span>
          </label>)}
        </fieldset>
        <Button disabled={busy} onClick={() => void action("save")}>{busy ? copy.busy : copy.save}</Button>
      </> : <div className="space-y-3">
        <Button disabled={busy} variant="secondary" onClick={() => void action("request")}>{copy.verify}</Button>
        <Input label={copy.code} inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={event => setCode(event.target.value.replace(/\D/g, ""))} />
        <Button disabled={busy || !/^\d{6}$/.test(code)} onClick={() => void action("verify")}>{copy.confirm}</Button>
      </div>}
    </> : null}
    {notice ? <p role="status" className="text-sm text-ink-2">{notice}</p> : null}
    <p className="text-xs leading-relaxed text-muted">{copy.privacy}</p>
  </section>;
}
