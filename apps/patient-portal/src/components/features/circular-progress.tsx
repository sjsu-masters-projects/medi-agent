interface CircularProgressProps {
    percent: number;
    size?: number;
    strokeWidth?: number;
}

export function CircularProgress({
    percent,
    size = 64,
    strokeWidth = 6,
}: CircularProgressProps) {
    const radius = (size - strokeWidth) / 2;
    const circumference = 2 * Math.PI * radius;
    const safePercent = Math.max(0, Math.min(100, percent));
    const dashOffset = circumference - (safePercent / 100) * circumference;

    return (
        <div className="relative flex items-center justify-center" style={{ height: size, width: size }}>
            <svg className="-rotate-90" height={size} width={size}>
                <circle
                    className="stroke-blue-100"
                    cx={size / 2}
                    cy={size / 2}
                    fill="transparent"
                    r={radius}
                    strokeWidth={strokeWidth}
                />
                <circle
                    className="stroke-blue-600"
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
            <span className="absolute text-sm font-semibold text-gray-900">{safePercent}%</span>
        </div>
    );
}
