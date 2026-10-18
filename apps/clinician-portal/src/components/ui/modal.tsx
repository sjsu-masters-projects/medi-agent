"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./icons";

interface ModalProps {
    open: boolean;
    onClose: () => void;
    title: string;
    children: ReactNode;
    contentClassName?: string;
    /**
     * "side" is a right-hand panel: about 440px wide on desktop and full screen below 640px.
     * Its children fill the panel under the title (own scroll area and sticky footer).
     */
    placement?: "center" | "side";
}

export function Modal({ children, contentClassName, onClose, open, placement = "center", title }: ModalProps) {
    const titleId = useId();
    const dialogRef = useRef<HTMLDivElement>(null);
    const closeRef = useRef(onClose);
    useEffect(() => { closeRef.current = onClose; }, [onClose]);
    useEffect(() => {
        if (!open) return;
        const previousFocus = document.activeElement;
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        const focusable = () => [...(dialogRef.current?.querySelectorAll<HTMLElement>(
            'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex="0"]',
        ) ?? [])].filter((element) => {
            if (element.matches(":disabled") || element.closest('[hidden], [aria-hidden="true"]')) return false;
            for (let ancestor = element.parentElement; ancestor; ancestor = ancestor.parentElement) {
                if (ancestor.tagName === "DETAILS" && !ancestor.hasAttribute("open") &&
                    !ancestor.firstElementChild?.contains(element)) return false;
            }
            return true;
        });
        focusable()[0]?.focus();
        function handleKey(event: KeyboardEvent) {
            if (event.key === "Escape") { event.preventDefault(); closeRef.current(); }
            if (event.key !== "Tab") return;
            const elements = focusable();
            const first = elements[0];
            const last = elements[elements.length - 1];
            if (event.shiftKey && (document.activeElement === first || !dialogRef.current?.contains(document.activeElement))) {
                event.preventDefault(); last?.focus();
            } else if (!event.shiftKey && (document.activeElement === last || !dialogRef.current?.contains(document.activeElement))) {
                event.preventDefault(); first?.focus();
            }
        }
        document.addEventListener("keydown", handleKey);
        return () => {
            document.removeEventListener("keydown", handleKey);
            document.body.style.overflow = previousOverflow;
            if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
        };
    }, [open]);
    if (!open) {
        return null;
    }

    // Rendered into <body>: an animated or transformed ancestor would otherwise become the
    // containing block for `fixed`, so the backdrop covered only part of the screen and
    // left the sidebar and header clickable behind the dialog.
    const side = placement === "side";
    const dialog = (
        <div className={`ma-fade fixed inset-0 z-50 flex bg-[rgba(15,23,42,.45)] backdrop-blur-[2px] ${side ? "justify-end" : "items-center justify-center p-4"}`} onClick={onClose}>
            <div
                ref={dialogRef}
                role="dialog"
                aria-modal="true"
                aria-labelledby={titleId}
                className={side
                    ? `flex h-dvh w-full min-w-0 flex-col border-line bg-surface shadow-[var(--shadow-pop)] sm:max-w-[440px] sm:rounded-l-2xl sm:border-l ${contentClassName ?? ""}`
                    : `ma-pop max-h-[calc(100dvh-2rem)] w-full max-w-2xl overflow-y-auto rounded-2xl border border-line bg-surface p-5 shadow-[var(--shadow-pop)] sm:p-6 ${contentClassName ?? ""}`}
                onClick={(event) => event.stopPropagation()}
            >
                <div className={`flex items-center justify-between ${side ? "shrink-0 border-b border-line px-5 py-3.5" : "mb-4"}`}>
                    <h2 id={titleId} className="text-lg font-semibold tracking-[-0.01em] text-ink">{title}</h2>
                    <button
                        aria-label="Close modal"
                        className="ma-press flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-sunken hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                        onClick={onClose}
                        type="button"
                    >
                        <Icon name="close" className="h-4 w-4" strokeWidth={2} />
                    </button>
                </div>
                {children}
            </div>
        </div>
    );
    return typeof document === "undefined" ? dialog : createPortal(dialog, document.body);
}
