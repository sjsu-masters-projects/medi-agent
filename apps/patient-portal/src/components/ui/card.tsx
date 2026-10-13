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
            className={`rounded-[22px] border border-line bg-surface ${paddingClasses[padding]} ${className}`}
        >
            {children}
        </Component>
    );
}
