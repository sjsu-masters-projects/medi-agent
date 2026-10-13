"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Button, Input } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { GroupedList, IconTile, SectionLabel } from "@/components/ui/list";
import { api } from "@/services/api";
import { emailPreferenceCopy, verificationNotice, type EmailPreferenceKey, type EmailPreferenceState } from "../../../../../packages/shared/src/utils/email-preferences";

const chipBase = "inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold";

/** Profile section for optional email notices: one inset card in the same style as the other Profile groups. */
export function EmailPreferences({ token, locale = "en-US" }: { token: string; locale?: "en-US" | "es-MX" }) {
  const copy = emailPreferenceCopy[locale];
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
  const keys: EmailPreferenceKey[] = ["messages", "appointments", "care_plans", "records"];
  const ready = account !== null && account.available !== false;
  const verified = ready && !account.synthetic && account.verified;
  const hint = !ready ? "" : account.synthetic ? copy.synthetic : verified ? copy.recoveryNote : codeSent ? copy.codeHelp : copy.unverifiedHelp;
  const chip = !ready ? null : account.synthetic
    ? <span className={`${chipBase} bg-surface-2 text-ink-2`}>{copy.statusSynthetic}</span>
    : verified
      ? <span className={`${chipBase} bg-brand-tint text-brand-ink`}><Icon name="check" className="h-3 w-3" />{copy.statusVerified}</span>
      : <span className={`${chipBase} bg-note-tint text-note-ink`}>{copy.statusUnverified}</span>;
  return <section aria-labelledby="email-preferences-title">
    <SectionLabel as="h3" id="email-preferences-title">{copy.title}</SectionLabel>
    <GroupedList as="div">
      {!account && !error ? <p role="status" className="px-4 py-3 text-[13px] text-muted">{copy.loading}</p> : null}
      {account && account.available === false ? <div className="flex items-center gap-3 px-[14px] py-3">
        <IconTile icon="mail" tone="neutral" />
        <p role="status" className="min-w-0 flex-1 break-words text-[13px] text-muted">{copy.notAvailable}</p>
      </div> : null}
      {ready ? <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-3 px-[14px] py-3">
        <IconTile icon="mail" tone={verified ? "brand" : "neutral"} className="row-span-2" />
        <p className="truncate text-[15px] font-semibold text-ink" title={account.email}>{account.email}</p>
        {chip}
        <p id="email-preferences-hint" className="col-span-2 col-start-2 mt-0.5 break-words text-[13px] text-muted">{hint}</p>
      </div> : null}
      {verified ? <fieldset disabled={busy} className="m-0 min-w-0 border-0 p-0 [&>label+label]:border-t [&>label+label]:border-line">
        <legend className="sr-only">{copy.title}</legend>
        {keys.map(key => <label key={key} className="flex min-h-[52px] cursor-pointer items-center justify-between gap-3 px-4 py-3">
          <span className="min-w-0 break-words text-[15px] text-ink">{copy[key]}</span>
          <input type="checkbox" className="h-5 w-5 shrink-0 accent-brand" checked={draft[key] ?? false} onChange={event => setDraft(current => ({ ...current, [key]: event.target.checked }))} />
        </label>)}
      </fieldset> : null}
      {error ? <div role="alert" className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-4 py-3">
        <p className="min-w-0 flex-1 break-words text-[13px] font-medium text-danger-ink">{copy.unavailable}</p>
        <Button size="sm" variant="secondary" onClick={() => void load()}>{copy.retry}</Button>
      </div> : null}
      {ready && !account.synthetic ? <div className="px-4 py-3">
        {verified ? <Button size="sm" disabled={busy} onClick={() => void action("save")}>{busy ? copy.busy : copy.save}</Button>
          : codeSent ? <div className="space-y-1">
            <form className="flex gap-2" onSubmit={submitCode}>
              <div className="min-w-0 flex-1">
                <Input aria-label={copy.code} aria-describedby="email-preferences-hint" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={event => setCode(event.target.value.replace(/\D/g, ""))} />
              </div>
              <Button type="submit" disabled={busy || !/^\d{6}$/.test(code)}>{copy.confirm}</Button>
            </form>
            <Button size="sm" variant="ghost" className="-ml-3.5" disabled={busy} onClick={() => void action("request")}>{copy.resend}</Button>
          </div>
          : <Button size="sm" variant="secondary" disabled={busy} onClick={() => void action("request")}>{copy.verify}</Button>}
        <p role="status" className={notice ? "mt-2 break-words text-[13px] text-ink-2" : ""}>{notice}</p>
      </div> : null}
    </GroupedList>
    <p className="px-[22px] pt-2 text-[13px] leading-relaxed text-muted">{copy.privacy}</p>
  </section>;
}
