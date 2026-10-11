import Link from "next/link";
import type { TodayCopy } from "@/content/today-copy";
import { getCarePlanCategoryLabel, getTaskStatusLabel } from "@/content/today-copy";
import { ApprovalSeal } from "@/components/ui/approval-seal";
import { Icon, type IconName } from "@/components/ui/icons";
import type { TaskCardStatus } from "./task-card.types";
import { FeedTaskType, type FeedTask } from "@/types";

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

export function TodayTaskIcon({ task, large = false }: { task: FeedTask; large?: boolean }) {
    let name: IconName = "check";
    let color = "bg-surface-2 text-ink-2";
    if (task.type === FeedTaskType.MEDICATION) { name = "pill"; color = "bg-med-tint text-med-ink"; }
    else if (task.carePlan?.category === "monitoring") { name = "gauge"; color = "bg-lab-tint text-lab-ink"; }
    else if (task.carePlan?.category === "hydration") { name = "drop"; color = "bg-hyd-tint text-hyd-ink"; }
    else if (task.carePlan?.category === "movement") { name = "walk"; color = "bg-brand-tint text-brand"; }
    return <span className={`flex shrink-0 items-center justify-center ${color} ${large ? "h-[52px] w-[52px] rounded-2xl" : "h-10 w-10 rounded-xl"}`}><Icon name={name} className={large ? "h-6 w-6" : "h-5 w-5"} /></span>;
}

export function TodayTaskContent({ task, copy, status, timeLabel, disabled, onComplete, onBarrier, hero = false, phase }: {
    task: FeedTask; copy: TodayCopy; status: TaskCardStatus; timeLabel: string;
    disabled: boolean; onComplete: () => void; onBarrier: () => void;
    hero?: boolean; phase?: "saving" | "checked" | "leaving";
}) {
    const medication = task.type === FeedTaskType.MEDICATION;
    const actionable = status === "active" || status === "missed";
    const category = activityType(task);
    const instruction = medication ? task.description ?? copy.prescription : task.description || copy.activity[category];
    return <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2 text-[13px]">
            {!task.requiresScheduleConfiguration || task.scheduledTime ? <span className="font-mono text-muted">{timeLabel}</span> : null}
            <span className={`rounded-full px-2.5 py-1 font-semibold ${status === "missed" ? "bg-danger-tint text-danger-ink" : status === "active" || status === "completed" ? "bg-brand-tint text-brand-ink" : "bg-surface-2 text-ink-2"}`}>{getTaskStatusLabel(status, task.scheduledTime ?? "", copy)}</span>
        </div>
        <div className="flex items-start gap-3.5">
            <TodayTaskIcon task={task} large />
            <div className="min-w-0 flex-1 space-y-1 break-words">
                <h3 className="text-[22px] font-semibold leading-tight tracking-[-0.01em] text-ink">{task.name}</h3>
                {instruction.trim() !== task.name.trim() ? <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-ink-2">{instruction}</p> : null}
                {!medication && task.frequency ? <p className="text-[13px] text-muted">{task.frequency}</p> : null}
                <p className="text-xs text-muted">{medication ? "Rx" : copy.types[category]}</p>
            </div>
        </div>
        {task.carePlan ? <div className="space-y-2">
            {hero ? <ApprovalSeal>{task.provider?.name ? copy.approvedBy(task.provider.name) : copy.approved}</ApprovalSeal> : null}
            {!hero ? <p className="text-xs text-muted">{copy.approved} • {getCarePlanCategoryLabel(task.carePlan.category, copy)}</p> : null}
            {!hero ? <><p className="text-sm text-ink-2">{copy.planDetail(task.carePlan.versionNumber)}</p>{task.provider?.name ? <p className="text-sm text-brand-ink">{copy.approvedBy(task.provider.name)}</p> : null}</> : null}
        </div> : medication && task.provider?.name ? <p className="text-sm text-brand-ink">{copy.prescribedBy(task.provider.name)}</p> : null}
        {task.requiresScheduleConfiguration ? <div className="space-y-1 text-sm"><Link href="/reminders" className="inline-flex min-h-11 items-center font-semibold text-brand underline underline-offset-4">{copy.setTime}</Link><p className="text-muted">{copy.setupDetail}</p></div> : null}
        {actionable ? <div className="space-y-2">
            <button type="button" disabled={disabled} onClick={onComplete} className="ma-press flex min-h-[54px] w-full items-center justify-center gap-2 rounded-2xl bg-brand px-4 py-3 text-[17px] font-semibold text-white hover:bg-brand-hover disabled:opacity-60">
                <svg viewBox="0 0 24 24" aria-hidden="true" className={`h-5 w-5 shrink-0 ${phase === "checked" || phase === "leaving" ? "ma-check-draw" : ""}`} fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path pathLength="1" d="M5 12.5l4.5 4.5L19 7" /></svg>
                {medication ? copy.taken : copy.done}
            </button>
            <button type="button" disabled={disabled} onClick={onBarrier} className="ma-press min-h-[46px] w-full rounded-[14px] bg-surface-2 px-3 py-3 text-[15px] font-medium text-ink-2 disabled:opacity-60">{copy.barrier}</button>
        </div> : null}
    </div>;
}

export function TodayTaskRow({ task, copy, status, timeLabel, disabled, onDetails, onComplete }: {
    task: FeedTask; copy: TodayCopy; status: TaskCardStatus; timeLabel: string;
    disabled: boolean; onDetails: () => void; onComplete: () => void;
}) {
    return <li className="flex flex-wrap items-center gap-3 border-b border-line px-[14px] py-[13px] last:border-b-0">
        <button type="button" aria-label={`${copy.details}: ${task.name}`} onClick={onDetails} className="flex min-h-11 min-w-0 flex-1 basis-40 items-start gap-3 text-left">
            <TodayTaskIcon task={task} />
            <span className="min-w-0 flex-1 space-y-1 break-words">
                <span className="block text-[15px] font-semibold text-ink">{task.name}</span>
                {task.description ? <span className="block whitespace-pre-wrap text-[13px] text-ink-2">{task.description}</span> : null}
            </span>
            <span className="ml-auto flex min-w-0 max-w-[40%] shrink-0 flex-col items-end gap-1 break-words text-right text-[13px] text-muted">
                <span>{getTaskStatusLabel(status, task.scheduledTime ?? "", copy)}</span>
                {!task.requiresScheduleConfiguration ? <span className="font-mono">{timeLabel}</span> : null}
            </span>
        </button>
        {task.requiresScheduleConfiguration ? <Link href="/reminders" className="flex min-h-11 max-w-full items-center rounded-xl px-2 text-[13px] font-medium text-brand underline underline-offset-4">{copy.setTime}</Link> : task.type !== FeedTaskType.MEDICATION && (status === "active" || status === "missed") ? <button type="button" disabled={disabled} onClick={onComplete} className="ma-press min-h-11 max-w-full rounded-[11px] bg-brand-tint px-3 py-2 text-[13px] font-semibold text-brand disabled:opacity-60">{copy.done}</button> : null}
    </li>;
}
