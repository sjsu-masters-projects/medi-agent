import type { ReactNode } from "react";

interface BadgeProps {
    variant: "success" | "warning" | "danger" | "info" | "neutral";
    children: ReactNode;
}

const variantClasses: Record<BadgeProps["variant"], string> = {
    success: "bg-green-100 text-green-800",
    warning: "bg-yellow-100 text-yellow-800",
    danger: "bg-red-100 text-red-800",
    info: "bg-blue-100 text-blue-800",
    neutral: "bg-gray-100 text-gray-700",
};

export function Badge({ children, variant }: BadgeProps) {
    return (
        <span
            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${variantClasses[variant]}`}
        >
            {children}
        </span>
    );
}
