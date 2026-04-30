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
            {label ? <span className="mb-2 block text-[0.95rem] font-semibold text-[#30415f]">{label}</span> : null}
            <span className="relative block">
                {icon ? (
                    <span className="pointer-events-none absolute inset-y-0 left-4 flex items-center text-[#8090a5]">
                        {icon}
                    </span>
                ) : null}
                <input
                    className={`min-h-[3.25rem] w-full rounded-2xl border border-[#d9cbc0] bg-white/90 px-4 py-3 text-base text-[#17233a] shadow-[0_8px_20px_rgba(42,58,84,0.05)] outline-none transition placeholder:text-[#8d9bae] focus:border-[#147465] focus:ring-4 focus:ring-[#147465]/15 ${icon ? "pl-11" : ""} ${trailingAction ? "pr-12" : ""} ${error ? "border-[#d55b4d] focus:border-[#d55b4d] focus:ring-[#d55b4d]/15" : ""} ${className}`}
                    id={id}
                    {...props}
                />
                {trailingAction ? (
                    <span className="absolute inset-y-0 right-4 flex items-center text-[#64748b]">
                        {trailingAction}
                    </span>
                ) : null}
            </span>
            {error ? <span className="mt-2 block text-sm font-medium text-[#b94032]">{error}</span> : null}
        </label>
    );
}
