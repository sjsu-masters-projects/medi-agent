import type { ReactNode } from "react";
import { Icon } from "./icons";

interface ErrorStateProps {
    title?: string;
    description?: string;
    icon?: ReactNode;
    onRetry?: () => void;
    action?: ReactNode;
}

export function ErrorState({
    action,
    description = "Something went wrong. Please try again.",
    icon = <Icon name="alert" />,
    onRetry,
    title = "Error",
}: ErrorStateProps) {
    return (
        <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-risk-line bg-risk-soft px-6 py-10 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-surface text-2xl text-risk-ink [&>svg]:h-6 [&>svg]:w-6">{icon}</span>
            <div className="max-w-[56ch] space-y-1">
                <h3 className="text-[15px] font-semibold text-ink">{title}</h3>
                <p className="text-sm leading-relaxed text-ink-2">{description}</p>
            </div>
            {onRetry ? (
                <button
                    className="ma-press h-[34px] rounded-[9px] border border-risk-line bg-surface px-4 text-[13px] font-semibold text-risk-ink hover:bg-risk-tint"
                    onClick={onRetry}
                    type="button"
                >
                    Try again
                </button>
            ) : null}
            {action}
        </div>
    );
}
