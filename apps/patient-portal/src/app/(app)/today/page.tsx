"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { getTodayCopy, type TodayCopy } from "@/content/today-copy";
import { resolveVisitsTimezone } from "@/content/visits-copy";
import { HiOutlineArrowPath, HiOutlineCalendarDays, HiOutlineInformationCircle } from "react-icons/hi2";
import { TodayTaskContent, TodayTaskRow } from "@/components/features/today-presentation";
import { Icon } from "@/components/ui/icons";
import { PullToRefresh } from "@/components/ui/pull-to-refresh";
import type { TaskCardStatus } from "@/components/features/task-card.types";
import { EmptyState, ErrorState, Modal, Skeleton } from "@/components/ui";
import { useFeedData } from "@/hooks/use-feed-data";
import { usePatientProfile } from "@/hooks/use-patient-profile";
import { usePatientShell } from "@/contexts/patient-shell-context";
import { FeedTaskStatus, normalizeLocale, type Locale, type FeedTask } from "@/types";

function mapTaskStatus(task: FeedTask, now: number): TaskCardStatus {
    const status = task.status;
    if (status === FeedTaskStatus.PENDING) {
        if (task.scheduledTime && (!task.scheduledAt || !Number.isFinite(Date.parse(task.scheduledAt)) || Date.parse(task.scheduledAt) > now)) {
            return "upcoming";
        }
        return "active";
    }

    if (status === FeedTaskStatus.SKIPPED) {
        return "skipped";
    }

    return status;
}

function formatTimeLabel(
    locale: Locale,
    copy: TodayCopy,
    scheduledTime?: string,
    status?: TaskCardStatus,
    requiresScheduleConfiguration?: boolean,
) {
    if (!scheduledTime && requiresScheduleConfiguration) {
        return copy.setTime;
    }
    if (!scheduledTime) {
        return copy.anyTime;
    }

    const [hours = "0", minutes = "0"] = scheduledTime.split(":");
    // The feed already supplies the patient-local clock time; avoid browser DST shifts.
    const value = new Date(0);
    value.setUTCHours(Number(hours), Number(minutes), 0, 0);
    const label = value.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit", timeZone: "UTC" });
    return status === "active" ? `${label} • ${copy.now}` : label;
}

