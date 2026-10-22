"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getTodayCopy, getTodayErrorMessage, type TodayCopy } from "@/content/today-copy";
import { useInitialPatientLocale } from "@/contexts/patient-locale-context";
import { resolveVisitsTimezone } from "@/content/visits-copy";
import { TodayTaskContent, TodayTaskRow } from "@/components/features/today-presentation";
import { Icon } from "@/components/ui/icons";
import { IconTile } from "@/components/ui/list";
import { OverflowMenu } from "@/components/ui/overflow-menu";
import { PullToRefresh } from "@/components/ui/pull-to-refresh";
import type { TaskCardStatus } from "@/components/features/task-card.types";
import { EmptyState, ErrorState, Modal, Skeleton } from "@/components/ui";
import { useFeedData } from "@/hooks/use-feed-data";
import { usePatientProfile } from "@/hooks/use-patient-profile";
import { usePatientShell } from "@/contexts/patient-shell-context";
import { FeedTaskStatus, normalizeLocale, type Locale, type FeedTask } from "@/types";
import { ApprovedPlanDetails } from "@/components/features/approved-plan-details";
import { NotificationBell } from "@/components/features/notification-centre";
import { ADRFollowUpEntryRow } from "@/components/features/adr-follow-up-entry-row";
import { MedicationQuestionCards } from "@/components/features/medication-question-cards";
import { CareTeamFilterChips, ContactClinicCard, hasMultipleOwners, taskMatchesFilter } from "@/components/features/care-team-owner";
import { getCareTeamCopy } from "@/content/care-team-copy";

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
    return value.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit", timeZone: "UTC" });
}

function segmentClass(status: FeedTask["status"]) {
    if (status === FeedTaskStatus.COMPLETED) return "bg-brand";
    if (status === FeedTaskStatus.MISSED) return "bg-danger-seg";
    if (status === FeedTaskStatus.SKIPPED) return "bg-[#D9B783]";
    return "bg-brand";
}

