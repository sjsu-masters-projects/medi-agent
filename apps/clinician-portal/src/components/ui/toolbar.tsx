"use client";

import type { ReactNode } from "react";

/** Segmented control for a single-choice filter. Same values as the select it replaces. */
export function SegmentedControl<T extends string>({ label, options, value, onChange, className = "" }: {
    label: string;
    options: { value: T; label: string }[];
    value: T;
    onChange: (value: T) => void;
    className?: string;
}) {
    return (
        <div role="radiogroup" aria-label={label} className={`inline-flex flex-wrap gap-0.5 rounded-[10px] bg-[rgba(100,116,139,.08)] p-[3px] ${className}`}>
            {options.map((option) => {
                const active = option.value === value;
                return (
                    <button key={option.value} type="button" role="radio" aria-checked={active} onClick={() => onChange(option.value)}
                        className={`h-[30px] min-h-0 rounded-lg px-3 text-[13px] transition-colors duration-[160ms] ${active ? "bg-surface font-medium text-ink shadow-[0_1px_2px_rgba(15,23,42,.08),0_0_0_1px_rgba(15,23,42,.04)]" : "text-muted hover:text-ink"}`}>
                        {option.label}
                    </button>
                );
            })}
        </div>
    );
}

/** Compact labelled field shell for toolbar selects and inputs. */
export function CompactField({ label, children, className = "" }: { label: string; children: ReactNode; className?: string }) {
    return (
        <label className={`flex h-10 items-center md:h-[34px] gap-2 rounded-[9px] border border-line-strong bg-surface pl-3 text-[13px] transition-colors focus-within:border-primary focus-within:ring-4 focus-within:ring-[rgba(37,99,235,.12)] hover:border-[rgba(100,116,139,.36)] ${className}`}>
            <span className="shrink-0 text-muted">{label}</span>
            {children}
        </label>
    );
}

export const compactSelectClass = "h-full min-w-0 cursor-pointer rounded-r-[9px] bg-transparent pr-7 font-medium text-ink outline-none";
