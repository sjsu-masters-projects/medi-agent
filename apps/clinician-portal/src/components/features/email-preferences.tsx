"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Badge, Button, Card, Input } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { CardHeader, cardFooterClass } from "@/components/features/settings-card";
import { api } from "@/services/api";
import { emailPreferenceCopy, verificationNotice, type EmailPreferenceKey, type EmailPreferenceState } from "../../../../../packages/shared/src/utils/email-preferences";

/** Settings card for optional email notices, matching the other General Profile cards. */
export function EmailPreferences({ token }: { token: string }) {
  const copy = emailPreferenceCopy["en-US"];
  const [account, setAccount] = useState<EmailPreferenceState | null>(null);
  const [draft, setDraft] = useState<Partial<Record<EmailPreferenceKey, boolean>>>({});
  const [code, setCode] = useState("");
  const [codeSent, setCodeSent] = useState(false);
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
    setAccount(null); setDraft({}); setCode(""); setCodeSent(false); setNotice(""); setError(false);
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
        setNotice(verificationNotice(copy, result.status));
        setCodeSent(true);
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
  function submitCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!busy && /^\d{6}$/.test(code)) void action("verify");
  }
  const keys: EmailPreferenceKey[] = ["messages", "appointments", "reviews"];
  const ready = account !== null && account.available !== false;
  const verified = ready && !account.synthetic && account.verified;
  const hint = !ready ? "" : account.synthetic ? copy.synthetic : verified ? copy.recoveryNote : codeSent ? copy.codeHelp : copy.unverifiedHelp;
  const chip = !ready ? undefined : account.synthetic
    ? <Badge variant="neutral">{copy.statusSynthetic}</Badge>
    : verified
      ? <Badge variant="success"><Icon name="check" className="h-3 w-3" />{copy.statusVerified}</Badge>
      : <Badge variant="warning">{copy.statusUnverified}</Badge>;
  return <Card padding="none">
    <section aria-labelledby="email-preferences-title" className="scroll-mt-24" id="email-notices">
      <CardHeader icon="mail" action={chip}>
        <h3 id="email-preferences-title" className="text-[15px] font-semibold text-ink">{copy.title}</h3>
      </CardHeader>
      <div className="divide-y divide-line">
        {!account && !error ? <p role="status" className="px-5 py-4 text-[13px] text-muted">{copy.loading}</p> : null}
        {account && account.available === false ? <p role="status" className="px-5 py-4 text-[13px] text-muted">{copy.notAvailable}</p> : null}
        {ready ? <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 px-5 py-4">
          <div className="min-w-0 flex-1 basis-56">
            <p className="truncate text-sm font-medium text-ink" title={account.email}>{account.email}</p>
            <p id="email-preferences-hint" className="mt-0.5 text-[13px] text-muted">{hint}</p>
          </div>
          {account.synthetic || verified ? null : codeSent
            ? <div className="flex flex-wrap items-center gap-2">
              <form className="flex items-center gap-2" onSubmit={submitCode}>
                <div className="w-36">
                  <Input aria-label={copy.code} aria-describedby="email-preferences-hint" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={event => setCode(event.target.value.replace(/\D/g, ""))} />
                </div>
                <Button type="submit" disabled={busy || !/^\d{6}$/.test(code)}>{copy.confirm}</Button>
              </form>
              <Button variant="ghost" disabled={busy} onClick={() => void action("request")}>{copy.resend}</Button>
            </div>
            : <Button variant="secondary" disabled={busy} onClick={() => void action("request")}>{copy.verify}</Button>}
        </div> : null}
        {verified ? <fieldset disabled={busy} className="m-0 min-w-0 border-0 p-0 [&>label+label]:border-t [&>label+label]:border-line">
          <legend className="sr-only">{copy.title}</legend>
          {keys.map(key => <label key={key} className="flex cursor-pointer items-center justify-between gap-4 px-5 py-3 text-sm text-ink">
            <span className="min-w-0">{copy[key]}</span>
            <input type="checkbox" className="h-4 w-4 shrink-0 accent-[var(--color-primary)]" checked={draft[key] ?? false} onChange={event => setDraft(current => ({ ...current, [key]: event.target.checked }))} />
          </label>)}
        </fieldset> : null}
        {error ? <div role="alert" className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
          <p className="text-[13px] font-medium text-risk-ink">{copy.unavailable}</p>
          <Button variant="secondary" onClick={() => void load()}>{copy.retry}</Button>
        </div> : null}
      </div>
      <div className={cardFooterClass}>
        <p className="mr-auto text-xs text-muted">{copy.privacy}</p>
        <p role="status" className={notice ? "text-[13px] text-ink-2" : ""}>{notice}</p>
        {verified ? <Button disabled={busy} onClick={() => void action("save")}>{busy ? copy.busy : copy.save}</Button> : null}
      </div>
    </section>
  </Card>;
}
