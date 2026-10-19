"use client";

import { useState } from "react";
import { Icon } from "@/components/ui/icons";
import type { NeedsActionItem, NeedsActionKind } from "@/services/appointments";
import { needsActionCounts } from "@/utils/schedule";
import { ClinicChip } from "./clinic-chip";

type Filter = NeedsActionKind | "expiring" | null;

const KIND_TEXT: Record<NeedsActionKind, string> = {
  awaiting_reply: "Awaiting the patient's reply",
  change_request: "Patient asked for different times",
  expired: "Expired without an answer",
};

function plural(count: number, one: string, many = `${one}s`) {
  return `${count} ${count === 1 ? one : many}`;
}

function expiresIn(item: NeedsActionItem, now: number): string | null {
  if (!item.expiresAt) return null;
  const hours = Math.round((Date.parse(item.expiresAt) - now) / 3_600_000);
  if (hours < 1) return "expires within the hour";
  return hours < 48 ? `expires in ${hours} h` : `expires in ${Math.round(hours / 24)} d`;
}

function matches(item: NeedsActionItem, filter: Filter) {
  if (filter === null) return true;
  if (filter === "expiring") return item.kind === "awaiting_reply" && item.expiringSoon;
  return item.kind === filter;
}

/**
 * Offers waiting on the patient, change requests and expired offers: a compact row of count
 * cards that each open a short list. At phone width the cards collapse to one summary line.
 */
export function ScheduleNeedsAction({
  items,
  showClinic,
  onOpen,
  now,
}: {
  items: NeedsActionItem[];
  showClinic: boolean;
  onOpen: (item: NeedsActionItem) => void;
  now: number;
}) {
  const [filter, setFilter] = useState<Filter>(null);
  const [open, setOpen] = useState(false);
  if (!items.length) return null;
  const counts = needsActionCounts(items);
  const cards: { filter: Filter; count: number; label: string; urgent?: boolean }[] = [
    { filter: "awaiting_reply", count: counts.awaiting, label: "awaiting reply" },
    { filter: "expiring", count: counts.expiringSoon, label: "expiring soon", urgent: true },
    {
      filter: "change_request",
      count: counts.changeRequests,
      label: counts.changeRequests === 1 ? "change request" : "change requests",
    },
    { filter: "expired", count: counts.expired, label: "expired" },
  ];
  const shown = cards.filter((card) => card.count > 0);
  const summary = shown.map((card) => `${card.count} ${card.label}`).join(" · ");
  const visible = items.filter((item) => matches(item, filter));

  function choose(next: Filter) {
    if (open && filter === next) {
      setOpen(false);
      return;
    }
    setFilter(next);
    setOpen(true);
  }

  return (
    <section aria-label="Needs action" className="space-y-2">
      <h2 className="sr-only">Needs action</h2>
      <button
        aria-expanded={open}
        className="ma-press flex min-h-11 w-full items-center gap-2 rounded-xl border border-line bg-surface px-3.5 py-2 text-left text-[13px] font-medium text-ink shadow-[var(--shadow-card)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary sm:hidden"
        onClick={() => choose(null)}
        type="button"
      >
        <Icon name="bell" className="h-4 w-4 shrink-0 text-warn-ink" />
        <span className="min-w-0 flex-1 truncate" title={summary}>{summary}</span>
        <Icon name="chevron" className={`h-4 w-4 shrink-0 text-muted transition-transform ${open ? "rotate-90" : ""}`} />
      </button>
      <div className="hidden flex-wrap gap-2 sm:flex">
        {shown.map((card) => {
          const active = open && filter === card.filter;
          return (
            <button
              aria-label={`${card.count} ${card.label}`}
              aria-pressed={active}
              className={`ma-press flex min-h-11 items-center gap-2 rounded-xl border px-3.5 py-2 text-[13px] shadow-[var(--shadow-card)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                active ? "border-primary bg-primary-tint" : "border-line bg-surface hover:bg-surface-2"
              }`}
              key={card.filter}
              onClick={() => choose(card.filter)}
              type="button"
            >
              <span className={`font-mono text-base font-semibold ${card.urgent ? "text-warn-ink" : "text-ink"}`}>
                {card.count}
              </span>
              <span className="text-ink-2">{card.label}</span>
            </button>
          );
        })}
      </div>
      {open && (
        <ul
          aria-label="Items that need action"
          className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface shadow-[var(--shadow-card)]"
        >
          {visible.map((item) => {
            const expiry = item.kind === "awaiting_reply" ? expiresIn(item, now) : null;
            return (
              <li key={`${item.kind}-${item.appointmentId}`}>
                <button
                  className="flex min-h-14 w-full flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 text-left hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary"
                  onClick={() => onOpen(item)}
                  type="button"
                >
                  <span className="min-w-0 break-words text-sm font-medium text-ink">
                    {item.patientName ?? "Patient"}
                  </span>
                  {showClinic && <ClinicChip name={item.clinicName} />}
                  <span className="text-[13px] text-muted">
                    {KIND_TEXT[item.kind]} · {plural(item.slotCount, "time")}
                    {expiry ? ` · ${expiry}` : ""}
                  </span>
                  {item.expiringSoon && (
                    <span className="rounded-[7px] bg-warn-tint px-2 py-0.5 text-xs font-medium text-warn-ink">
                      Expiring soon
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
