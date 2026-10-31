import type { ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: "primary" | "secondary" | "ghost" | "danger" | "approve";
    size?: "sm" | "md" | "lg";
    fullWidth?: boolean;
}

const variantClasses: Record<NonNullable<ButtonProps["variant"]>, string> = {
    primary: "bg-primary text-white shadow-[0_1px_2px_rgba(37,99,235,.25)] hover:bg-primary-hover disabled:bg-track disabled:text-[#94A3B8] disabled:shadow-none",
    secondary: "border border-line-strong bg-surface text-ink-2 hover:bg-surface-2 hover:text-ink disabled:text-[#94A3B8]",
    ghost: "text-muted hover:bg-sunken hover:text-ink disabled:text-[#94A3B8]",
    danger: "border border-risk-line bg-surface text-risk-ink hover:bg-risk-soft disabled:text-[#94A3B8]",
    approve: "bg-ok text-white hover:bg-ok-strong disabled:bg-track disabled:text-[#94A3B8]",
};

const sizeClasses: Record<NonNullable<ButtonProps["size"]>, string> = {
    sm: "h-8 rounded-lg px-3 text-[13px]",
    md: "min-h-9 rounded-[9px] px-4 py-2 text-sm leading-5",
    lg: "min-h-[42px] rounded-[10px] px-[18px] py-2 text-sm",
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
        "ma-press inline-flex items-center justify-center gap-2 font-semibold disabled:cursor-not-allowed",
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
