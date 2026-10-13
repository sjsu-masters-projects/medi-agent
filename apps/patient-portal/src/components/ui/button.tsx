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
    danger: "bg-danger-tint text-danger-ink hover:bg-[#F6DCD4]",
};

const sizeClasses: Record<NonNullable<ButtonProps["size"]>, string> = {
    sm: "min-h-11 rounded-[14px] px-3.5 py-2 text-sm",
    md: "min-h-12 rounded-2xl px-4 py-2.5 text-[15px]",
    lg: "min-h-[54px] rounded-2xl px-5 py-3 text-[17px]",
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
        "ma-press inline-flex min-w-11 max-w-full items-center justify-center gap-2 whitespace-normal break-words text-center font-semibold disabled:cursor-not-allowed disabled:opacity-50",
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
