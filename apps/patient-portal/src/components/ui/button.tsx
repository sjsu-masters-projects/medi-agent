import type { ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: "primary" | "secondary" | "ghost" | "danger";
    size?: "sm" | "md" | "lg";
    fullWidth?: boolean;
}

const variantClasses: Record<NonNullable<ButtonProps["variant"]>, string> = {
    primary:
        "bg-brand text-white hover:bg-brand-hover",
    secondary:
        "bg-surface-2 text-ink-2 hover:bg-line-strong",
    ghost: "text-muted hover:bg-surface-2 hover:text-ink",
    danger: "border border-danger-ink/20 bg-danger-tint text-danger-ink hover:bg-danger-ink/10",
};

const sizeClasses: Record<NonNullable<ButtonProps["size"]>, string> = {
    sm: "min-h-11 px-3 py-2 text-sm",
    md: "min-h-12 px-4 py-2.5 text-[0.95rem]",
    lg: "min-h-14 px-5 py-3.5 text-base",
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
        "ma-press inline-flex min-w-11 max-w-full items-center justify-center whitespace-normal break-words rounded-2xl font-semibold transition-colors duration-[160ms] disabled:cursor-not-allowed disabled:opacity-50",
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
