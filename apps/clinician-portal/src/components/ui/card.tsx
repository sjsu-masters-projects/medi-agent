import type { ReactNode } from "react";

interface CardProps {
    children: ReactNode;
    className?: string;
    padding?: "none" | "sm" | "md" | "lg";
}

const paddingClasses: Record<NonNullable<CardProps["padding"]>, string> = {
    none: "",
    sm: "p-4",
    md: "p-5",
    lg: "p-6",
};

export function Card({ children, className = "", padding = "md" }: CardProps) {
    return (
        <div
            className={`rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)] ${paddingClasses[padding]} ${className}`}
        >
            {children}
        </div>
    );
}
