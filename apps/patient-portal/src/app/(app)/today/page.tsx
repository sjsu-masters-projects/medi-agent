"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getCarePlanCategoryLabel, getTodayCopy, type TodayCopy } from "@/content/today-copy";
import { resolveVisitsTimezone } from "@/content/visits-copy";
import { HiOutlineArrowPath, HiOutlineCalendarDays, HiOutlineCheck, HiOutlineInformationCircle } from "react-icons/hi2";
import { CircularProgress, MedicationCard, ObligationCard } from "@/components/features";
import type { TaskCardStatus } from "@/components/features/task-card.types";
import { Card, EmptyState, ErrorState, Modal, Skeleton } from "@/components/ui";
import { useFeedData } from "@/hooks/use-feed-data";
import { usePatientProfile } from "@/hooks/use-patient-profile";
import { FeedTaskStatus, FeedTaskType, normalizeLocale, type Locale, type FeedTask } from "@/types";

function splitMedicationName(name: string) {
    const match = name.match(/^(.*?)(\s+\d.*)$/);
    return {
        dosage: match?.[2]?.trim() ?? "",
        name: match?.[1]?.trim() ?? name,
    };
}

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

function carePlanLabel(task: FeedTask, copy: TodayCopy) {
    if (!task.carePlan) {
        return null;
    }
    return `${copy.approved} • ${getCarePlanCategoryLabel(task.carePlan.category, copy)}`;
}

function CarePlanDetails({ task, copy }: { task: FeedTask; copy: TodayCopy }) {
    if (!task.carePlan) return null;
    return <details className="mb-3 text-xs text-slate-600"><summary className="cursor-pointer">{copy.details}</summary><p className="mt-1">{copy.planDetail(task.carePlan.versionNumber)}</p></details>;
}