export default function TodayPage() {
    const { setConversationOpen } = usePatientShell();
    const profile = usePatientProfile();
    const locale = normalizeLocale(profile?.preferredLanguage);
    const copy = getTodayCopy(locale);
    const nextUpLabel = locale === "es-MX" ? "Siguiente actividad" : "Next up";
    const { timezone } = resolveVisitsTimezone(profile?.timezone);
    const [now, setNow] = useState(() => Date.now());
    useEffect(() => {
        const timer = setInterval(() => setNow(Date.now()), 30_000);
        return () => clearInterval(timer);
    }, []);
    const {
        adherenceStats, actionError, submitting, error, loading,
        markComplete, reportBarrier, refreshFeed, summary, tasks,
    } = useFeedData(locale);
    const [barrierTask, setBarrierTask] = useState<FeedTask | null>(null);
    const [barrierNote, setBarrierNote] = useState("");
    const [detailsId, setDetailsId] = useState<string | null>(null);
    const [progressOpen, setProgressOpen] = useState(false);
    const [completion, setCompletion] = useState<{ task: FeedTask; phase: "saving" | "checked" | "leaving" } | null>(null);
    const inFlight = useRef(false);
    const mounted = useRef(true);
    useEffect(() => {
        mounted.current = true;
        return () => { mounted.current = false; };
    }, []);
    useEffect(() => {
        if (!completion || completion.phase === "saving") return;
        const timer = setTimeout(() => {
            if (completion.phase === "checked") setCompletion({ ...completion, phase: "leaving" });
            else { setCompletion(null); inFlight.current = false; }
        }, 160);
        return () => clearTimeout(timer);
    }, [completion]);

    const displayName = profile?.firstName ?? "";
    const avatarInitial = displayName.charAt(0).toUpperCase() || "?";
    const completedLabel = copy.completed(summary.completed, summary.total || tasks.length);
    // Keep feed order and the existing eligibility rules; the hero is only a presentation choice.
    const nextTask = completion?.task ?? tasks.find((task) => {
        const status = mapTaskStatus(task, now);
        return status === "active" || status === "missed";
    });
    const remainingTasks = tasks.filter((task) => task.id !== nextTask?.id);
    const detailTask = tasks.find((task) => task.id === detailsId);
    const nextReminder = tasks.find((task) => mapTaskStatus(task, now) === "upcoming" && task.scheduledTime);
    const disabled = submitting || Boolean(completion);

    async function complete(task: FeedTask) {
        if (inFlight.current || submitting) return;
        inFlight.current = true;
        setCompletion({ task, phase: "saving" });
        try {
            const saved = await markComplete(task);
            if (!mounted.current) return;
            if (saved === true && !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
                setCompletion({ task, phase: "checked" });
            } else {
                setCompletion(null);
                inFlight.current = false;
            }
        } catch {
            // The existing hook owns save errors. A rejected or unconfirmed save never animates.
            if (mounted.current) setCompletion(null);
            inFlight.current = false;
        }
    }

    function openBarrier(task: FeedTask) {
        setDetailsId(null);
        setBarrierTask(task);
    }

    async function sendBarrier(code: "side_effects" | "cost" | "access" | "schedule" | "confusion" | "other") {
        if (barrierTask && await reportBarrier(barrierTask, code, barrierNote)) {
            setBarrierTask(null);
            setBarrierNote("");
        }
    }

    if (loading && tasks.length === 0) {
        return (
            <div className="patient-page space-y-4 px-5 py-10" aria-busy="true">
                <p role="status" className="sr-only">{copy.loading}</p>
                <Skeleton className="h-24 w-full" variant="rect" />
                <Skeleton className="h-28 w-full" variant="rect" />
                <Skeleton className="h-28 w-full" variant="rect" />
            </div>
        );
    }

    return (
        <PullToRefresh onRefresh={refreshFeed} busy={loading} label={copy.refresh}>
        <div className="patient-page pb-8">
            <header className="flex items-start justify-between gap-3 px-[22px] pt-5">
                <div className="min-w-0">
                    <p className="text-sm text-muted">{new Date(now).toLocaleDateString(locale, { timeZone: timezone, day: "numeric", month: "long", weekday: "long" })}</p>
                    <h1 className="mt-1 break-words text-[28px] font-semibold leading-tight tracking-[-0.02em] text-ink">{displayName ? copy.greeting(displayName) : copy.hello}</h1>
                </div>
                <div aria-hidden="true" className="flex h-[42px] w-[42px] shrink-0 items-center justify-center rounded-full bg-brand-tint font-semibold text-brand">{avatarInitial}</div>
            </header>

            <section aria-label={copy.progress} className="space-y-2 px-[22px] pt-[18px]">
                <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 text-[13px] text-muted">
                    <p className="font-medium text-ink">{completedLabel}</p>
                    {nextReminder ? <p className="ml-auto">{locale === "es-MX" ? "Próximo recordatorio" : "Next reminder"} <span className="font-mono">{formatTimeLabel(locale, copy, nextReminder.scheduledTime)}</span></p> : null}
                    <button type="button" aria-label={copy.progressHelp} onClick={() => setProgressOpen(true)} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-muted"><HiOutlineInformationCircle aria-hidden="true" className="h-5 w-5" /></button>
                </div>
                <div className="grid gap-[5px]" style={{ gridTemplateColumns: `repeat(${Math.max(tasks.length, 1)}, minmax(0, 1fr))` }} aria-hidden="true" data-testid="today-progress-segments">
                    {tasks.map((task) => <span key={task.id} data-status={task.status} className="h-1.5 overflow-hidden rounded-[3px] bg-[#DCD5CA]">
                        <span className={`block h-full rounded-[3px] transition-[width] duration-[240ms] ease-[cubic-bezier(.2,.8,.2,1)] ${task.status === FeedTaskStatus.MISSED ? "bg-[#E39A86]" : "bg-brand"}`} style={{ width: task.status === FeedTaskStatus.COMPLETED || task.status === FeedTaskStatus.MISSED ? "100%" : "0%" }} />
                    </span>)}
                </div>
                <div className="flex flex-wrap justify-between gap-2 text-[13px] text-muted">
                    {adherenceStats.currentStreakDays > 0 ? <p>{copy.streak(adherenceStats.currentStreakDays)}</p> : null}
                </div>
            </section>

            <div className="space-y-4 pt-[18px]">
                {remainingTasks.length === 0 ? <h2 className="sr-only">{copy.schedule}</h2> : null}
                {actionError && !barrierTask ? <p role="alert" className="mx-4 rounded-xl bg-danger-tint p-4 text-danger-ink">{actionError}</p> : null}
                {error ? <div className="mx-4"><ErrorState description={error} action={<button className="min-h-11 rounded-2xl border border-line-strong bg-surface px-4 py-2 text-sm font-semibold text-danger-ink" onClick={refreshFeed} type="button">{copy.retry}</button>} title={tasks.length > 0 ? copy.stale : copy.loadError} /></div> : null}
                {!error && tasks.length === 0 ? <div className="mx-4"><EmptyState description={copy.emptyDetail} icon={<HiOutlineCalendarDays />} title={copy.empty} /></div> : null}
                {nextTask ? <article aria-label={nextUpLabel} data-completion-phase={completion?.phase ?? "idle"} className={`mx-4 space-y-4 rounded-[28px] bg-surface p-5 shadow-[var(--shadow-raised)] ${completion?.phase === "leaving" ? "ma-leave" : "ma-enter-spring"}`} key={nextTask.id}>
                    <h2 className="font-mono text-xs uppercase tracking-[0.08em] text-muted">{nextUpLabel}</h2>
                    <TodayTaskContent task={nextTask} copy={copy} status={mapTaskStatus(nextTask, now)} timeLabel={formatTimeLabel(locale, copy, nextTask.scheduledTime, mapTaskStatus(nextTask, now), nextTask.requiresScheduleConfiguration)} disabled={disabled} onComplete={() => void complete(nextTask)} onBarrier={() => openBarrier(nextTask)} hero phase={completion?.phase} />
                    <button type="button" onClick={() => setDetailsId(nextTask.id)} className="min-h-11 w-full text-left text-sm font-medium text-brand underline underline-offset-4">{copy.details}</button>
                </article> : null}
                {remainingTasks.length > 0 ? <section aria-label={copy.schedule}>
                    <h2 className="mb-2 px-[22px] font-mono text-xs uppercase tracking-[0.08em] text-muted">{copy.schedule}</h2>
                    <ul className="mx-4 rounded-[22px] bg-surface">
                        {remainingTasks.map((task) => <TodayTaskRow key={task.id} task={task} copy={copy} status={mapTaskStatus(task, now)} timeLabel={formatTimeLabel(locale, copy, task.scheduledTime, mapTaskStatus(task, now), task.requiresScheduleConfiguration)} disabled={disabled} onDetails={() => setDetailsId(task.id)} onComplete={() => void complete(task)} />)}
                    </ul>
                </section> : null}
                <div className="flex flex-wrap items-center justify-between gap-2 px-[22px]">
                    <p className="text-[13px] text-muted">{copy.count(tasks.length)}</p>
                    <button aria-label={loading ? copy.refreshing : copy.refresh} aria-busy={loading} disabled={loading || disabled} className="flex min-h-11 items-center gap-2 rounded-xl bg-surface-2 px-3 py-2 text-sm font-medium text-ink-2 disabled:opacity-50" onClick={refreshFeed} type="button"><HiOutlineArrowPath aria-hidden="true" className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /><span>{loading ? copy.refreshing : copy.refresh}</span></button>
                </div>
            </div>

            <div className="px-4 pt-5">
                <Link href="/chat" onClick={(event) => { if (!event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) setConversationOpen(true); }} className="flex min-h-11 items-center gap-3 rounded-[22px] bg-surface px-[14px] py-[13px]">
                    <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[13px] bg-brand-deep text-gold"><Icon name="spark" className="h-5 w-5" /></span>
                    <span className="min-w-0 flex-1"><span className="block text-[15px] font-semibold text-ink">{copy.symptom}</span><span className="block text-[13px] text-muted">{copy.symptomDetail}</span></span>
                    <Icon name="arrow" className="h-5 w-5 shrink-0 text-brand" />
                </Link>
            </div>
            <Modal closeLabel={copy.close} onClose={() => setProgressOpen(false)} open={progressOpen} title={copy.progressHelp}><p className="text-sm text-ink-2">{copy.progressDetail}</p></Modal>
            <Modal closeLabel={copy.close} onClose={() => setDetailsId(null)} open={Boolean(detailTask)} title={copy.details}>
                {detailTask ? <TodayTaskContent task={detailTask} copy={copy} status={mapTaskStatus(detailTask, now)} timeLabel={formatTimeLabel(locale, copy, detailTask.scheduledTime, mapTaskStatus(detailTask, now), detailTask.requiresScheduleConfiguration)} disabled={disabled} onComplete={() => { setDetailsId(null); void complete(detailTask); }} onBarrier={() => openBarrier(detailTask)} /> : null}
            </Modal>
            <Modal
                closeLabel={copy.close}
                onClose={() => { if (!submitting) { setBarrierTask(null); setBarrierNote(""); } }}
                open={Boolean(barrierTask)}
                title={copy.barrierTitle}
            >
                <div className="space-y-3">
                    {actionError ? <p role="alert" className="rounded-lg bg-danger-tint p-3 text-danger-ink">{actionError}</p> : null}
                    <p className="text-sm text-muted">{copy.barrierDetail}</p>
                    <div className="grid grid-cols-2 gap-2">
                        {(["side_effects", "cost", "access", "schedule", "confusion"] as const).map((code) => (
                            <button disabled={submitting} className="min-h-11 rounded-xl border border-line-strong px-3 py-2 text-sm font-semibold text-brand" key={code} onClick={() => void sendBarrier(code)} type="button">{copy.barriers[code]}</button>
                        ))}
                    </div>
                    <label className="block text-sm font-semibold text-ink">{copy.barriers.other}<textarea className="mt-1 min-h-20 w-full rounded-xl border border-line-strong p-2 font-normal" value={barrierNote} onChange={(event) => setBarrierNote(event.target.value)} /></label>
                    <button className="min-h-11 w-full rounded-xl bg-brand px-3 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={submitting || !barrierNote.trim()} onClick={() => void sendBarrier("other")} type="button">{submitting ? copy.saving : copy.send}</button>
                </div>
            </Modal>
        </div>
        </PullToRefresh>
    );
}
