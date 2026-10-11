import type { ReactNode } from "react";

interface BadgeProps {
    variant: "success" | "warning" | "danger" | "info" | "neutral";
    children: ReactNode;
}

const variantClasses: Record<BadgeProps["variant"], string> = {
    success: "border-brand/15 bg-brand-tint text-brand-ink",
    warning: "border-note-ink/15 bg-note-tint text-note-ink",
    danger: "border-danger-ink/15 bg-danger-tint text-danger-ink",
    info: "border-lab-ink/15 bg-lab-tint text-lab-ink",
    neutral: "border-line-strong bg-surface-2 text-muted",
};

export function Badge({ children, variant }: BadgeProps) {
    return (
        <span
            className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold ${variantClasses[variant]}`}
        >
            {children}
        </span>
    );
}
