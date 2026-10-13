import type { ReactNode } from "react";

interface BadgeProps {
    variant: "success" | "warning" | "danger" | "info" | "neutral" | "ai";
    children: ReactNode;
    className?: string;
}

const variantClasses: Record<BadgeProps["variant"], string> = {
    success: "bg-ok-tint text-ok-ink",
    warning: "bg-warn-tint text-warn-ink",
    danger: "bg-risk-tint text-risk-ink",
    info: "bg-primary-tint text-primary",
    neutral: "bg-[rgba(100,116,139,.1)] text-ink-2",
    ai: "bg-ai-tint text-ai-ink",
};

export function Badge({ children, variant, className = "" }: BadgeProps) {
    return (
        <span
            className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-[7px] px-2 py-1 text-xs font-medium ${variantClasses[variant]} ${className}`}
        >
            {children}
        </span>
    );
}
