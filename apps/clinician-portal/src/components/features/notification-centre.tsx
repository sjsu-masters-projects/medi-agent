"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Icon, type IconName } from "@/components/ui/icons";
import { useNotificationCentre } from "@/components/features/notification-provider";
import { notificationTarget } from "@/services/notification-centre";
import type { CentreItem, NotificationCategory } from "@/types/notification-centre";

const categories: Record<NotificationCategory, string> = {
  documents: "Documents", care_plans: "Care plans", appointments: "Appointments",
  follow_up: "Follow-up", safety: "Safety", messages: "Messages", reminders: "Reminders",
};
const kinds: Record<NotificationCategory, { icon: IconName; tint: string }> = {
  documents: { icon: "file", tint: "bg-primary-tint text-primary" },
  care_plans: { icon: "note", tint: "bg-ok-tint text-ok-ink" },
  appointments: { icon: "cal", tint: "bg-primary-tint text-primary" },
  follow_up: { icon: "alert", tint: "bg-warn-tint text-warn-ink" },
  safety: { icon: "shield", tint: "bg-risk-tint text-risk-ink" },
  messages: { icon: "chat", tint: "bg-surface-2 text-ink-2" },
  reminders: { icon: "clock", tint: "bg-surface-2 text-ink-2" },
};

/** "5m ago", "3h ago", then "Oct 9"; the full date stays in the tooltip and accessible name. */
function shortTime(iso: string): { short: string; full: string } | null {
  const when = Date.parse(iso);
  if (!Number.isFinite(when)) return null;
  const full = new Date(when).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });
  const minutes = Math.round((Date.now() - when) / 60000);
  const relative = new Intl.RelativeTimeFormat("en-US", { numeric: "auto", style: "narrow" });
  const short = minutes < 1 ? relative.format(0, "minute")
    : minutes < 60 ? relative.format(-minutes, "minute")
    : minutes < 24 * 60 ? relative.format(-Math.round(minutes / 60), "hour")
    : new Date(when).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  return { short, full };
}

