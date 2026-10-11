import type { ReactNode } from "react";
import { Icon } from "./icons";

interface EmptyStateProps {
    icon?: ReactNode;
    title: string;
    description?: string;
    action?: ReactNode;
}

export function EmptyState({ action, description, icon, title }: EmptyStateProps) {
    return (
        <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-line bg-surface px-6 py-12 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-sunken text-2xl text-muted [&>svg]:h-6 [&>svg]:w-6">{icon ?? <Icon name="inbox" />}</span>
            <div className="max-w-[48ch] space-y-1">
                <h3 className="text-[15px] font-semibold text-ink">{title}</h3>
                {description ? <p className="text-sm leading-relaxed text-muted">{description}</p> : null}
            </div>
            {action}
        </div>
    );
}
