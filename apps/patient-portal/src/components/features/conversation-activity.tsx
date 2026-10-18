"use client";

import { useEffect, useState } from "react";
import { api } from "@/services/api";
import type { ConversationActivity } from "../../../../../packages/shared/src/types/care-conversations";

type Item = { id: string; title: string; frequency: string; is_removed: boolean; wording?: ConversationActivity["wording"] };

export function ConversationActivityAttachment(props: Parameters<typeof ConversationActivityPicker>[0]) {
  const [expanded, setExpanded] = useState(Boolean(props.value));
  return <div>
    <button className="min-h-11 px-2 text-sm font-semibold text-brand" type="button" disabled={props.disabled} aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>
      {props.locale === "es-MX" ? "Preguntar sobre una actividad del plan" : "Ask about a plan activity"}
    </button>
    {expanded ? <ConversationActivityPicker {...props} /> : null}
  </div>;
}

export function ConversationActivityPicker({ token, patientId, locale, value, disabled, onChange }: {
  token: string; patientId: string; locale: string; value?: string; disabled: boolean;
  onChange: (id: string | undefined) => void;
}) {
  const es = locale === "es-MX";
  const [items, setItems] = useState<Item[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    api.get<{ items: Item[] } | null>(`/api/v1/care-plans/patients/${encodeURIComponent(patientId)}`, { token, signal: controller.signal })
      .then((plan) => { if (!controller.signal.aborted) { setItems((plan?.items ?? []).filter((item) => !item.is_removed)); setStatus("ready"); } })
      .catch(() => { if (!controller.signal.aborted) setStatus("error"); });
    return () => controller.abort();
  }, [token, patientId, attempt]);
  return <div className="space-y-1.5 px-1 text-sm text-muted">
    <label className="block">
      {es ? "Actividad sobre la que preguntas (opcional)" : "Activity you are asking about (optional)"}
      <select className="mt-1 min-h-11 w-full rounded-xl border border-line-strong bg-surface px-3 text-ink" value={value ?? ""} disabled={disabled || status !== "ready"} onChange={(event) => onChange(event.target.value || undefined)}>
        <option value="">{status === "loading" ? (es ? "Cargando actividades…" : "Loading activities…") : (es ? "Sin actividad adjunta" : "No activity attached")}</option>
        {value && !items.some((item) => item.id === value) ? <option value={value}>{es ? "Actividad adjunta anteriormente" : "Previously attached activity"}</option> : null}
        {items.map((item) => <option key={item.id} value={item.id}>{item.wording?.[locale]?.title ?? item.title}</option>)}
      </select>
    </label>
    {status === "error" ? <p role="alert">{es ? "No se pudieron cargar las actividades." : "Activities could not be loaded."} <button className="min-h-11 px-2 font-semibold text-brand" type="button" disabled={disabled} onClick={() => { setStatus("loading"); setAttempt((n) => n + 1); }}>{es ? "Reintentar actividades" : "Retry loading activities"}</button></p> : null}
    {value ? <p>{es ? "Tu mensaje no cambia el plan ni los recordatorios. Tu equipo debe revisar y aprobar cualquier cambio." : "Your message does not change the plan or reminders. Your care team must review and approve any change."}</p> : null}
  </div>;
}

export function ConversationActivityContext({ activity, locale }: { activity: ConversationActivity; locale: string }) {
  const wording = activity.wording?.[locale];
  return <div className="max-w-full rounded-xl border border-line-strong bg-surface px-3 py-2 text-sm text-ink-2">
    <p className="text-xs text-muted">{locale === "es-MX" ? "Actividad del plan adjunta" : "Attached plan activity"}</p>
    <p className="break-words font-semibold">{wording?.title ?? activity.title}</p>
    <p>{wording?.frequency ?? activity.frequency}</p>
    {!activity.current ? <p className="text-muted">{locale === "es-MX" ? "Esta actividad ya no pertenece al plan actual." : "This activity is no longer part of the current plan."}</p> : null}
  </div>;
}
