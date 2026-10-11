"use client";

import { useLayoutEffect, useRef, type TextareaHTMLAttributes } from "react";

export function chatDisplayTime(timestamp: Date | string, locale: string, now = new Date()) {
  const date = timestamp instanceof Date ? timestamp : new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  if (date.toDateString() === now.toDateString())
    return new Intl.DateTimeFormat(locale, { hour: "numeric", minute: "2-digit" }).format(date);
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString())
    return new Intl.RelativeTimeFormat(locale, { numeric: "auto" }).format(-1, "day");
  return new Intl.DateTimeFormat(locale, { month: "short", day: "numeric", ...(date.getFullYear() !== now.getFullYear() ? { year: "numeric" } : {}) }).format(date);
}

export function ChatTextarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const field = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const element = field.current;
    if (!element) return;
    element.style.height = "0px";
    element.style.height = `${Math.max(44, Math.min(element.scrollHeight, 104))}px`;
  }, [props.value]);
  return <textarea {...props} ref={field} rows={1} className={`min-h-11 min-w-0 w-full resize-none bg-transparent px-4 py-3 text-base leading-[22px] text-ink placeholder:text-muted ${props.className ?? ""}`} />;
}

export const chatButton = "min-h-11 rounded-[14px] border border-line-strong bg-surface px-3 py-2 text-sm font-medium text-ink-2 transition-transform active:scale-[0.98] disabled:opacity-50";
