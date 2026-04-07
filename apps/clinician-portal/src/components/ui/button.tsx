import type { ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: "primary" | "secondary" | "ghost" | "danger";
    size?: "sm" | "md" | "lg";
    fullWidth?: boolean;
}

const variantClasses: Record<NonNullable<ButtonProps["variant"]>, string> = {
    primary: "bg-blue-600 text-white hover:bg-blue-700",
    secondary: "border border-gray-300 bg-white text-gray-700 shadow-sm hover:bg-gray-50",
    ghost: "text-gray-500 hover:bg-gray-100 hover:text-gray-700",
    danger: "border border-red-300 bg-red-50 text-red-600 hover:bg-red-100",
};

const sizeClasses: Record<NonNullable<ButtonProps["size"]>, string> = {
    sm: "px-3 py-2 text-xs",
    md: "px-4 py-2 text-sm",
    lg: "px-4 py-3 text-sm",
};

export function Button({
    children,
    className = "",
    fullWidth = false,
    size = "md",
    type = "button",
    variant = "primary",
    ...props
}: ButtonProps) {
    const classes = [
        "rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        variantClasses[variant],
        sizeClasses[size],
        fullWidth ? "w-full" : "",
        className,
    ]
        .filter(Boolean)
        .join(" ");

    return (
        <button className={classes} type={type} {...props}>
            {children}
        </button>
    );
}
