interface CircularProgressProps {
    percent: number;
    size?: number;
    strokeWidth?: number;
    className?: string;
    progressClassName?: string;
    textClassName?: string;
    trackClassName?: string;
}

export function CircularProgress({
    className = "",
    percent,
    progressClassName = "stroke-[#147465]",
    size = 64,
    strokeWidth = 6,
    textClassName = "text-[#17233a]",
    trackClassName = "stroke-[#d7e5de]",
}: CircularProgressProps) {
    const radius = (size - strokeWidth) / 2;
    const circumference = 2 * Math.PI * radius;
    const safePercent = Math.max(0, Math.min(100, percent));
    const dashOffset = circumference - (safePercent / 100) * circumference;

    return (
        <div className={`relative flex items-center justify-center ${className}`} style={{ height: size, width: size }}>
            <svg className="-rotate-90" height={size} width={size}>
                <circle
                    className={trackClassName}
                    cx={size / 2}
                    cy={size / 2}
                    fill="transparent"
                    r={radius}
                    strokeWidth={strokeWidth}
                />
                <circle
                    className={progressClassName}
                    cx={size / 2}
                    cy={size / 2}
                    fill="transparent"
                    r={radius}
                    strokeDasharray={circumference}
                    strokeDashoffset={dashOffset}
                    strokeLinecap="round"
                    strokeWidth={strokeWidth}
                />
            </svg>
            <span className={`absolute text-sm font-semibold ${textClassName}`}>{safePercent}%</span>
        </div>
    );
}
