import type { InputHTMLAttributes, ReactNode } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
    label?: string;
    error?: string;
    icon?: ReactNode;
    trailingAction?: ReactNode;
}

export function Input({ className = "", error, icon, id, label, trailingAction, ...props }: InputProps) {
    return (
        <label className="block min-w-0">
            {label ? <span className="mb-2 block text-[0.95rem] font-semibold text-ink-2">{label}</span> : null}
            <span className="relative block">
                {icon ? (
                    <span className="pointer-events-none absolute inset-y-0 left-4 flex items-center text-muted">
                        {icon}
                    </span>
                ) : null}
                <input
                    className={`min-h-[3.25rem] w-full rounded-2xl border border-line-strong bg-surface px-4 py-3 text-base text-ink outline-none transition placeholder:text-muted focus:border-brand focus:ring-4 focus:ring-brand/15 ${icon ? "pl-11" : ""} ${trailingAction ? "pr-12" : ""} ${error ? "border-danger-ink focus:border-danger-ink focus:ring-danger-ink/15" : ""} ${className}`}
                    id={id}
                    {...props}
                />
                {trailingAction ? (
                    <span className="absolute inset-y-0 right-4 flex items-center text-muted">
                        {trailingAction}
                    </span>
                ) : null}
            </span>
            {error ? <span className="mt-2 block text-sm font-medium text-danger-ink">{error}</span> : null}
        </label>
    );
}
