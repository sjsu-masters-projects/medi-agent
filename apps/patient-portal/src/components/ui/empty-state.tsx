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
        <div className="flex flex-col items-center justify-center gap-4 rounded-[28px] border border-dashed border-[#d8cbc0] bg-white/82 px-6 py-11 text-center shadow-[0_18px_48px_rgba(42,58,84,0.08)]">
            <span className="flex h-16 w-16 items-center justify-center rounded-3xl bg-[#e6f4f1] text-4xl text-[#147465]">{icon ?? <HiOutlineInbox />}</span>
            <div className="space-y-1">
                <h3 className="text-lg font-bold text-[#17233a]">{title}</h3>
                {description ? <p className="text-base leading-7 text-[#64748b]">{description}</p> : null}
            </div>
            {action}
        </div>
    );
}
