import type { ReactNode } from "react";

interface CardProps {
    children: ReactNode;
    className?: string;
    padding?: "sm" | "md" | "lg";
    as?: "article" | "div" | "section";
}

const paddingClasses: Record<NonNullable<CardProps["padding"]>, string> = {
    sm: "p-4",
    md: "p-5",
    lg: "p-6 sm:p-7",
};

export function Card({ as: Component = "div", children, className = "", padding = "md" }: CardProps) {
    return (
        <Component
            className={`rounded-[26px] border border-white/70 bg-white/88 shadow-[0_18px_48px_rgba(42,58,84,0.10)] ring-1 ring-[#eadfd4]/70 backdrop-blur ${paddingClasses[padding]} ${className}`}
        >
            {children}
        </Component>
    );
}
