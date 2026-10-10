"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";

interface ModalProps {
    open: boolean;
    onClose: () => void;
    title: string;
    children: ReactNode;
    contentClassName?: string;
}

export function Modal({ children, contentClassName, onClose, open, title }: ModalProps) {
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

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
            <div
                ref={dialogRef}
                role="dialog"
                aria-modal="true"
                aria-labelledby={titleId}
                className={`max-h-[calc(100dvh-2rem)] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-4 shadow-xl sm:p-6 ${contentClassName ?? ""}`}
                onClick={(event) => event.stopPropagation()}
            >
                <div className="mb-4 flex items-center justify-between">
                    <h2 id={titleId} className="text-lg font-semibold text-gray-900">{title}</h2>
                    <button
                        aria-label="Close modal"
                        className="rounded-lg p-2 text-gray-400 transition hover:bg-gray-100 hover:text-gray-600"
                        onClick={onClose}
                        type="button"
                    >
                        ✕
                    </button>
                </div>
                {children}
            </div>
        </div>
    );
}
