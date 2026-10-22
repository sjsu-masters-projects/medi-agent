"use client";

import { useState } from "react";
import Link from "next/link";
import { Badge } from "@/components/ui";
import type { HandoffItem, HandoffSection } from "@/services/handoff-summaries";

export function stamp(value: string): string {
    return value.replace("T", " ").slice(0, 16);
}

function SourceChip({ item }: { item: HandoffItem }) {
    const chip = "inline-flex max-w-full min-w-0 items-center rounded-md border border-line bg-surface-2 px-2 py-0.5 text-xs text-ink-2";
    if (item.source.href) {
        return <Link className={`${chip} [overflow-wrap:anywhere] hover:bg-sunken hover:text-ink`} href={item.source.href}>Source: {item.source.label}</Link>;
    }
    return <span className={`${chip} [overflow-wrap:anywhere]`}>Source: {item.source.label}</span>;
}

export function Section({ section }: { section: HandoffSection }) {
    const [open, setOpen] = useState(true);
    const panel = `handoff-section-${section.key}`;
    return (
        <section className="rounded-xl border border-line bg-surface ma-print-section" data-testid={`section-${section.key}`}>
            <h3>
                <button aria-controls={panel} aria-expanded={open} className="flex min-h-11 w-full items-center justify-between gap-3 px-4 py-2.5 text-left text-sm font-semibold text-ink" onClick={() => setOpen(!open)} type="button">
                    <span>{section.title}</span>
                    <span className="flex items-center gap-2 text-xs font-normal text-muted">
                        {section.status === "unavailable" ? <Badge variant="danger">Unavailable</Badge> : `${section.items.length} ${section.items.length === 1 ? "line" : "lines"}`}
                        <span aria-hidden="true">{open ? "−" : "+"}</span>
                    </span>
                </button>
            </h3>
            <div className={`border-t border-line px-4 py-3 ${open ? "" : "hidden print:block"}`} id={panel}>
                {section.note ? <p className={`mb-2 text-sm ${section.status === "unavailable" ? "font-medium text-risk-ink" : "text-muted"}`} role={section.status === "unavailable" ? "alert" : undefined}>{section.note}</p> : null}
                <ul className="space-y-3">
                    {section.items.map((item) => (
                        <li className="min-w-0" key={item.id}>
                            <p className="[overflow-wrap:anywhere] text-sm text-ink">{item.text}</p>
                            {item.detail ? <p className="[overflow-wrap:anywhere] text-xs text-muted">{item.detail}</p> : null}
                            <div className="mt-1"><SourceChip item={item} /></div>
                        </li>
                    ))}
                </ul>
            </div>
        </section>
    );
}

