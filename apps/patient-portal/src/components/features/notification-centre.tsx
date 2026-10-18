"use client";

import Link from "next/link";
import { useState } from "react";
import { useNotifications, useOptionalNotifications } from "@/contexts/notifications-context";
import { getNotificationsCopy } from "@/content/notifications-copy";
import { notificationDestination } from "@/services/notifications";
import { Icon, type IconName } from "@/components/ui/icons";
import { Modal } from "@/components/ui/modal";

const button = "ma-press min-h-11 rounded-[14px] bg-surface-2 px-3 py-2 text-sm font-semibold text-ink-2 hover:bg-line-strong disabled:opacity-50";
// One tint per kind, so the list scans by type; tokens come from globals.css.
const categories: Record<string, { icon: IconName; tint: string }> = {
  messages: { icon: "chat", tint: "bg-brand-tint text-brand-ink" },
  documents: { icon: "file", tint: "bg-upload-tint text-upload-ink" },
  appointments: { icon: "cal", tint: "bg-note-tint text-note-ink" },
  reminders: { icon: "clock", tint: "bg-move-tint text-move-ink" },
  care_plans: { icon: "note", tint: "bg-med-tint text-med-ink" },
  safety: { icon: "alert", tint: "bg-danger-tint text-danger-ink" },
  follow_up: { icon: "history", tint: "bg-surface-2 text-ink-2" },
};
const iconButton = "ma-press flex h-11 w-11 shrink-0 items-center justify-center rounded-[14px] text-ink hover:bg-surface-2 disabled:text-muted disabled:opacity-60";

/** "now", "5 min", "3 h", then "Oct 9": the full date stays in the title and for screen readers. */
function shortTime(iso: string, locale: string, timezone: string | null): { short: string; full: string } | null {
  const when = Date.parse(iso);
  if (!timezone || !Number.isFinite(when)) return null;
  try {
    const full = new Intl.DateTimeFormat(locale, { timeZone: timezone, dateStyle: "medium", timeStyle: "short" }).format(new Date(when));
    const minutes = Math.round((Date.now() - when) / 60000);
    const relative = new Intl.RelativeTimeFormat(locale, { numeric: "auto", style: "narrow" });
    const short = minutes < 1 ? relative.format(0, "minute")
      : minutes < 60 ? relative.format(-minutes, "minute")
      : minutes < 24 * 60 ? relative.format(-Math.round(minutes / 60), "hour")
      : new Intl.DateTimeFormat(locale, { timeZone: timezone, month: "short", day: "numeric" }).format(new Date(when));
    return { short, full };
  } catch { return null; /* Missing/invalid saved timezone cannot establish a local clock. */ }
}