export default function TodayPage() {
    const params = useSearchParams();
    const activityId = params.get("activity");
    const planDestination = params.get("view") === "care-plan";
    const handledActivity = useRef<string | null>(null);
    const [planOpen, setPlanOpen] = useState(planDestination);
    useEffect(() => { setPlanOpen(planDestination); }, [planDestination]);
    const { setConversationOpen } = usePatientShell();
    const profile = usePatientProfile();
    const initialLocale = useInitialPatientLocale();
    const locale = normalizeLocale(profile?.preferredLanguage ?? initialLocale);
    const copy = getTodayCopy(locale);
    const spanish = locale === "es-MX";
    const nextUpLabel = spanish ? "Siguiente actividad" : "Next up";
    const { timezone } = resolveVisitsTimezone(profile?.timezone);
    const [now, setNow] = useState(() => Date.now());
    useEffect(() => {
        const timer = setInterval(() => setNow(Date.now()), 30_000);
        return () => clearInterval(timer);
    }, []);
    const {
        adherenceStats, actionError, submitting, error, loading,
        markComplete, reportBarrier, refreshFeed, summary, tasks, careTeamFilters = [], contactClinic = false,
    } = useFeedData(locale);
    const careCopy = getCareTeamCopy(locale);
    const showOwner = hasMultipleOwners(tasks, careTeamFilters);
    const [careTeamFilter, setCareTeamFilter] = useState("all");
    const [barrierTask, setBarrierTask] = useState<FeedTask | null>(null);
    const [barrierNote, setBarrierNote] = useState("");
    const [detailsId, setDetailsId] = useState<string | null>(null);
    const [activityGroupId, setActivityGroupId] = useState<string | null>(null);
    const matchingActivities = tasks.filter((task) => task.targetId === activityId);
    const exactActivity = tasks.find((task) => task.id === activityId) ?? (matchingActivities.length === 1 ? matchingActivities[0] : undefined);
    useEffect(() => {
        if (!activityId) { handledActivity.current = null; return; }
        if (loading || error || handledActivity.current === activityId) return;
        if (exactActivity) { handledActivity.current = activityId; setActivityGroupId(null); setDetailsId(exactActivity.id); }
        else if (matchingActivities.length > 1) { handledActivity.current = activityId; setDetailsId(null); setActivityGroupId(activityId); }
        else { setDetailsId(null); setActivityGroupId(null); }
    }, [activityId, exactActivity, matchingActivities.length, loading, error]);
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
    const filterAvailable = showOwner && careTeamFilter !== "all" && careTeamFilters.some((option) => (option.care_team_id ?? "unowned") === careTeamFilter);
    const visibleTasks = filterAvailable ? tasks.filter((task) => taskMatchesFilter(task, careTeamFilter)) : tasks;
    const nextTask = completion?.task ?? visibleTasks.find((task) => {
        const status = mapTaskStatus(task, now);
        return status === "active" || status === "missed";
    });
    const remainingTasks = visibleTasks.filter((task) => task.id !== nextTask?.id);
    const detailTask = tasks.find((task) => task.id === detailsId);
    const nextReminder = visibleTasks.find((task) => mapTaskStatus(task, now) === "upcoming" && task.scheduledTime);
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
            <div className="patient-page px-[22px] pt-5" aria-busy="true">
                <p role="status" className="sr-only">{copy.loading}</p>
                <div className="space-y-2 pb-5">
                    <Skeleton className="h-4 w-32" variant="text" />
                    <Skeleton className="h-8 w-52" variant="text" />
                </div>
                <div className="-mx-1.5 space-y-4">
                    <Skeleton className="h-[260px] w-full !rounded-[28px]" variant="rect" />
                    <Skeleton className="h-36 w-full" variant="rect" />
                </div>
            </div>
        );
    }

    return (
        <PullToRefresh onRefresh={refreshFeed} busy={loading} label={copy.refresh}>
        <div className="patient-page pb-6">
            <header className="flex items-start justify-between gap-3 px-[22px] pt-5">
                <div className="min-w-0">
                    <p className="text-sm text-muted first-letter:uppercase">{new Date(now).toLocaleDateString(locale, { timeZone: timezone, day: "numeric", month: "long", weekday: "long" })}</p>
                    <h1 className="mt-0.5 break-words text-[28px] font-semibold leading-tight tracking-[-0.02em] text-ink">{displayName ? copy.greeting(displayName) : copy.hello}</h1>
                </div>
                <div className="flex shrink-0 items-center gap-1.5 pt-1">
                    <NotificationBell />
                    <OverflowMenu label={spanish ? "Más opciones" : "More options"} items={[
                        { label: loading ? copy.refreshing : copy.refresh, icon: "refresh", onSelect: refreshFeed, disabled: loading || disabled, busy: loading },
                        { label: copy.progressHelp, icon: "info", onSelect: () => setProgressOpen(true) },
                    ]} />
                    <div aria-hidden="true" className="flex h-[42px] w-[42px] items-center justify-center rounded-full bg-brand-tint text-[17px] font-semibold text-brand">{avatarInitial}</div>
                </div>
            </header>

            <section aria-label={copy.progress} className="px-[22px] pt-4">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted">
                    <p className="font-medium text-ink-2">{completedLabel}</p>
                    {adherenceStats.currentStreakDays > 0 ? <p className="inline-flex items-center gap-1 text-brand-ink"><span aria-hidden="true" className="h-1 w-1 rounded-full bg-brand" />{copy.streak(adherenceStats.currentStreakDays)}</p> : null}
                    <div className="ml-auto flex items-center gap-1">
                        {nextReminder ? <p>{spanish ? "Próximo recordatorio" : "Next reminder"} <span className="font-mono text-ink-2">{formatTimeLabel(locale, copy, nextReminder.scheduledTime)}</span></p> : null}
                        <button type="button" aria-label={copy.progressHelp} onClick={() => setProgressOpen(true)} className="-mr-2.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-muted hover:text-ink"><Icon name="info" className="h-[18px] w-[18px]" /></button>
                    </div>
                </div>
                <div className="grid gap-[5px]" style={{ gridTemplateColumns: `repeat(${Math.max(tasks.length, 1)}, minmax(0, 1fr))` }} aria-hidden="true" data-testid="today-progress-segments">
                    {tasks.map((task) => <span key={task.id} data-status={task.status} className="h-1.5 overflow-hidden rounded-[3px] bg-idle-seg">
                        <span className={`block h-full rounded-[3px] transition-[width] duration-[240ms] ease-[cubic-bezier(.2,.8,.2,1)] ${segmentClass(task.status)}`} style={{ width: task.status === FeedTaskStatus.COMPLETED || task.status === FeedTaskStatus.MISSED || task.status === FeedTaskStatus.SKIPPED ? "100%" : "0%" }} />
                    </span>)}
                </div>
            </section>

            <div className="space-y-5 pt-[18px]">
                <MedicationQuestionCards locale={locale} />
                <div className="px-4 empty:hidden"><ADRFollowUpEntryRow locale={locale} /></div>
                {showOwner && careTeamFilters.length > 0 ? <CareTeamFilterChips filters={careTeamFilters} value={filterAvailable ? careTeamFilter : "all"} onChange={setCareTeamFilter} locale={locale} /> : null}
                {contactClinic ? <ContactClinicCard locale={locale} /> : null}
                {tasks.length > 0 && visibleTasks.length === 0 ? <div className="mx-4 flex flex-wrap items-center gap-3 rounded-[22px] bg-surface p-4 text-[15px] text-ink-2"><p role="status" className="min-w-0 flex-1">{careCopy.filterEmpty}</p><button type="button" onClick={() => setCareTeamFilter("all")} className="ma-press min-h-11 rounded-[14px] bg-surface-2 px-4 text-sm font-semibold text-ink-2 hover:bg-line-strong">{careCopy.filterEmptyAction}</button></div> : null}
                {activityId && !loading && !error && !exactActivity && matchingActivities.length === 0 && <p role="alert" className="mx-4 rounded-2xl bg-danger-tint p-3 text-sm text-danger-ink">{spanish ? "Esta actividad no está disponible hoy. Actualiza tus actividades." : "This activity is unavailable today. Refresh your activities."}</p>}
                {remainingTasks.length === 0 ? <h2 className="sr-only">{copy.schedule}</h2> : null}
                {actionError && !barrierTask ? <p role="alert" className="mx-4 flex items-start gap-2.5 rounded-2xl bg-danger-tint p-3.5 text-sm text-danger-ink"><Icon name="alert" className="h-5 w-5 shrink-0" />{actionError}</p> : null}
                {error ? <div className="mx-4"><ErrorState description={getTodayErrorMessage(error, locale)} action={<button className="ma-press min-h-11 rounded-[14px] bg-surface-2 px-4 py-2 text-sm font-semibold text-ink-2 hover:bg-line-strong" onClick={refreshFeed} type="button">{copy.retry}</button>} title={tasks.length > 0 ? copy.stale : copy.loadError} /></div> : null}
                {!error && tasks.length === 0 ? <div className="mx-4 rounded-[22px] bg-surface"><EmptyState description={copy.emptyDetail} icon={<Icon name="cal" />} title={copy.empty} /></div> : null}
                {nextTask ? <article aria-label={nextUpLabel} data-completion-phase={completion?.phase ?? "idle"} className={`mx-4 rounded-[28px] bg-surface p-5 shadow-[var(--shadow-raised)] ${completion?.phase === "leaving" ? "ma-leave" : "ma-enter-spring"}`} key={nextTask.id}>
                    <TodayTaskContent task={nextTask} copy={copy} eyebrow={nextUpLabel} status={mapTaskStatus(nextTask, now)} timeLabel={formatTimeLabel(locale, copy, nextTask.scheduledTime, nextTask.requiresScheduleConfiguration)} disabled={disabled} onComplete={() => void complete(nextTask)} onBarrier={() => openBarrier(nextTask)} hero phase={completion?.phase} showOwner={showOwner} />
                    <button type="button" onClick={() => setDetailsId(nextTask.id)} className="mt-3 -mb-1 flex min-h-11 w-full items-center justify-center gap-1 rounded-xl text-sm font-medium text-brand hover:bg-brand-tint/50">{copy.details}<Icon name="chevron" className="h-4 w-4" /></button>
                </article> : null}
                {remainingTasks.length > 0 ? <section aria-label={copy.schedule}>
                    <h2 className="px-[22px] pb-2 text-[15px] font-semibold text-ink">{copy.schedule}</h2>
                    <ul className="mx-4 overflow-hidden rounded-[22px] bg-surface [&>li+li]:border-t [&>li+li]:border-line">
                        {remainingTasks.map((task) => <TodayTaskRow key={task.id} task={task} copy={copy} status={mapTaskStatus(task, now)} timeLabel={formatTimeLabel(locale, copy, task.scheduledTime, task.requiresScheduleConfiguration)} disabled={disabled} onDetails={() => setDetailsId(task.id)} onComplete={() => void complete(task)} showOwner={showOwner} />)}
                    </ul>
                </section> : null}
                <div className="px-4">
                    <Link href="/chat" onClick={(event) => { if (!event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) setConversationOpen(true); }} className="ma-press flex min-h-11 items-center gap-3 rounded-[22px] bg-surface px-[14px] py-[13px] hover:bg-[#FFFBF4]">
                        <IconTile icon="spark" tone="assistant" />
                        <span className="min-w-0 flex-1"><span className="block text-[15px] font-semibold text-ink">{copy.symptom}</span><span className="block text-[13px] leading-snug text-muted">{copy.symptomDetail}</span></span>
                        <Icon name="chevron" className="h-5 w-5 shrink-0 text-muted" />
                    </Link>
                </div>
            </div>

            <Modal closeLabel={copy.close} onClose={() => setProgressOpen(false)} open={progressOpen} title={copy.progressHelp}><p className="text-[15px] leading-relaxed text-ink-2">{copy.progressDetail}</p></Modal>
            <Modal closeLabel={copy.close} onClose={() => setPlanOpen(false)} open={planOpen} title={copy.details}>{planOpen && <ApprovedPlanDetails locale={locale} />}</Modal>
            <Modal closeLabel={copy.close} onClose={() => setActivityGroupId(null)} open={Boolean(activityGroupId && tasks.some((task) => task.targetId === activityGroupId))} title={copy.details}>
                <div className="space-y-6">{tasks.filter((task) => task.targetId === activityGroupId).map((task) => <TodayTaskContent key={task.id} task={task} copy={copy} status={mapTaskStatus(task, now)} timeLabel={formatTimeLabel(locale, copy, task.scheduledTime, task.requiresScheduleConfiguration)} disabled={disabled} onComplete={() => { setActivityGroupId(null); void complete(task); }} onBarrier={() => { setActivityGroupId(null); openBarrier(task); }} showOwner={showOwner} />)}</div>
            </Modal>
            <Modal closeLabel={copy.close} onClose={() => setDetailsId(null)} open={Boolean(detailTask)} title={copy.details}>
                {detailTask ? <TodayTaskContent task={detailTask} copy={copy} status={mapTaskStatus(detailTask, now)} timeLabel={formatTimeLabel(locale, copy, detailTask.scheduledTime, detailTask.requiresScheduleConfiguration)} disabled={disabled} onComplete={() => { setDetailsId(null); void complete(detailTask); }} onBarrier={() => openBarrier(detailTask)} showOwner={showOwner} /> : null}
            </Modal>
            <Modal
                closeLabel={copy.close}
                onClose={() => { if (!submitting) { setBarrierTask(null); setBarrierNote(""); } }}
                open={Boolean(barrierTask)}
                title={copy.barrierTitle}
            >
                <div className="space-y-4">
                    {actionError ? <p role="alert" className="rounded-2xl bg-danger-tint p-3.5 text-sm text-danger-ink">{actionError}</p> : null}
                    {barrierTask ? <p className="text-[15px] font-semibold text-ink">{barrierTask.name}</p> : null}
                    <p className="text-[15px] leading-relaxed text-muted">{copy.barrierDetail}</p>
                    <div className="grid grid-cols-2 gap-2">
                        {(["side_effects", "cost", "access", "schedule", "confusion"] as const).map((code) => (
                            <button disabled={submitting} className="ma-press min-h-12 rounded-2xl border border-line-strong bg-surface px-3 py-2 text-[15px] font-semibold text-ink-2 hover:border-brand/40 hover:bg-brand-tint/50 hover:text-brand-ink disabled:opacity-50" key={code} onClick={() => void sendBarrier(code)} type="button">{copy.barriers[code]}</button>
                        ))}
                    </div>
                    <label className="block text-sm font-semibold text-ink-2">{copy.barriers.other}<textarea className="mt-2 min-h-24 w-full rounded-2xl border border-line-strong bg-surface p-3.5 text-base font-normal text-ink outline-none transition placeholder:text-muted focus:border-brand focus:ring-4 focus:ring-brand/15" value={barrierNote} onChange={(event) => setBarrierNote(event.target.value)} /></label>
                    <button className="ma-press min-h-[52px] w-full rounded-2xl bg-brand px-4 py-3 text-base font-semibold text-white hover:bg-brand-hover disabled:opacity-50" disabled={submitting || !barrierNote.trim()} onClick={() => void sendBarrier("other")} type="button">{submitting ? copy.saving : copy.send}</button>
                </div>
            </Modal>
        </div>
        </PullToRefresh>
    );
}
