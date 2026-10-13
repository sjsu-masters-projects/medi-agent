import type { ReactNode } from "react";
import { Icon, type IconName } from "./icons";

export type TileTone = "med" | "lab" | "hyd" | "note" | "upload" | "brand" | "move" | "danger" | "neutral" | "assistant";

const tileTones: Record<TileTone, string> = {
    med: "bg-med-tint text-med-ink",
    lab: "bg-lab-tint text-lab-ink",
    hyd: "bg-hyd-tint text-hyd-ink",
    note: "bg-note-tint text-note-ink",
    upload: "bg-upload-tint text-upload-ink",
    brand: "bg-brand-tint text-brand",
    move: "bg-move-tint text-move-ink",
    danger: "bg-danger-tint text-danger-ink",
    neutral: "bg-surface-2 text-ink-2",
    assistant: "bg-brand-deep text-gold",
};

const tileSizes = {
    sm: "h-10 w-10 rounded-xl [&>svg]:h-5 [&>svg]:w-5",
    md: "h-11 w-11 rounded-[13px] [&>svg]:h-5 [&>svg]:w-5",
    lg: "h-[52px] w-[52px] rounded-2xl [&>svg]:h-6 [&>svg]:w-6",
} as const;

/** Square icon tile coloured by the kind of thing it represents. */
export function IconTile({ icon, tone = "neutral", size = "md", className = "" }: { icon: IconName; tone?: TileTone; size?: keyof typeof tileSizes; className?: string }) {
    return <span aria-hidden="true" className={`flex shrink-0 items-center justify-center ${tileTones[tone]} ${tileSizes[size]} ${className}`}><Icon name={icon} /></span>;
}

/** Monospace uppercase eyebrow above a grouped list. */
export function SectionLabel({ children, action, as: Tag = "h2", className = "" }: { children: ReactNode; action?: ReactNode; as?: "h2" | "h3" | "p"; className?: string }) {
    return (
        <div className={`flex min-h-9 items-end justify-between gap-3 px-[22px] pt-5 pb-2 ${className}`}>
            <Tag className="font-mono text-xs uppercase tracking-[0.08em] text-muted">{children}</Tag>
            {action}
        </div>
    );
}

/** Rounded white container whose rows are separated by hairlines. */
export function GroupedList({ children, className = "", as: Tag = "ul", label }: { children: ReactNode; className?: string; as?: "ul" | "div" | "ol"; label?: string }) {
    return <Tag aria-label={label} className={`mx-4 overflow-hidden rounded-[22px] bg-surface [&>*]:border-b [&>*]:border-line [&>*:last-child]:border-b-0 ${className}`}>{children}</Tag>;
}

/** Large-title header used by every tab screen. */
export function LargeTitle({ title, subtitle, action, className = "" }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode; className?: string }) {
    return (
        <header className={`px-[22px] pt-4 pb-1 ${className}`}>
            <div className="flex items-center justify-between gap-3">
                <h1 className="min-w-0 break-words text-[32px] font-semibold leading-[1.1] tracking-[-0.02em] text-ink">{title}</h1>
                {action ? <div className="flex shrink-0 items-center gap-2">{action}</div> : null}
            </div>
            {subtitle ? <div className="mt-1.5 text-sm text-muted">{subtitle}</div> : null}
        </header>
    );
}

/** 44×44 filled brand action used in large-title headers. */
export const headerActionClass = "ma-press flex h-11 w-11 items-center justify-center rounded-[14px] bg-brand text-white shadow-[0_8px_18px_-10px_rgba(20,116,101,.8)] hover:bg-brand-hover disabled:opacity-50";
/** 44×44 quiet action used in large-title headers. */
export const headerGhostClass = "ma-press flex h-11 w-11 items-center justify-center rounded-[14px] bg-surface text-ink-2 hover:bg-surface-2 disabled:opacity-50";
