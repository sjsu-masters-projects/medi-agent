"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Icon, type IconName } from "./icons";

export interface OverflowMenuItem {
    label: string;
    icon?: IconName;
    onSelect: () => void;
    disabled?: boolean;
    busy?: boolean;
}

/** Quiet ⋯ menu for secondary actions such as Refresh (pull-to-refresh is the gesture path). */
export function OverflowMenu({ label, items, className = "", trigger, filled = false }: { label: string; items: OverflowMenuItem[]; className?: string; trigger?: ReactNode; filled?: boolean }) {
    const [open, setOpen] = useState(false);
    const root = useRef<HTMLDivElement>(null);
    const button = useRef<HTMLButtonElement>(null);
    const menuId = useId();
    useEffect(() => {
        if (!open) return;
        const first = root.current?.querySelector<HTMLElement>('[role="menuitem"]:not(:disabled)');
        first?.focus();
        function onPointer(event: PointerEvent) {
            if (!root.current?.contains(event.target as Node)) setOpen(false);
        }
        function onKey(event: KeyboardEvent) {
            if (event.key === "Escape") { event.preventDefault(); setOpen(false); button.current?.focus(); }
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                const entries = Array.from(root.current?.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled)') ?? []);
                if (!entries.length) return;
                event.preventDefault();
                const index = entries.indexOf(document.activeElement as HTMLElement);
                const next = event.key === "ArrowDown" ? (index + 1) % entries.length : (index - 1 + entries.length) % entries.length;
                entries[next]?.focus();
            }
        }
        document.addEventListener("pointerdown", onPointer);
        document.addEventListener("keydown", onKey);
        return () => { document.removeEventListener("pointerdown", onPointer); document.removeEventListener("keydown", onKey); };
    }, [open]);
    return (
        <div ref={root} className={`relative ${className}`}>
            <button
                ref={button}
                type="button"
                aria-label={label}
                aria-haspopup="menu"
                aria-expanded={open}
                aria-controls={open ? menuId : undefined}
                onClick={() => setOpen((value) => !value)}
                className={`ma-press flex h-11 w-11 items-center justify-center rounded-[14px] text-ink-2 aria-expanded:bg-surface ${filled ? "bg-surface hover:bg-surface-2" : "hover:bg-surface"}`}
            >
                {trigger ?? <Icon name="more" className="h-5 w-5" />}
            </button>
            {open ? (
                <div id={menuId} role="menu" aria-label={label} className="ma-enter absolute right-0 top-[calc(100%+6px)] z-40 min-w-[200px] overflow-hidden rounded-2xl border border-line bg-surface p-1.5 shadow-[var(--shadow-raised)]">
                    {items.map((item) => (
                        <button
                            key={item.label}
                            role="menuitem"
                            type="button"
                            disabled={item.disabled}
                            aria-busy={item.busy || undefined}
                            onClick={() => { setOpen(false); item.onSelect(); }}
                            className="flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-left text-[15px] font-medium text-ink hover:bg-surface-2 focus-visible:bg-surface-2 disabled:opacity-50"
                        >
                            {item.icon ? <Icon name={item.icon} className={`h-[18px] w-[18px] text-muted ${item.busy ? "animate-spin" : ""}`} /> : null}
                            {item.label}
                        </button>
                    ))}
                </div>
            ) : null}
        </div>
    );
}
