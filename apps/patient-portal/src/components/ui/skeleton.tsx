interface SkeletonProps {
    className?: string;
    variant?: "text" | "circle" | "rect";
}

const variantClasses: Record<NonNullable<SkeletonProps["variant"]>, string> = {
    text: "h-4 rounded-md",
    circle: "rounded-full",
    rect: "rounded-[22px]",
};

export function Skeleton({ className = "", variant = "rect" }: SkeletonProps) {
    return <div aria-hidden="true" className={`ma-skeleton ${variantClasses[variant]} ${className}`} />;
}
