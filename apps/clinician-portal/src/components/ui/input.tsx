import type { InputHTMLAttributes, ReactNode } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
    label?: string;
    error?: string;
    icon?: ReactNode;
    trailingAction?: ReactNode;
}

export function Input({ className = "", error, icon, id, label, trailingAction, ...props }: InputProps) {
    return (
        <label className="block">
            {label ? <span className="mb-1 block text-sm font-medium text-gray-700">{label}</span> : null}
            <span className="relative block">
                {icon ? (
                    <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-gray-400">
                        {icon}
                    </span>
                ) : null}
                <input
                    className={`w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-500 ${icon ? "pl-10" : ""} ${trailingAction ? "pr-11" : ""} ${error ? "border-red-300 focus:border-red-400 focus:ring-red-200" : ""} ${className}`}
                    id={id}
                    {...props}
                />
                {trailingAction ? (
                    <span className="absolute inset-y-0 right-3 flex items-center text-gray-500">
                        {trailingAction}
                    </span>
                ) : null}
            </span>
            {error ? <span className="mt-1 block text-xs text-red-600">{error}</span> : null}
        </label>
    );
}
