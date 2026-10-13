import Link from "next/link";
import type { TodayCopy } from "@/content/today-copy";
import { getCarePlanCategoryLabel, getTaskStatusLabel } from "@/content/today-copy";
import { ApprovalSeal } from "@/components/ui/approval-seal";
import { Icon } from "@/components/ui/icons";
import { IconTile, type TileTone } from "@/components/ui/list";
import type { IconName } from "@/components/ui/icons";
import type { TaskCardStatus } from "./task-card.types";
import { FeedTaskType, type FeedTask } from "@/types";

/** Long patient instructions step down from headline size so the card stays scannable on a phone. */
/** Category labels are written for mid-sentence use; capitalize one that starts a line. */
function sentenceStart(text: string) {
    return text ? text.charAt(0).toLocaleUpperCase() + text.slice(1) : text;
}

function heroTitleSize(text: string) {
    return text.length > 72 ? "text-[19px]" : text.length > 40 ? "text-[20px]" : "text-[22px]";
}

function activityType(task: FeedTask) {
    switch (task.carePlan?.category) {
        case "movement": return "exercise";
        case "nutrition": return "diet";
        case "hydration": return "hydration";
        case "monitoring": return "monitoring";
        case "follow_up": return "follow_up";
        default: return "custom";
    }
}

function taskVisual(task: FeedTask): { icon: IconName; tone: TileTone } {
    if (task.type === FeedTaskType.MEDICATION) return { icon: "pill", tone: "med" };
    switch (task.carePlan?.category) {
        case "monitoring": return { icon: "gauge", tone: "lab" };
        case "hydration": return { icon: "drop", tone: "hyd" };
        case "movement": return { icon: "walk", tone: "move" };
        case "nutrition": return { icon: "leaf", tone: "note" };
        case "follow_up": return { icon: "cal", tone: "brand" };
        default: return { icon: "check", tone: "neutral" };
    }
}

export function TodayTaskIcon({ task, large = false }: { task: FeedTask; large?: boolean }) {
    const visual = taskVisual(task);
    return <IconTile icon={visual.icon} tone={visual.tone} size={large ? "lg" : "sm"} />;
}

function statusPillClass(status: TaskCardStatus) {
    if (status === "missed") return "bg-danger-tint text-danger-ink";
    if (status === "active" || status === "completed") return "bg-brand-tint text-brand-ink";
    if (status === "skipped") return "bg-note-tint text-note-ink";
    return "bg-surface-2 text-ink-2";
}

/** Status pill with the clock time in mono, e.g. "Missed · 8:00 AM". */
/** Older single-language records keep their wording; say so instead of mixing silently. */
export function WrittenIn({ task, copy }: { task: FeedTask; copy: TodayCopy }) {
    if (!task.contentLocale || task.contentLocale === copy.locale) return null;
    return <p className="flex items-center gap-1.5 text-[12px] font-medium text-muted"><Icon name="globe" className="h-3.5 w-3.5 shrink-0" />{copy.writtenIn(task.contentLocale)}</p>;
}

export function TaskStatusPill({ status, task, copy, timeLabel }: { status: TaskCardStatus; task: FeedTask; copy: TodayCopy; timeLabel: string }) {
    const showTime = Boolean(task.scheduledTime) || !task.requiresScheduleConfiguration;
    return <span className={`inline-flex max-w-full shrink-0 flex-wrap items-center gap-x-1 rounded-full px-2.5 py-1 text-xs font-semibold ${statusPillClass(status)}`}>
        <span>{getTaskStatusLabel(status, task.scheduledTime ?? "", copy)}</span>
        {showTime ? <><span aria-hidden="true">·</span><span className="font-mono font-medium">{timeLabel}</span></> : null}
    </span>;
}

