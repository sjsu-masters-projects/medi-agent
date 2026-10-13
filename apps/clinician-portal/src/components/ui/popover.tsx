"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";

/** Anchored help panel. Opens on click, closes on Escape or outside click, returns focus. */
export function Popover({ trigger, label, children, align = "start", side = "bottom", className = "", panelClassName = "" }: {
    trigger: (props: { "aria-expanded": boolean; "aria-controls": string; onClick: () => void }) => ReactNode;
    label: string;
    children: ReactNode;
    align?: "start" | "end";
    side?: "bottom" | "top";
    className?: string;
    panelClassName?: string;
}) {
    const [open, setOpen] = useState(false);
    const root = useRef<HTMLDivElement>(null);
    const panelId = useId();
    useEffect(() => {
        if (!open) return;
        function onPointer(event: PointerEvent) { if (!root.current?.contains(event.target as Node)) setOpen(false); }
        function onKey(event: KeyboardEvent) { if (event.key === "Escape") { event.preventDefault(); setOpen(false); root.current?.querySelector<HTMLElement>("[aria-controls]")?.focus(); } }
        document.addEventListener("pointerdown", onPointer);
        document.addEventListener("keydown", onKey);
        return () => { document.removeEventListener("pointerdown", onPointer); document.removeEventListener("keydown", onKey); };
    }, [open]);
    return (
        <div ref={root} className={`relative ${className}`}>
            {trigger({ "aria-expanded": open, "aria-controls": panelId, onClick: () => setOpen((value) => !value) })}
            {open ? (
                <div id={panelId} role="dialog" aria-label={label}
                    className={`ma-pop absolute z-40 w-[min(420px,calc(100vw-48px))] rounded-xl border border-line bg-surface p-4 text-sm leading-relaxed text-ink-2 shadow-[var(--shadow-pop)] ${side === "bottom" ? "top-[calc(100%+8px)]" : "bottom-[calc(100%+8px)]"} ${align === "end" ? "right-0" : "left-0"} ${panelClassName}`}>
                    {children}
                </div>
            ) : null}
        </div>
    );
}