export function NotificationCentre({ onNavigate }: { onNavigate?: () => void }) {
  const state = useNotifications();
  const copy = getNotificationsCopy(state.locale);
  const unreadCount = state.summary?.unread_count ?? null;
  const canMarkAll = !state.busy && !state.loading && state.canMarkDisplayed && Boolean(state.page?.items.some((item) => !item.is_read));
  return <section className="space-y-3" lang={state.locale} aria-label={copy.title} aria-busy={state.loading}>
    <div className="flex items-center gap-1">
      <div className="flex gap-1 rounded-2xl bg-surface-2 p-1" role="group" aria-label={copy.title}>
        {[false, true].map((unread) => <button key={String(unread)} type="button" aria-pressed={state.unread === unread} aria-label={unread ? copy.unread : copy.all} disabled={state.busy} className={`ma-press inline-flex min-h-11 items-center gap-1.5 rounded-[12px] px-3.5 text-sm font-semibold disabled:opacity-50 ${state.unread === unread ? "bg-surface text-ink shadow-sm" : "text-ink-2"}`} onClick={() => state.setUnread(unread)}>
          {unread ? copy.unread : copy.all}
          {unread && unreadCount !== null && unreadCount > 0 && <span aria-hidden="true" className="rounded-full bg-brand px-1.5 font-mono text-[11px] leading-5 text-white">{unreadCount}</span>}
        </button>)}
      </div>
      <span className="flex-1" />
      <button className={iconButton} type="button" aria-label={copy.refresh} title={copy.refresh} disabled={state.busy || state.loading} onClick={() => void state.refresh()}><Icon name="refresh" className="h-5 w-5" /></button>
      <button className={iconButton} type="button" aria-label={copy.readAll} title={copy.readAll} disabled={!canMarkAll} onClick={() => void state.markAllRead()}><Icon name="check" className="h-5 w-5" /></button>
    </div>
    {/* Unknown is not zero: say so when the count could not be loaded. */}
    {state.summary === null && !state.loading && <p className="px-1 text-[13px] text-muted" role="status">{copy.unavailable}</p>}
    {state.summary !== null && <p className="sr-only" role="status">{copy.count(state.summary.unread_count)}</p>}
    {state.skipped > 0 && <p role="status" className="px-1 text-[13px] text-muted">{copy.skipped(state.skipped)}</p>}
    {state.error && <p role="alert" className="rounded-2xl bg-danger-tint p-3 text-sm text-danger-ink">{state.error === "write" ? copy.writeError : copy.loadError}</p>}
    {state.loading && !state.page && !state.error && <p role="status" className="px-1 text-sm text-muted">{copy.loading}</p>}
    {state.page?.items.length === 0 && !state.error && <p className="flex items-center gap-3 rounded-[22px] bg-surface p-5 text-sm text-muted"><Icon name="bell" className="h-5 w-5 shrink-0" />{state.unread ? copy.emptyUnread : copy.empty}</p>}
    {state.page && state.page.items.length > 0 && <ul className="divide-y divide-line overflow-hidden rounded-[22px] bg-surface">
      {state.page.items.map((item) => {
        const href = notificationDestination(item.action_url);
        const kind = item.event_type === "legacy_update" ? categories.follow_up : categories[item.category] ?? { icon: "bell" as IconName, tint: "bg-surface-2 text-ink-2" };
        const time = shortTime(item.created_at, state.locale, state.timezone);
        return <li key={item.id} className="flex gap-3 px-3.5 py-3">
          <span aria-hidden="true" className={`relative mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] ${kind.tint}`}>
            <Icon name={kind.icon} className="h-[18px] w-[18px]" />
          </span>
          <div className="min-w-0 flex-1 break-words [overflow-wrap:anywhere]">
            <div className="flex items-start gap-2">
              {!item.is_read && <span role="img" aria-label={copy.unread} className="mt-[7px] h-2 w-2 shrink-0 rounded-full bg-brand" />}
              <h2 className={`min-w-0 flex-1 text-[15px] leading-snug ${item.is_read ? "font-medium text-ink-2" : "font-semibold text-ink"}`}>{item.title}</h2>
            </div>
            {item.clinic_name && <p className="mt-0.5 break-words text-[13px] leading-snug text-muted">{item.clinic_name}</p>}
            {item.body && <p className="mt-0.5 line-clamp-2 whitespace-pre-wrap text-[13px] leading-snug text-muted">{item.body}</p>}
            {href && <Link prefetch={false} className="ma-press -mb-2 -ml-2 inline-flex min-h-11 items-center gap-1 rounded-xl px-2 text-[13px] font-semibold text-brand-ink hover:bg-brand-tint" href={href} onClick={() => { if (!item.is_read) void state.markRead(item.id); onNavigate?.(); }}>{item.action_label}<Icon name="chevron" className="h-3.5 w-3.5" /></Link>}
          </div>
          <div className="-mr-1.5 flex shrink-0 flex-col items-end">
            {time && <time dateTime={item.created_at} title={time.full} aria-label={time.full} className="pt-0.5 font-mono text-xs text-muted">{time.short}</time>}
            {!item.is_read && <button type="button" className={`${iconButton} -mb-1.5 text-muted`} disabled={state.busy || state.loading} aria-label={`${copy.read}: ${item.title}`} title={copy.read} onClick={() => void state.markRead(item.id)}><Icon name="check" className="h-[18px] w-[18px]" /></button>}
          </div>
        </li>;
      })}
    </ul>}
    {state.page?.next_cursor && <button type="button" className={`${button} w-full`} disabled={state.busy || state.loading} onClick={() => void state.loadMore()}>{copy.more}</button>}
    <p className="px-1 text-xs leading-relaxed text-muted">{copy.notice}</p>
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
      {summary === null ? <span aria-hidden="true" className="absolute -right-1 -top-1 flex h-[18px] min-w-[18px] items-center justify-center rounded-full border border-line-strong bg-surface px-1 font-mono text-[10px] text-muted">?</span> : summary.unread_count > 0 && <span aria-hidden="true" className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-danger-ink px-1.5 font-mono text-[11px] font-semibold leading-none text-white ring-2 ring-background">{summary.unread_count > 99 ? "99+" : summary.unread_count}</span>}
    </button>
    <Modal open={open} onClose={() => setOpen(false)} title={copy.title} closeLabel={copy.close}>
      <NotificationCentre onNavigate={() => setOpen(false)} />
      <Link className="ma-press mt-2 flex min-h-11 items-center justify-center gap-1 rounded-xl text-sm font-semibold text-brand-ink hover:bg-brand-tint" href="/notifications" prefetch={false} onClick={() => setOpen(false)}>{copy.full}<Icon name="chevron" className="h-4 w-4" /></Link>
    </Modal>
  </>;
}
