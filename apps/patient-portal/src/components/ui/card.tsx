import type { ReactNode } from "react";

interface CardProps {
    children: ReactNode;
    className?: string;
    padding?: "sm" | "md" | "lg";
}

const paddingClasses: Record<NonNullable<CardProps["padding"]>, string> = {
    sm: "p-4",
    md: "p-5",
    lg: "p-6",
};

export function Card({ children, className = "", padding = "md" }: CardProps) {
    return (
        <div
            className={`rounded-xl border border-gray-200 bg-white shadow-sm ${paddingClasses[padding]} ${className}`}
        >
            {children}
        </div>
    );
}
