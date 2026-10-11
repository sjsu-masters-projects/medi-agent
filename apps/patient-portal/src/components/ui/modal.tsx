"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

interface ModalProps {
    open: boolean;
    onClose: () => void;
    title: string;
    children: ReactNode;
    size?: "default" | "wide";
    closeLabel?: string;
    keepMounted?: boolean;
}

const sizeClasses: Record<NonNullable<ModalProps["size"]>, string> = {
    default: "max-w-[480px] rounded-t-[28px]",
    wide: "max-w-[480px] rounded-t-[28px] md:max-w-[960px] md:rounded-[28px] xl:max-w-[1080px]",
};

const overlayClasses: Record<NonNullable<ModalProps["size"]>, string> = {
    default: "justify-end",
    wide: "justify-end md:items-center md:justify-center md:p-6",
};

export function Modal({ children, closeLabel = "Close modal", keepMounted = false, onClose, open, size = "default", title }: ModalProps) {
    const panel = useRef<HTMLDivElement>(null);
    const titleId = useId();
    const close = useRef(onClose);
    useEffect(() => { close.current = onClose; }, [onClose]);
    useEffect(() => {
        if (!open) return;
        const previous = document.activeElement as HTMLElement | null;
        const overflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        const focusable = () => Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [tabindex="0"]') ?? []).filter((element) => !element.closest("[hidden]"));
        (focusable()[0] ?? panel.current)?.focus();
        function onKey(event: KeyboardEvent) {
            if (event.key === "Escape") { event.preventDefault(); close.current(); }
            if (event.key !== "Tab") return;
            const elements = focusable();
            const first = elements[0]; const last = elements.at(-1);
            if (!first) { event.preventDefault(); panel.current?.focus(); }
            else if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last?.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        }
        document.addEventListener("keydown", onKey);
        return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = overflow; if (previous?.isConnected) previous.focus(); };
    }, [open]);
    if ((!open && !keepMounted) || typeof document === "undefined") {
        return null;
    }

    return createPortal(
        <div hidden={!open} style={!open ? { display: "none" } : undefined} className={`ma-fade fixed inset-0 z-60 flex flex-col bg-ink/40 ${overlayClasses[size]}`} onClick={onClose}>
            <div
                aria-labelledby={open ? titleId : undefined}
                aria-modal={open ? true : undefined}
                ref={panel}
                role={open ? "dialog" : undefined}
                tabIndex={-1}
                className={`ma-sheet-panel mx-auto max-h-[88dvh] w-full ${sizeClasses[size]} overflow-y-auto border border-line bg-surface p-6 pb-[calc(24px+env(safe-area-inset-bottom))] shadow-[0_-24px_80px_rgba(16,32,43,0.20)]`}
                onClick={(event) => event.stopPropagation()}
            >
                <div className="mb-4 flex items-center justify-between">
                    <h3 id={titleId} className="min-w-0 break-words [overflow-wrap:anywhere] text-xl font-semibold text-ink">{title}</h3>
                    <button
                        aria-label={closeLabel}
                        className="ma-press flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl text-muted transition hover:bg-surface-2 hover:text-ink"
                        onClick={onClose}
                        type="button"
                    >
                        ✕
                    </button>
                </div>
                {children}
            </div>
        </div>,
        document.body,
    );
}
