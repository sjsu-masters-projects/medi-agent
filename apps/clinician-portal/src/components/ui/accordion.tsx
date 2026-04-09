"use client";

import { useState } from "react";
import type { ReactNode } from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface AccordionProps {
    children: ReactNode;
    className?: string;
    /** Allow multiple items open simultaneously */
    multi?: boolean;
}

interface AccordionItemProps {
    title: ReactNode;
    children: ReactNode;
    /** Badge/label shown to the right of the title */
    badge?: ReactNode;
    /** Pre-expand this item */
    defaultOpen?: boolean;
    /** External control — pass isOpen + onToggle to manage from parent */
    isOpen?: boolean;
    onToggle?: () => void;
    className?: string;
}

// ── AccordionItem (can be used standalone) ────────────────────────────────────

export function AccordionItem({
    title,
    children,
    badge,
    defaultOpen = false,
    isOpen: controlledOpen,
    onToggle,
    className = "",
}: AccordionItemProps) {
    const [internalOpen, setInternalOpen] = useState(defaultOpen);
    const isControlled = controlledOpen !== undefined;
    const open = isControlled ? controlledOpen : internalOpen;

    function handleToggle() {
        if (isControlled) {
            onToggle?.();
        } else {
            setInternalOpen((prev) => !prev);
        }
    }

    return (
        <div className={`border border-gray-200 rounded-xl overflow-hidden ${className}`}>
            <button
                aria-expanded={open}
                className="flex w-full items-center justify-between bg-white px-5 py-4 text-left transition-colors hover:bg-gray-50"
                onClick={handleToggle}
                type="button"
            >
                <span className="text-sm font-semibold text-gray-900">{title}</span>
                <div className="flex items-center gap-2">
                    {badge}
                    <svg
                        aria-hidden="true"
                        className={`h-4 w-4 text-gray-400 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={2}
                        viewBox="0 0 24 24"
                    >
                        <path d="M19 9l-7 7-7-7" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                </div>
            </button>

            {/* CSS-based animation — no external deps */}
            <div
                className="overflow-hidden transition-all duration-300 ease-in-out"
                style={{ maxHeight: open ? "9999px" : "0px" }}
            >
                <div className="border-t border-gray-100 bg-white px-5 py-4">{children}</div>
            </div>
        </div>
    );
}

// ── Accordion wrapper (handles single-open logic) ─────────────────────────────

export function Accordion({ children, className = "", multi = false }: AccordionProps) {
    return (
        <div className={`flex flex-col gap-2 ${className}`} role="list">
            {children}
        </div>
    );
}
