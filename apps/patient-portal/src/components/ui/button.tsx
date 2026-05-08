import type { ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
    variant?: "primary" | "secondary" | "ghost" | "danger";
    size?: "sm" | "md" | "lg";
    fullWidth?: boolean;
}

const variantClasses: Record<NonNullable<ButtonProps["variant"]>, string> = {
    primary:
        "bg-[#147465] text-white shadow-[0_14px_30px_rgba(20,116,101,0.24)] hover:bg-[#0f5f53]",
    secondary:
        "border border-[#d9cbc0] bg-white/88 text-[#30415f] shadow-[0_10px_24px_rgba(37,52,82,0.08)] hover:bg-[#fffaf4]",
    ghost: "text-[#5b6b83] hover:bg-white/70 hover:text-[#17233a]",
    danger: "border border-[#f0b8ae] bg-[#fff2ef] text-[#b94032] hover:bg-[#ffe8e3]",
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
        "inline-flex items-center justify-center rounded-2xl font-semibold transition-all duration-200 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50",
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
