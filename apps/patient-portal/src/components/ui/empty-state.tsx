import type { ReactNode } from "react";
import { HiOutlineInbox } from "react-icons/hi2";

interface EmptyStateProps {
    icon?: ReactNode;
    title: string;
    description?: string;
    action?: ReactNode;
}

export function EmptyState({ action, description, icon, title }: EmptyStateProps) {
    return (
        <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-gray-300 bg-white px-6 py-10 text-center shadow-sm">
            <span className="text-4xl text-slate-400">{icon ?? <HiOutlineInbox />}</span>
            <div className="space-y-1">
                <h3 className="text-base font-semibold text-gray-900">{title}</h3>
                {description ? <p className="text-sm text-gray-500">{description}</p> : null}
            </div>
            {action}
        </div>
    );
}
