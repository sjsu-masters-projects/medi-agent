import type { InputHTMLAttributes, ReactNode } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
    label?: string;
    error?: string;
    icon?: ReactNode;
    trailingAction?: ReactNode;
}

export const fieldClass = "w-full rounded-[10px] border border-line-strong bg-surface px-3.5 text-sm text-ink outline-none transition placeholder:text-[#94A3B8] hover:border-[rgba(100,116,139,.36)] focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)] disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-muted";

export function Input({ className = "", error, icon, id, label, trailingAction, ...props }: InputProps) {
    return (
        <label className="block">
            {label ? <span className="mb-1.5 block text-[13px] font-medium text-ink-2">{label}</span> : null}
            <span className="relative block">
                {icon ? (
                    <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-muted">
                        {icon}
                    </span>
                ) : null}
                <input
                    className={`${fieldClass} h-[42px] ${icon ? "pl-10" : ""} ${trailingAction ? "pr-11" : ""} ${error ? "border-risk focus:border-risk focus:ring-[rgba(220,38,38,.12)]" : ""} ${className}`}
                    id={id}
                    {...props}
                />
                {trailingAction ? (
                    <span className="absolute inset-y-0 right-2 flex items-center text-muted">
                        {trailingAction}
                    </span>
                ) : null}
            </span>
            {error ? <span className="mt-1.5 block text-xs text-risk-ink">{error}</span> : null}
        </label>
    );
}
