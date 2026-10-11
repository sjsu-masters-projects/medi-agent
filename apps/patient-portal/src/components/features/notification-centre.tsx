"use client";

import Link from "next/link";
import { useState } from "react";
import { useNotifications, useOptionalNotifications } from "@/contexts/notifications-context";
import { getNotificationsCopy } from "@/content/notifications-copy";
import { notificationDestination } from "@/services/notifications";
import { Icon, type IconName } from "@/components/ui/icons";
import { Modal } from "@/components/ui/modal";

const button = "ma-press min-h-11 rounded-[14px] bg-surface-2 px-3 py-2 text-sm font-semibold text-ink-2 hover:bg-line-strong disabled:opacity-50";
const categoryIcons: Record<string, IconName> = { messages: "chat", documents: "file", appointments: "cal", reminders: "clock", care_plans: "note", follow_up: "alert", safety: "alert" };

export function NotificationCentre({ onNavigate }: { onNavigate?: () => void }) {
  const state = useNotifications();
  const copy = getNotificationsCopy(state.locale);
  return <section className="space-y-3" lang={state.locale} aria-label={copy.title} aria-busy={state.loading}>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex gap-1 rounded-2xl bg-surface-2 p-1" role="group" aria-label={copy.title}>
        {[false, true].map((unread) => <button key={String(unread)} type="button" aria-pressed={state.unread === unread} disabled={state.busy} className={`${button} ${state.unread === unread ? "!bg-brand-tint !text-brand-ink" : ""}`} onClick={() => state.setUnread(unread)}>{unread ? copy.unread : copy.all}</button>)}
      </div>
      <button className={button} type="button" disabled={state.busy || state.loading} onClick={() => void state.refresh()}>{copy.refresh}</button>
    </div>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p className="text-sm text-muted" role="status">{state.summary ? copy.count(state.summary.unread_count) : copy.unavailable}</p>
      <button type="button" className={button} disabled={state.busy || state.loading || !state.canMarkDisplayed || !state.page?.items.some((item) => !item.is_read)} onClick={() => void state.markAllRead()}>{copy.readAll}</button>
    </div>
    {state.error && <p role="alert" className="rounded-2xl bg-danger-tint p-3 text-sm text-danger-ink">{state.error === "write" ? copy.writeError : copy.loadError}</p>}
    {state.loading && !state.page && !state.error && <p role="status" className="text-sm text-muted">{copy.loading}</p>}
    {state.page?.items.length === 0 && !state.error && <p className="rounded-[22px] bg-surface p-5 text-sm text-muted">{state.unread ? copy.emptyUnread : copy.empty}</p>}
    {state.page && <ul className="divide-y divide-line overflow-hidden rounded-[22px] bg-surface">
      {state.page.items.map((item) => {
        const href = notificationDestination(item.action_url);
        let date = "";
        if (state.timezone && Number.isFinite(Date.parse(item.created_at))) {
          try { date = new Intl.DateTimeFormat(state.locale, { timeZone: state.timezone, dateStyle: "medium", timeStyle: "short" }).format(new Date(item.created_at)); } catch { /* Missing/invalid saved timezone cannot establish a local clock. */ }
        }
        return <li key={item.id} className="space-y-2 px-4 py-3.5">
          <div className="flex items-start gap-2">
            <span aria-hidden="true" className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[13px] bg-surface-2 text-ink-2"><Icon name={categoryIcons[item.category] ?? "bell"} className="h-5 w-5" /></span>
            {!item.is_read && <span role="img" aria-label={copy.unread} className="mt-2 h-2 w-2 shrink-0 rounded-full bg-brand" />}
            <div className="min-w-0 flex-1 break-words [overflow-wrap:anywhere]">
              <h2 className="text-[15px] font-semibold text-ink">{item.title}</h2>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink-2">{item.body}</p>
              {date && <time dateTime={item.created_at} className="mt-1 block font-mono text-xs text-muted">{date}</time>}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {href && <Link prefetch={false} className={`${button} inline-flex items-center !bg-brand-tint !text-brand-ink`} href={href} onClick={() => { if (!item.is_read) void state.markRead(item.id); onNavigate?.(); }}>{item.action_label}</Link>}
            {!item.is_read && <button type="button" className={button} disabled={state.busy || state.loading} aria-label={`${copy.read}: ${item.title}`} onClick={() => void state.markRead(item.id)}>{copy.read}</button>}
          </div>
        </li>;
      })}
    </ul>}
    {state.page?.next_cursor && <button type="button" className={`${button} w-full`} disabled={state.busy || state.loading} onClick={() => void state.loadMore()}>{copy.more}</button>}
    <p className="text-[13px] leading-relaxed text-muted">{copy.notice}</p>
  </section>;
}

export function NotificationBell() {
  const state = useOptionalNotifications();
  const [open, setOpen] = useState(false);
  if (!state) return null;
  const { locale, summary } = state;
  const copy = getNotificationsCopy(locale);
  return <>
    <button type="button" className="ma-press relative flex h-11 w-11 items-center justify-center rounded-[14px] bg-surface text-ink-2 hover:bg-surface-2" aria-label={`${copy.title} · ${summary ? copy.count(summary.unread_count) : copy.unavailable}`} aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}>
      <Icon name="bell" className="h-5 w-5" />
      {summary === null ? <span aria-hidden="true" className="absolute right-0 top-0 rounded-full bg-surface-2 px-1.5 font-mono text-xs text-muted">?</span> : summary.unread_count > 0 && <span aria-hidden="true" className="absolute right-0 top-0 rounded-full bg-brand px-1.5 font-mono text-xs text-white">{summary.unread_count > 99 ? "99+" : summary.unread_count}</span>}
    </button>
    <Modal open={open} onClose={() => setOpen(false)} title={copy.title} closeLabel={copy.close}>
      <NotificationCentre onNavigate={() => setOpen(false)} />
      <Link className={`${button} mt-4 flex items-center justify-center !bg-brand !text-white`} href="/notifications" prefetch={false} onClick={() => setOpen(false)}>{copy.full}</Link>
    </Modal>
  </>;
}
