"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./icons";

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

/** Bottom sheet on phones: slides up, traps focus, closes on backdrop tap and Escape. */
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
        // Same rules as the clinician dialog: skip hidden, aria-hidden and collapsed-<details>
        // controls, which cannot take focus and would otherwise let Tab leave the trap.
        const focusable = () => Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [tabindex="0"]') ?? []).filter((element) => {
            if (element.closest('[hidden], [aria-hidden="true"]')) return false;
            for (let ancestor = element.parentElement; ancestor; ancestor = ancestor.parentElement) {
                if (ancestor.tagName === "DETAILS" && !ancestor.hasAttribute("open") && !ancestor.firstElementChild?.contains(element)) return false;
            }
            return true;
        });
        (focusable()[0] ?? panel.current)?.focus();
        function onKey(event: KeyboardEvent) {
            if (event.key === "Escape") { event.preventDefault(); close.current(); }
            if (event.key !== "Tab") return;
            const elements = focusable();
            const first = elements[0]; const last = elements.at(-1);
            const outside = !panel.current?.contains(document.activeElement);
            if (!first) { event.preventDefault(); panel.current?.focus(); }
            else if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current || outside)) { event.preventDefault(); last?.focus(); }
            else if (!event.shiftKey && (document.activeElement === last || outside)) { event.preventDefault(); first.focus(); }
        }
        document.addEventListener("keydown", onKey);
        return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = overflow; if (previous?.isConnected) previous.focus(); };
    }, [open]);
    if ((!open && !keepMounted) || typeof document === "undefined") {
        return null;
    }

    return createPortal(
        <div hidden={!open} style={!open ? { display: "none" } : undefined} className={`ma-fade fixed inset-0 z-60 flex flex-col bg-[rgba(16,32,43,.4)] ${overlayClasses[size]}`} onClick={onClose}>
            <div
                aria-labelledby={open ? titleId : undefined}
                aria-modal={open ? true : undefined}
                ref={panel}
                role={open ? "dialog" : undefined}
                tabIndex={-1}
                className={`ma-sheet-panel mx-auto max-h-[90dvh] w-full ${sizeClasses[size]} overflow-y-auto overscroll-contain bg-surface px-5 pt-2.5 pb-[calc(24px+env(safe-area-inset-bottom))] shadow-[var(--shadow-sheet)] outline-none`}
                onClick={(event) => event.stopPropagation()}
            >
                <div aria-hidden="true" className={`mx-auto mb-3 h-[5px] w-9 rounded-full bg-line-strong ${size === "wide" ? "md:hidden" : ""}`} />
                <div className="mb-4 flex items-start justify-between gap-3">
                    <h3 id={titleId} className="min-w-0 break-words pt-1.5 text-[20px] font-semibold leading-tight tracking-[-0.01em] text-ink [overflow-wrap:anywhere]">{title}</h3>
                    <button
                        aria-label={closeLabel}
                        className="ma-press -mr-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-ink-2 hover:bg-surface-2"
                        onClick={onClose}
                        type="button"
                    >
                        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-surface-2"><Icon name="close" className="h-4 w-4" strokeWidth={2} /></span>
                    </button>
                </div>
                {children}
            </div>
        </div>,
        document.body,
    );
}
