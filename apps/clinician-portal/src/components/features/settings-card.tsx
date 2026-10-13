import type { ReactNode } from "react";
import { Icon, type IconName } from "@/components/ui/icons";

/** Footer strip shared by Settings cards. */
export const cardFooterClass =
    "flex flex-wrap items-center justify-end gap-3 rounded-b-2xl border-t border-line bg-surface-2 px-5 py-3";

/** Small sunken icon square used in Settings card headers and rows. */
export function IconTile({ name }: { name: IconName }) {
    return (
        <span aria-hidden="true" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-sunken text-ink-2">
            <Icon name={name} className="h-4 w-4" />
        </span>
    );
}

/** Settings card header: icon tile, title (children), optional subtitle and trailing action. */
export function CardHeader({ action, children, icon, sub }: { action?: ReactNode; children: ReactNode; icon: IconName; sub?: ReactNode }) {
    return (
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
            <div className="flex min-w-0 items-center gap-3">
                <IconTile name={icon} />
                <div className="min-w-0">
                    {children}
                    {sub ? <p className="mt-0.5 text-[13px] text-muted">{sub}</p> : null}
                </div>
            </div>
            {action}
        </div>
    );
}
