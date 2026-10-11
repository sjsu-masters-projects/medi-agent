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
        <div className="flex flex-col items-center justify-center gap-3 px-6 py-10 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-tint text-2xl text-brand [&>svg]:h-6 [&>svg]:w-6">{icon ?? <Icon name="inbox" />}</span>
            <div className="max-w-[30ch] space-y-1">
                <h3 className="text-[17px] font-semibold text-ink">{title}</h3>
                {description ? <p className="text-[15px] leading-relaxed text-muted">{description}</p> : null}
            </div>
            {action ? <div className="mt-1">{action}</div> : null}
        </div>
    );
}
