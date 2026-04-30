interface SkeletonProps {
    className?: string;
    variant?: "text" | "circle" | "rect";
}

const variantClasses: Record<NonNullable<SkeletonProps["variant"]>, string> = {
    text: "h-4 rounded",
    circle: "rounded-full",
    rect: "rounded-[24px]",
};

export function Skeleton({ className = "", variant = "rect" }: SkeletonProps) {
    return <div className={`animate-pulse bg-[#e7ddd2] ${variantClasses[variant]} ${className}`} />;
}
