/**
 * Shared utility functions.
 */

import { DEFAULT_LOCALE, type Locale } from "../types";

const INVALID_DATE_FALLBACK = "";

function toValidDate(input: string | Date): Date | null {
    const date = typeof input === "string" ? new Date(input) : input;
    return Number.isNaN(date.getTime()) ? null : date;
}

/**
 * Format a date string or Date object into a human-readable format.
 */
export function formatDate(date: string | Date, locale: Locale = DEFAULT_LOCALE): string {
    const validDate = toValidDate(date);
    if (!validDate) return INVALID_DATE_FALLBACK;
    return validDate.toLocaleDateString(locale, {
        year: "numeric",
        month: "short",
        day: "numeric",
    });
}

/**
 * Format a date string into a relative time string (e.g., "2 hours ago").
 */
export function formatRelativeTime(date: string | Date): string {
    const validDate = toValidDate(date);
    if (!validDate) return INVALID_DATE_FALLBACK;
    const now = new Date();
    const diffMs = now.getTime() - validDate.getTime();
    const diffMinutes = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMinutes / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMinutes < 1) return "just now";
    if (diffMinutes < 60) return `${diffMinutes}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return formatDate(validDate);
}

/**
 * Clamp a number between min and max.
 */
export function clamp(value: number, min: number, max: number): number {
    return Math.min(Math.max(value, min), max);
}

export type { SharedAuthSession, SharedAuthUser } from "./auth-session";
export { createAuthSessionStorage } from "./auth-session";
export type { BuildLoginRedirectUrlParams } from "./return-path";
export { buildLoginRedirectUrl, sanitizeReturnPath } from "./return-path";
