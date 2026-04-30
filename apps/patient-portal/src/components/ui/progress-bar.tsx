interface ProgressBarProps {
    value: number;
}

export function ProgressBar({ value }: ProgressBarProps) {
    return (
        <div className="h-3 w-full overflow-hidden rounded-full bg-[#e2d7cb]">
            <div
                aria-label={`Upload progress ${value}%`}
                className="h-full rounded-full bg-[#147465] transition-all"
                style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
            />
        </div>
    );
}