function NotificationRows({ items, onNavigate, allowAcknowledge, allowRead, onAcknowledged }: { items: CentreItem[]; onNavigate?: () => void; allowAcknowledge: boolean; allowRead: boolean; onAcknowledged: () => void }) {
  const centre = useNotificationCentre();
  const [acknowledging, setAcknowledging] = useState<CentreItem | null>(null);
  const [note, setNote] = useState("");
  const targetItem = acknowledging && centre.actions.data?.items.find((item) => item.id === acknowledging.id && item.can_acknowledge);
  return <>
    <ul className="divide-y divide-line">
      {items.map((item) => {
        const target = notificationTarget(item.action_url);
        const kind = item.event_type === "legacy_update" ? { icon: "history" as IconName, tint: "bg-surface-2 text-ink-2" } : kinds[item.category] ?? { icon: "bell" as IconName, tint: "bg-surface-2 text-ink-2" };
        const time = shortTime(item.created_at);
        const context = [item.patient_name, item.clinic_name].filter(Boolean).join(" · ");
        return <li key={item.id} className="flex gap-3 px-4 py-3">
          <span aria-hidden="true" className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${kind.tint}`}><Icon name={kind.icon} className="h-[18px] w-[18px]" /></span>
          <div className="min-w-0 flex-1 [overflow-wrap:anywhere]">
            <div className="flex items-start gap-2">
              {!item.is_read && <span role="img" aria-label="Unread" className="mt-[7px] h-2 w-2 shrink-0 rounded-full bg-primary" />}
              <h3 className={`min-w-0 flex-1 text-sm leading-snug ${item.is_read ? "font-medium text-ink-2" : "font-semibold text-ink"}`}><span className="sr-only">{categories[item.category] ?? item.category}: </span>{item.title}</h3>
              {time && <time dateTime={item.created_at} title={time.full} aria-label={time.full} className="shrink-0 pt-0.5 font-mono text-xs text-muted">{time.short}</time>}
            </div>
            {context && <p className="mt-0.5 truncate text-xs text-muted">{context}</p>}
            <p className="mt-1 line-clamp-2 whitespace-pre-wrap text-[13px] leading-snug text-ink-2">{item.body}</p>
            {(target || (allowRead && !item.is_read) || (allowAcknowledge && item.can_acknowledge)) && <div className="-ml-2 mt-1.5 flex flex-wrap items-center gap-1">
              {target && <Link href={target} onClick={() => { if (!item.is_read) void centre.read(item.id); onNavigate?.(); }} className="inline-flex min-h-8 items-center gap-0.5 rounded-lg px-2 text-[13px] font-medium text-primary hover:bg-primary-tint">{item.action_label || "Open details"}<Icon name="chevron" className="h-3.5 w-3.5" /></Link>}
              {allowAcknowledge && item.can_acknowledge && <Button variant="secondary" disabled={centre.busy || !!centre.actions.error} onClick={() => { setNote(""); setAcknowledging(item); }}>Acknowledge</Button>}
              {allowRead && !item.is_read && <button type="button" disabled={centre.busy} onClick={() => void centre.read(item.id)} aria-label={`Mark read: ${item.title}`} title="Mark read" className="ma-press ml-auto flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-surface-2 hover:text-ink disabled:opacity-50"><Icon name="check" className="h-4 w-4" /></button>}
            </div>}
          </div>
        </li>;
      })}
    </ul>
    <Modal open={!!acknowledging} onClose={() => { if (!centre.busy) setAcknowledging(null); }} title="Acknowledge follow-up">
      <p className="text-sm text-ink-2">This records an audited acknowledgement. It does not approve care or resolve a clinical concern.</p>
      <label className="mt-4 block text-sm font-medium text-ink">Optional note
        <textarea maxLength={1000} value={note} disabled={centre.busy} onChange={(event) => setNote(event.target.value)} className="mt-2 min-h-24 w-full rounded-lg border border-line-strong bg-surface p-3 font-normal" />
      </label>
      {!targetItem && <p role="alert" className="mt-3 text-sm text-risk-ink">This item is no longer available for acknowledgement. Refresh Alerts.</p>}
      {centre.writeError && <p role="alert" className="mt-3 text-sm text-risk-ink">{centre.writeError}</p>}
      <div className="mt-4 flex flex-wrap justify-end gap-2">
        <Button variant="secondary" disabled={centre.busy} onClick={() => setAcknowledging(null)}>Cancel</Button>
        <Button disabled={centre.busy || !targetItem || !!centre.actions.error} onClick={async () => {
          if (targetItem && await centre.acknowledge(targetItem, note.trim() || undefined)) {
            setAcknowledging(null);
            window.requestAnimationFrame(onAcknowledged);
          }
        }}>Record acknowledgement</Button>
      </div>
    </Modal>
  </>;
}

export function NotificationList({ actions = false, compact = false, onNavigate }: { actions?: boolean; compact?: boolean; onNavigate?: () => void }) {
  const centre = useNotificationCentre();
  const [unread, setUnread] = useState(false);
  const [category, setCategory] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const listRef = useRef<HTMLElement>(null);
  const feed = actions ? "actions" : "history";
  const resource = centre[feed];
  const selectedCategory = actions ? centre.actionsCategory : category;
  const items = resource.data?.items.filter((item) => (!unread || !item.is_read) && (!selectedCategory || item.category === selectedCategory)) ?? [];
  return <section ref={listRef} aria-label={actions ? "Needs attention" : "Notification history"} className="overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        {!actions && <div role="group" aria-label="Notification filter" className="flex gap-1 rounded-lg bg-surface-2 p-1">
          {[false, true].map((value) => <button key={String(value)} type="button" aria-pressed={unread === value} onClick={() => setUnread(value)} className={`min-h-8 rounded-md px-3 text-sm ${unread === value ? "bg-surface font-medium text-ink shadow-sm" : "text-muted"}`}>{value ? "Unread" : "All"}</button>)}
        </div>}
        {!compact && <label className="flex flex-wrap items-center gap-2 text-sm text-ink-2">Category
          <select disabled={centre.busy} value={selectedCategory} onChange={(event) => { if (actions) centre.filterActions(event.target.value as NotificationCategory | ""); else setCategory(event.target.value); }} className="min-h-9 rounded-lg border border-line-strong bg-surface px-2">
            <option value="">All categories</option>
            {Object.entries(categories).filter(([key]) => !actions || !["messages", "reminders"].includes(key)).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select>
        </label>}
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" aria-label="Refresh" title="Refresh" disabled={centre.busy} onClick={() => void centre.refresh()} className="ma-press flex h-9 w-9 items-center justify-center rounded-lg border border-line text-ink-2 hover:bg-surface-2 disabled:opacity-50"><Icon name="refresh" className="h-4 w-4" /></button>
        {!actions && <Button variant="secondary" disabled={centre.busy || !resource.data?.read_snapshots?.length || !!resource.error} onClick={() => void centre.readAll()}>Mark all loaded read</Button>}
      </div>
    </div>
    {(resource.error || centre.writeError) && <p role="alert" className="border-b border-line px-4 py-3 text-sm text-risk-ink">{resource.error || centre.writeError}</p>}
    {acknowledged && <p role="status" className="px-4 py-2 text-sm text-ok-ink">Acknowledgement recorded. Clinical review and resolution remain separate.</p>}
    {!resource.data && !resource.error && <p role="status" className="p-5 text-sm text-muted">Loading alerts…</p>}
    {resource.data && !items.length && <p className="p-5 text-sm text-muted">{actions ? "No items need attention in this view." : "No notifications in this view."}</p>}
    {!actions && (category || unread) && <p className="px-4 py-2 text-xs text-muted">Mark all loaded read includes all categories in the loaded pages.{resource.data?.next_cursor ? " Load more to include earlier history." : ""}</p>}
    <NotificationRows items={items} onNavigate={onNavigate} allowAcknowledge={actions} allowRead={!actions} onAcknowledged={() => { setAcknowledged(true); listRef.current?.querySelector<HTMLButtonElement>("button")?.focus(); }} />
    {resource.data?.next_cursor && <div className="border-t border-line p-3"><Button variant="secondary" disabled={centre.busy} onClick={() => void centre.more(feed)}>Load more</Button></div>}
  </section>;
}

export function NotificationBell() {
  const centre = useNotificationCentre();
  const [open, setOpen] = useState(false);
  const summary = centre.summary.data;
  const unavailable = !!centre.summary.error || !summary;
  return <>
    <button type="button" aria-label={`Open notifications${unavailable ? ": count unavailable" : `: ${summary.unread_count} unread`}`} aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)} className="ma-press relative flex h-10 min-w-10 items-center justify-center gap-1 rounded-lg border border-line-strong px-2 text-ink-2 hover:bg-surface-2">
      <Icon name="bell" className="h-5 w-5" />
      <span className="font-mono text-xs">{unavailable ? "—" : summary.unread_count || null}</span>
    </button>
    <Modal open={open} onClose={() => setOpen(false)} title="Notifications" contentClassName="sm:!max-w-xl !pb-[calc(env(safe-area-inset-bottom)+1.25rem)]">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-sm">
        <p className="text-muted">{unavailable ? "Notification counts unavailable" : `${summary.unread_count} unread · ${summary.action_item_count} need attention`}</p>
        <Link href="/alerts" onClick={() => setOpen(false)} className="min-h-9 py-2 font-medium text-primary hover:underline">Open Alerts</Link>
      </div>
      <NotificationList compact onNavigate={() => setOpen(false)} />
    </Modal>
  </>;
}