export default function TodayPage() {
    const profile = usePatientProfile();
    const locale = normalizeLocale(profile?.preferredLanguage);
    const copy = getTodayCopy(locale);
    const { timezone } = resolveVisitsTimezone(profile?.timezone);
    const [now, setNow] = useState(() => Date.now());
    useEffect(() => {
        const timer = setInterval(() => setNow(Date.now()), 30_000);
        return () => clearInterval(timer);
    }, []);
    const {
        adherenceStats,
        actionError,
        submitting,
        error,
        loading,
        markComplete,
        reportBarrier,
        refreshFeed,
        summary,
        tasks,
    } = useFeedData(locale);
    const [barrierTask, setBarrierTask] = useState<FeedTask | null>(null);
    const [barrierNote, setBarrierNote] = useState("");
    const displayName = profile?.firstName ?? "";
    const avatarInitial = displayName.charAt(0).toUpperCase() || "?";
    const completionPercent = summary.total > 0
        ? Math.round(summary.completed / summary.total * 100)
        : 0;
    const completedLabel = copy.completed(summary.completed, summary.total || tasks.length);
    const hasScheduleGaps = tasks.some((task) => task.requiresScheduleConfiguration);

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
        <div className="patient-page pb-8">
            <div className="relative overflow-hidden rounded-b-[38px] bg-[#147465] px-6 pt-11 pb-7 text-white shadow-[0_24px_70px_rgba(20,116,101,0.25)]">
                <div className="absolute -top-16 -right-14 h-52 w-52 rounded-full bg-white/12" />
                <div className="absolute -bottom-20 left-5 h-56 w-56 rounded-full bg-[#d8aa57]/18" />
                <div className="relative flex items-start justify-between gap-4">
                    <div>
                        <p className="text-xs font-black uppercase tracking-[0.24em] text-white/68">{copy.today}</p>
                        <h1 className="mt-2 text-[2.35rem] font-black leading-none tracking-[-0.04em]">
                            {displayName ? copy.greeting(displayName) : copy.hello}
                        </h1>
                        <p className="mt-2 text-base text-white/82">
                            {new Date(now).toLocaleDateString(locale, {
                                timeZone: timezone,
                                day: "numeric",
                                month: "long",
                                weekday: "long",
                            })}
                        </p>
                    </div>
                    <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-[24px] bg-white text-lg font-black text-[#147465] shadow-sm">
                        {avatarInitial}
                    </div>
                </div>

                <div className="relative mt-6 flex items-center justify-between gap-4 rounded-[28px] border border-white/18 bg-white/15 p-5 backdrop-blur">
                    <div className="space-y-1">
                        <p className="text-xl font-black text-white">{copy.progress}</p>
                        <p className="text-base text-white/82">{completedLabel}</p>
                        {adherenceStats.currentStreakDays > 0 ? <p className="text-sm font-semibold text-white/76">{copy.streak(adherenceStats.currentStreakDays)}</p> : null}
                    </div>
                    <div className="space-y-2 text-right">
                        <CircularProgress
                            percent={completionPercent}
                            progressClassName="stroke-white"
                            textClassName="text-white"
                            trackClassName="stroke-white/30"
                        />
                    </div>
                </div>
                <details className="relative mt-3 text-sm text-white/90">
                    <summary className="flex min-h-11 cursor-pointer items-center gap-2"><HiOutlineInformationCircle aria-hidden="true" className="h-5 w-5" />{copy.progressHelp}</summary>
                    <p className="mt-1 max-w-prose">{copy.progressDetail}</p>
                </details>
            </div>

            <div className="patient-stack space-y-5 px-5 pt-6">
                {actionError && !barrierTask ? <p role="alert" className="rounded-xl bg-rose-50 p-4 text-rose-800">{actionError}</p> : null}
                {hasScheduleGaps ? (
                    <Link href="/reminders">
                        <Card className="border-[#edd59a] bg-[#fff7dc]">
                            <p className="text-base font-black text-[#6f4b00]">{copy.setup}</p>
                            <p className="mt-1 text-base leading-7 text-[#7a5a15]">
                                {copy.setupDetail}
                            </p>
                        </Card>
                    </Link>
                ) : null}

                {error ? (
                    <ErrorState
                        description={error}
                        action={<button className="min-h-11 rounded-2xl border border-[#efbeb5] bg-white px-4 py-2 text-sm font-semibold text-[#b94032] transition hover:bg-[#fff2ef]" onClick={refreshFeed} type="button">{copy.retry}</button>}
                        title={tasks.length > 0 ? copy.stale : copy.loadError}
                    />
                ) : null}
                <div className="flex flex-wrap items-center justify-between gap-2">
                    <h2 className="text-xl font-black text-[#17233a]">{copy.schedule}</h2>
                    <button aria-label={loading ? copy.refreshing : copy.refresh} aria-busy={loading} disabled={loading || submitting} className="flex min-h-11 items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 disabled:opacity-50" onClick={refreshFeed} type="button"><HiOutlineArrowPath aria-hidden="true" className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /><span>{loading ? copy.refreshing : copy.refresh}</span></button>
                    <p className="rounded-full bg-white/80 px-3 py-1 text-sm font-bold text-[#64748b]">{copy.count(tasks.length)}</p>
                </div>
                {!error && tasks.length === 0 ? (
                    <EmptyState
                        description={copy.emptyDetail}
                        icon={<HiOutlineCalendarDays />}
                        title={copy.empty}
                    />
                ) : null}
                {tasks.length > 0 ? (
                    <div className="ml-2 border-l-2 border-[#d7e5de] pl-6">
                        {tasks.map((task) => {
                            const status = mapTaskStatus(task, now);
                            const dotClasses =
                                status === "completed"
                                    ? "bg-[#147465] text-white"
                                    : status === "active"
                                      ? "border-4 border-[#147465] bg-white"
                                      : status === "missed"
                                        ? "bg-[#d55b4d]"
                                        : "bg-[#d7e5de]";

                            if (task.type === FeedTaskType.MEDICATION) {
                                const medication = splitMedicationName(task.name);
                                return (
                                    <div className="relative pb-6 last:pb-0" key={task.id}>
                                        <span className={`absolute -left-[34px] top-5 flex h-5 w-5 items-center justify-center rounded-full border-4 border-white ${dotClasses}`}>
                                            {status === "completed" ? <HiOutlineCheck className="h-3.5 w-3.5" /> : null}
                                        </span>
                                        <p className={`mb-2 text-sm font-bold ${status === "active" ? "text-[#147465]" : "text-[#8090a5]"}`}>
                                            {formatTimeLabel(
                                                locale,
                                                copy,
                                                task.scheduledTime,
                                                status,
                                                task.requiresScheduleConfiguration,
                                            )}
                                        </p>
                                        {carePlanLabel(task, copy) ? <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#5b6b83]">{carePlanLabel(task, copy)}</p> : null}
                                        <MedicationCard
                                            locale={locale}
                                            dosage={medication.dosage}
                                            id={task.id}
                                            instructions={task.description}
                                            name={medication.name}
                                            onMarkComplete={() => markComplete(task)}
                                            onReportBarrier={() => setBarrierTask(task)}
                                            prescriber={task.carePlan ? undefined : task.provider?.name}
                                            approvedBy={task.carePlan ? task.provider?.name : undefined}
                                            status={status}
                                            submitting={submitting}
                                            time={task.scheduledTime ?? ""}
                                        />
                                        <CarePlanDetails task={task} copy={copy} />
                                    </div>
                                );
                            }

                            return (
                                <div className="relative pb-6 last:pb-0" key={task.id}>
                                    <span className={`absolute -left-[34px] top-5 flex h-5 w-5 items-center justify-center rounded-full border-4 border-white ${dotClasses}`}>
                                        {status === "completed" ? <HiOutlineCheck className="h-3.5 w-3.5" /> : null}
                                    </span>
                                    <p className={`mb-2 text-sm font-bold ${status === "active" ? "text-[#147465]" : "text-[#8090a5]"}`}>
                                        {formatTimeLabel(
                                            locale,
                                            copy,
                                            task.scheduledTime,
                                            status,
                                            task.requiresScheduleConfiguration,
                                        )}
                                    </p>
                                    {carePlanLabel(task, copy) ? <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[#5b6b83]">{carePlanLabel(task, copy)}</p> : null}
                                    <ObligationCard
                                        locale={locale}
                                        description={task.name}
                                        instructions={task.description}
                                        frequency={task.frequency}
                                        id={task.id}
                                        onMarkComplete={() => markComplete(task)}
                                        onReportBarrier={() => setBarrierTask(task)}
                                        status={status}
                                        submitting={submitting}
                                        time={task.scheduledTime ?? ""}
                                        type={task.carePlan?.category === "movement" ? "exercise" : task.carePlan?.category === "nutrition" ? "diet" : task.carePlan?.category === "hydration" ? "hydration" : task.carePlan?.category === "monitoring" ? "monitoring" : task.carePlan?.category === "follow_up" ? "follow_up" : "custom"}
                                    />
                                    <CarePlanDetails task={task} copy={copy} />
                                </div>
                            );
                        })}
                    </div>
                ) : null}
            </div>

            <div className="px-5 pt-2">
                <Link href="/symptoms">
                    <Card className="flex items-center justify-between border-[#b6d9d2] bg-[#e6f4f1]">
                        <div>
                            <p className="text-base font-black text-[#17233a]">{copy.symptom}</p>
                            <p className="text-base leading-7 text-[#5b6b83]">{copy.symptomDetail}</p>
                        </div>
                        <span className="text-2xl text-[#147465]">→</span>
                    </Card>
                </Link>
            </div>
            <Modal
                closeLabel={copy.close}
                onClose={() => { if (!submitting) { setBarrierTask(null); setBarrierNote(""); } }}
                open={Boolean(barrierTask)}
                title={copy.barrierTitle}
            >
                <div className="space-y-3">
                    {actionError ? <p role="alert" className="rounded-lg bg-rose-50 p-3 text-rose-800">{actionError}</p> : null}
                    <p className="text-sm text-[#5b6b83]">{copy.barrierDetail}</p>
                    <div className="grid grid-cols-2 gap-2">
                        {(["side_effects", "cost", "access", "schedule", "confusion"] as const).map((code) => (
                            <button disabled={submitting} className="rounded-lg border border-[#b6d9d2] px-3 py-2 text-sm font-semibold capitalize text-[#147465]" key={code} onClick={() => void sendBarrier(code)} type="button">{copy.barriers[code]}</button>
                        ))}
                    </div>
                    <label className="block text-sm font-semibold text-[#17233a]">{copy.barriers.other}<textarea className="mt-1 min-h-20 w-full rounded-lg border border-[#b6d9d2] p-2 font-normal" value={barrierNote} onChange={(event) => setBarrierNote(event.target.value)} /></label>
                    <button className="w-full rounded-lg bg-[#147465] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50" disabled={submitting || !barrierNote.trim()} onClick={() => void sendBarrier("other")} type="button">{submitting ? copy.saving : copy.send}</button>
                </div>
            </Modal>
        </div>
    );
}
