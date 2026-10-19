"use client";

import { useEffect, useId, useState } from "react";
import { api } from "@/services/api";
import type { Locale } from "@/types";
import type { ConversationActivity } from "../../../../../packages/shared/src/types/care-conversations";
import { getConversationCopy } from "../../../../../packages/shared/src/utils/care-conversations";

type Item = { id: string; title: string; frequency: string; is_removed: boolean; wording?: ConversationActivity["wording"] };
type ActivityPickerProps = {
  token: string;
  patientId: string;
  locale: Locale;
  value?: string;
  disabled: boolean;
  onChange: (id: string | undefined) => void;
  onSelectedLabelChange?: (label: string | null) => void;
  showExplanation?: boolean;
};

export function ConversationActivityAttachment(props: ActivityPickerProps) {
  const [expanded, setExpanded] = useState(Boolean(props.value));
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null);
  const pickerId = useId();
  const copy = getConversationCopy(props.locale);
  const buttonLabel = props.value
    ? copy.activityAttachedButton(selectedLabel ?? copy.activityPreviouslyAttached)
    : copy.activityAsk;
  return <div className="space-y-1.5">
    <button className="min-h-11 max-w-full px-2 text-left text-sm font-semibold text-brand" type="button" disabled={props.disabled} aria-controls={pickerId} aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>
      {buttonLabel}
    </button>
    <p className="px-2 text-xs leading-relaxed text-muted">{copy.activityExplanation}</p>
    {props.disabled ? <p className="px-2 text-xs leading-relaxed text-muted">{copy.activityLocked}</p> : null}
    {expanded ? <div id={pickerId}><ConversationActivityPicker {...props} onSelectedLabelChange={setSelectedLabel} showExplanation={false} /></div> : null}
  </div>;
}

export function ConversationActivityPicker({ token, patientId, locale, value, disabled, onChange, onSelectedLabelChange, showExplanation = true }: ActivityPickerProps) {
  const copy = getConversationCopy(locale);
  const [items, setItems] = useState<Item[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api.get<{ items: Item[] } | null>(`/api/v1/care-plans/patients/${encodeURIComponent(patientId)}`, { token, signal: controller.signal })
      .then((plan) => {
        if (controller.signal.aborted) return;
        const available = (plan?.items ?? []).filter((item) => !item.is_removed);
        setItems(available);
        const selected = available.find((item) => item.id === value);
        onSelectedLabelChange?.(selected ? selected.wording?.[locale]?.title ?? selected.title : null);
        setStatus("ready");
      })
      .catch(() => { if (!controller.signal.aborted) setStatus("error"); });
    return () => controller.abort();
  }, [token, patientId, locale, value, attempt, onSelectedLabelChange]);
  const previousAttachment = Boolean(value && !items.some((item) => item.id === value));
  return <div className="space-y-1.5 px-1 text-sm text-muted">
    <label className="block">
      {copy.activityLabel}
      <select className="mt-1 min-h-11 w-full rounded-xl border border-line-strong bg-surface px-3 text-ink" value={value ?? ""} disabled={disabled || status !== "ready"} onChange={(event) => onChange(event.target.value || undefined)}>
        <option value="">{status === "loading" ? copy.activityLoading : copy.activityNone}</option>
        {previousAttachment ? <option value={value}>{copy.activityPreviouslyAttached}</option> : null}
        {items.map((item) => <option key={item.id} value={item.id}>{item.wording?.[locale]?.title ?? item.title}</option>)}
      </select>
    </label>
    <p aria-live="polite" className="sr-only" role="status">
      {status === "loading" ? copy.activityLoading : previousAttachment ? copy.activityPreviouslyAttached : ""}
    </p>
    {status === "error" ? <p role="alert">{copy.activityLoadError} <button className="min-h-11 px-2 font-semibold text-brand" type="button" disabled={disabled} onClick={() => { setStatus("loading"); setAttempt((n) => n + 1); }}>{copy.activityRetry}</button></p> : null}
    {showExplanation ? <p>{copy.activityExplanation}</p> : null}
    {disabled ? <p>{copy.activityLocked}</p> : null}
  </div>;
}

export function ConversationActivityContext({ activity, locale }: { activity: ConversationActivity; locale: Locale }) {
  const copy = getConversationCopy(locale);
  const wording = activity.wording?.[locale];
  return <div className="max-w-full rounded-xl border border-line-strong bg-surface px-3 py-2 text-sm text-ink-2">
    <p className="text-xs text-muted">{copy.activityAttached}</p>
    <p className="break-words font-semibold">{wording?.title ?? activity.title}</p>
    <p>{wording?.frequency ?? activity.frequency}</p>
    {!activity.current ? <p className="text-muted">{copy.activityNotCurrent}</p> : null}
  </div>;
}
