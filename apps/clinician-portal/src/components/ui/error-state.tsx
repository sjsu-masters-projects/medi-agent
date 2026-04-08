import type { ReactNode } from "react";

interface ErrorStateProps {
    title?: string;
    description?: string;
    icon?: string;
    onRetry?: () => void;
    action?: ReactNode;
}

export function ErrorState({
    action,
    description = "Something went wrong. Please try again.",
    icon = "⚠️",
    onRetry,
    title = "Error",
}: ErrorStateProps) {
    return (
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-red-200 bg-red-50 px-6 py-10 text-center shadow-sm">
            <span className="text-4xl">{icon}</span>
            <div className="space-y-1">
                <h3 className="text-base font-semibold text-gray-900">{title}</h3>
                <p className="text-sm text-gray-600">{description}</p>
            </div>
            {onRetry ? (
                <button
                    className="rounded-lg border border-red-300 bg-white px-4 py-2 text-sm font-medium text-red-600 transition hover:bg-red-50"
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
