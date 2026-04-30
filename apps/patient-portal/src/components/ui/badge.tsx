import type { ReactNode } from "react";

interface BadgeProps {
    variant: "success" | "warning" | "danger" | "info" | "neutral";
    children: ReactNode;
}

const variantClasses: Record<BadgeProps["variant"], string> = {
    success: "border-[#b9dfcc] bg-[#e9f7ef] text-[#276749]",
    warning: "border-[#edd59a] bg-[#fff7dc] text-[#8a5a00]",
    danger: "border-[#efbeb5] bg-[#fff2ef] text-[#a43c2f]",
    info: "border-[#b6d9d2] bg-[#e6f4f1] text-[#147465]",
    neutral: "border-[#d7dce5] bg-[#f4f0ea] text-[#5b6b83]",
};

export function Badge({ children, variant }: BadgeProps) {
    return (
        <span
            className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-bold ${variantClasses[variant]}`}
        >
            {children}
        </span>
    );
}
