"use client";

import Link from "next/link";

import { Icon } from "@/components/ui/icons";
import { IconTile } from "@/components/ui/list";
import { getADRFollowUpCopy } from "@/content/adr-follow-up-copy";
import { usePendingADRFollowUps } from "@/hooks/use-pending-adr-follow-ups";
import type { Locale } from "@/types";

/**
 * Entry point to the ADR follow-up view, shown only while the care team is
 * waiting on the patient's answers. A load failure hides it because the
 * destination view reports the error.
 */
export function ADRFollowUpEntryRow({ locale }: { locale: Locale }) {
  const { count, loaded } = usePendingADRFollowUps();
  if (!loaded || count < 1) return null;
  const copy = getADRFollowUpCopy(locale);

  return (
    <Link
      href="/chat?view=follow-up"
      lang={locale}
      className="ma-press flex min-h-11 items-center gap-3 rounded-[22px] bg-surface px-[14px] py-[13px] hover:bg-surface-2"
    >
      <IconTile icon="note" tone="note" />
      <span className="min-w-0 flex-1">
        <span className="block break-words text-[15px] font-semibold text-ink [overflow-wrap:anywhere]">
          {copy.entry.title}
        </span>
        <span className="block break-words text-[13px] leading-snug text-muted [overflow-wrap:anywhere]">
          {copy.entry.detail(count)}
        </span>
      </span>
      <Icon name="chevron" className="h-5 w-5 shrink-0 text-muted" />
    </Link>
  );
}
