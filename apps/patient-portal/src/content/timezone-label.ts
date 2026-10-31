import type { Locale } from "@/types";

/**
 * A saved zone as people say it: "America/Los_Angeles" reads as "Pacific Time · Los Angeles"
 * ("hora del Pacífico · Los Angeles" in es-MX). A zone the browser cannot name falls back to
 * the id with spaces, never with underscores (UX-007).
 */
export function formatTimezoneLabel(zone: string, locale: Locale | string): string {
    try {
        const name = new Intl.DateTimeFormat(locale, { timeZone: zone, timeZoneName: "longGeneric" })
            .formatToParts(new Date())
            .find((part) => part.type === "timeZoneName")?.value;
        const city = zone.includes("/") ? zone.split("/").pop()?.replaceAll("_", " ") : null;
        if (name && city) return `${name} · ${city}`;
        return name ?? zone.replaceAll("_", " ");
    } catch {
        return zone.replaceAll("_", " ");
    }
}
