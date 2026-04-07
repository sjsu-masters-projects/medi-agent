interface ProgressBarProps {
    value: number;
}

export function ProgressBar({ value }: ProgressBarProps) {
    return (
        <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200">
            <div
                aria-label={`Upload progress ${value}%`}
                className="h-full rounded-full bg-blue-600 transition-all"
                style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
            />
        </div>
    );
}