export function TodayTaskContent({ task, copy, status, timeLabel, disabled, onComplete, onBarrier, hero = false, phase, eyebrow }: {
    task: FeedTask; copy: TodayCopy; status: TaskCardStatus; timeLabel: string;
    disabled: boolean; onComplete: () => void; onBarrier: () => void;
    hero?: boolean; phase?: "saving" | "checked" | "leaving"; eyebrow?: string;
}) {
    const medication = task.type === FeedTaskType.MEDICATION;
    const actionable = status === "active" || status === "missed";
    const category = activityType(task);
    const instruction = medication ? task.description ?? copy.prescription : task.description || copy.activity[category];
    return <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
            {eyebrow ? <h2 className="font-mono text-xs uppercase tracking-[0.08em] text-muted">{eyebrow}</h2> : null}
            <TaskStatusPill status={status} task={task} copy={copy} timeLabel={timeLabel} />
        </div>
        <div className="flex items-start gap-3.5">
            <TodayTaskIcon task={task} large />
            <div className="min-w-0 flex-1 space-y-1 break-words [overflow-wrap:anywhere]">
                <h3 lang={task.contentLocale} className={`${hero ? heroTitleSize(task.name) : "text-xl"} font-semibold leading-tight tracking-[-0.01em] text-ink`}>{task.name}</h3>
                <WrittenIn task={task} copy={copy} />
                {instruction.trim() !== task.name.trim() ? <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-ink-2">{instruction}</p> : null}
                {!medication && task.frequency ? <p className="text-[13px] text-muted">{task.frequency}</p> : null}
            </div>
        </div>
        {task.carePlan ? <div className="space-y-2">
            {hero ? <ApprovalSeal>{task.provider?.name ? copy.approvedBy(task.provider.name) : copy.approved}</ApprovalSeal> : null}
            {/* One approval line: who approved it, then what kind of activity and which version. */}
            {!hero ? <div className="space-y-1 rounded-2xl bg-surface-2/70 p-3.5">
                <ApprovalSeal>{task.provider?.name ? copy.approvedBy(task.provider.name) : copy.approved}</ApprovalSeal>
                <p className="text-[13px] text-muted">{sentenceStart(getCarePlanCategoryLabel(task.carePlan.category, copy))} · {copy.planVersion(task.carePlan.versionNumber)}</p>
            </div> : null}
        </div> : medication && task.provider?.name ? <p className="text-[13px] text-muted">{copy.prescribedBy(task.provider.name)}</p> : null}
        {task.requiresScheduleConfiguration ? <div className="ma-press relative flex items-start gap-3 rounded-2xl bg-brand-tint/60 p-3.5 text-sm transition-colors hover:bg-brand-tint">
            <Icon name="bell" className="mt-0.5 h-5 w-5 shrink-0 text-brand" />
            <div className="min-w-0 flex-1 space-y-0.5">
                {/* Stretched link: the whole card is the tap target, the link text stays the accessible name. */}
                <Link href="/reminders" className="inline-flex min-h-6 items-center font-semibold text-brand after:absolute after:inset-0 after:rounded-2xl after:content-[''] hover:underline">{copy.setTime}</Link>
                <p className="text-ink-2">{copy.setupDetail}</p>
            </div>
            <Icon name="chevron" className="mt-0.5 h-4 w-4 shrink-0 self-center text-brand" />
        </div> : null}
        {actionable ? <div className="space-y-2">
            <button type="button" disabled={disabled} onClick={onComplete} className="ma-press flex min-h-[54px] w-full items-center justify-center gap-2 rounded-2xl bg-brand px-4 py-3 text-[17px] font-semibold text-white shadow-[0_10px_22px_-14px_rgba(20,116,101,.9)] hover:bg-brand-hover disabled:opacity-60">
                <svg viewBox="0 0 24 24" aria-hidden="true" className={`h-5 w-5 shrink-0 ${phase === "checked" || phase === "leaving" ? "ma-check-draw" : ""}`} fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path pathLength="1" d="M5 12.5l4.5 4.5L19 7" /></svg>
                {medication ? copy.taken : copy.done}
            </button>
            <button type="button" disabled={disabled} onClick={onBarrier} className="ma-press min-h-[46px] w-full rounded-[14px] bg-surface-2 px-3 py-3 text-[15px] font-medium text-ink-2 hover:bg-line-strong disabled:opacity-60">{copy.barrier}</button>
        </div> : null}
    </div>;
}

export function TodayTaskRow({ task, copy, status, timeLabel, disabled, onDetails, onComplete }: {
    task: FeedTask; copy: TodayCopy; status: TaskCardStatus; timeLabel: string;
    disabled: boolean; onDetails: () => void; onComplete: () => void;
}) {
    const canMarkDone = !task.requiresScheduleConfiguration && task.type !== FeedTaskType.MEDICATION && (status === "active" || status === "missed");
    const rawStatus = getTaskStatusLabel(status, task.scheduledTime ?? "", copy);
    const statusLabel = rawStatus.charAt(0).toLocaleUpperCase() + rawStatus.slice(1);
    const sub = task.frequency || task.description;
    return <li className="flex items-center gap-3 px-[14px] py-3">
        <button type="button" aria-label={`${copy.details}: ${task.name}`} onClick={onDetails} className="flex min-h-11 min-w-0 flex-1 items-center gap-3 rounded-xl text-left">
            <TodayTaskIcon task={task} />
            <span className="min-w-0 flex-1">
                <span lang={task.contentLocale} className={`line-clamp-2 break-words text-[15px] font-semibold leading-snug [overflow-wrap:anywhere] ${status === "completed" ? "text-muted" : "text-ink"}`}>{task.name}</span>
                {sub ? <span className="mt-0.5 line-clamp-1 break-words text-[13px] text-muted [overflow-wrap:anywhere]">{sub}</span> : null}
            </span>
        </button>
        <div className="flex max-w-[42%] shrink-0 flex-col items-end gap-1 text-right">
            {status === "completed"
                ? <span className="inline-flex items-center gap-1 text-[13px] font-semibold text-brand"><Icon name="check" className="h-4 w-4" />{statusLabel}</span>
                : canMarkDone
                    ? <button type="button" disabled={disabled} onClick={onComplete} className="ma-press relative before:absolute before:-inset-x-1 before:-inset-y-[7px] before:content-[''] min-h-[34px] rounded-[11px] bg-brand-tint px-3 py-1.5 text-[13px] font-semibold text-brand hover:bg-[#D3E8E1] disabled:opacity-60">{copy.done}</button>
                    : <span className={`text-[12px] font-medium ${status === "missed" ? "text-danger-ink" : status === "skipped" ? "text-note-ink" : "text-muted"}`}>{statusLabel}</span>}
            {task.requiresScheduleConfiguration && !task.scheduledTime
                ? <Link href="/reminders" className="-my-1 inline-flex min-h-10 items-center text-[13px] font-medium leading-tight text-brand hover:underline">{copy.setTime}</Link>
                : status !== "completed" ? <span className="font-mono text-[13px] text-ink-2">{timeLabel}</span> : null}
        </div>
    </li>;
}
