"use client";

import { useRef, type ChangeEvent } from "react";
import Link from "next/link";
import { HiOutlineCalendarDays, HiOutlineCheck } from "react-icons/hi2";
import { CircularProgress, MedicationCard, ObligationCard } from "@/components/features";
import type { TaskCardStatus } from "@/components/features/task-card.types";
import { Button, Card, EmptyState, ErrorState, Skeleton } from "@/components/ui";
import { useFeedData } from "@/hooks/use-feed-data";
import { usePatientProfile } from "@/hooks/use-patient-profile";
import { FeedTaskStatus, FeedTaskType, type FeedTask } from "@/types";

function splitMedicationName(name: string) {
    const match = name.match(/^(.*?)(\s+\d.*)$/);
    return {
        dosage: match?.[2]?.trim() ?? "",
        name: match?.[1]?.trim() ?? name,
    };
}

function mapTaskStatus(status: FeedTask["status"]): TaskCardStatus {
    if (status === FeedTaskStatus.PENDING) {
        return "active";
    }

    if (status === FeedTaskStatus.SKIPPED) {
        return "upcoming";
    }

    return status;
}

function formatTimeLabel(
    scheduledTime?: string,
    status?: FeedTask["status"],
    requiresScheduleConfiguration?: boolean,
) {
    if (!scheduledTime && requiresScheduleConfiguration) {
        return "Set reminder time";
    }
    if (!scheduledTime) {
        return "Any time";
    }

    const [hours = "0", minutes = "0"] = scheduledTime.split(":");
    const value = new Date();
    value.setHours(Number(hours), Number(minutes), 0, 0);
    const label = value.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
    return status === FeedTaskStatus.PENDING ? `${label} • Now` : label;
}

export default function TodayPage() {
    const {
        adherenceStats,
        documentImportError,
        documentImporting,
        error,
        importDocumentFile,
        loading,
        markComplete,
        refreshFeed,
        summary,
        tasks,
    } = useFeedData();
    const documentInputRef = useRef<HTMLInputElement | null>(null);
    const profile = usePatientProfile();
    const displayName = profile?.firstName ?? "";
    const avatarInitial = displayName.charAt(0).toUpperCase() || "?";
    const completionPercent = Number.isFinite(adherenceStats.overallScore)
        ? Math.round(adherenceStats.overallScore * 100)
        : 0;
    const completedLabel = `${summary.completed} of ${summary.total || tasks.length} tasks completed`;
    const hasScheduleGaps = tasks.some((task) => task.requiresScheduleConfiguration);

    function handleDocumentFileChange(event: ChangeEvent<HTMLInputElement>) {
        const file = event.target.files?.[0];
        if (!file) {
            return;
        }

        void importDocumentFile(file);
        event.target.value = "";
    }

    if (loading && tasks.length === 0) {
        return (
            <div className="patient-page space-y-4 px-5 py-10">
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
                        <p className="text-xs font-black uppercase tracking-[0.24em] text-white/68">Today</p>
                        <h1 className="mt-2 text-[2.35rem] font-black leading-none tracking-[-0.04em]">
                            {displayName ? `Hi, ${displayName}` : "Hi there"}
                        </h1>
                        <p className="mt-2 text-base text-white/82">
                            {new Date().toLocaleDateString(undefined, {
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
                        <p className="text-xl font-black text-white">Daily progress</p>
                        <p className="text-base text-white/82">{completedLabel}</p>
                        <p className="text-sm font-semibold text-white/76">{adherenceStats.currentStreakDays}-day streak</p>
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
            </div>

            <div className="patient-stack space-y-5 px-5 pt-6">
                {hasScheduleGaps ? (
                    <Link href="/reminders">
                        <Card className="border-[#edd59a] bg-[#fff7dc]">
                            <p className="text-base font-black text-[#6f4b00]">Set reminder times</p>
                            <p className="mt-1 text-base leading-7 text-[#7a5a15]">
                                Some care-plan items still need your preferred days and times.
                            </p>
                        </Card>
                    </Link>
                ) : null}
                <Card className="flex items-center justify-between gap-4 border-[#b9ded6] bg-[#e7f4f1]">
                    <div>
                        <p className="text-base font-black text-[#17233a]">Clinical document</p>
                        <p className="text-sm font-semibold text-[#48627c]">
                            {documentImporting ? "Importing..." : "Upload PDF or image"}
                        </p>
                    </div>
                    <Button
                        disabled={documentImporting}
                        onClick={() => documentInputRef.current?.click()}
                        size="sm"
                        variant="secondary"
                    >
                        {documentImporting ? "Importing" : "Import"}
                    </Button>
                    <input
                        accept="application/pdf,image/*,text/plain,text/csv,application/json"
                        className="hidden"
                        onChange={handleDocumentFileChange}
                        ref={documentInputRef}
                        type="file"
                    />
                </Card>
                {documentImportError ? (
                    <ErrorState
                        description={documentImportError}
                        onRetry={() => documentInputRef.current?.click()}
                        title="Document import failed"
                    />
                ) : null}
                {error ? (
                    <ErrorState
                        description={error}
                        onRetry={refreshFeed}
                        title={tasks.length > 0 ? "Schedule may be stale" : "Could not load schedule"}
                    />
                ) : null}
                <div className="flex items-center justify-between">
                    <h2 className="text-xl font-black text-[#17233a]">Today&apos;s schedule</h2>
                    <p className="rounded-full bg-white/80 px-3 py-1 text-sm font-bold text-[#64748b]">{tasks.length} tasks</p>
                </div>
                {!error && tasks.length === 0 ? (
                    <EmptyState
                        description="Your clinicians have not assigned anything for today."
                        icon={<HiOutlineCalendarDays />}
                        title="Nothing scheduled"
                    />
                ) : null}
                {tasks.length > 0 ? (
                    <div className="ml-2 border-l-2 border-[#d7e5de] pl-6">
                        {tasks.map((task) => {
                            const status = mapTaskStatus(task.status);
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
                                                task.scheduledTime,
                                                task.status,
                                                task.requiresScheduleConfiguration,
                                            )}
                                        </p>
                                        <MedicationCard
                                            dosage={medication.dosage}
                                            id={task.id}
                                            instructions={task.description}
                                            name={medication.name}
                                            onMarkComplete={() => markComplete(task)}
                                            prescriber={task.provider?.name}
                                            status={status}
                                            time={task.scheduledTime ?? ""}
                                        />
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
                                            task.scheduledTime,
                                            task.status,
                                            task.requiresScheduleConfiguration,
                                        )}
                                    </p>
                                    <ObligationCard
                                        description={task.name}
                                        id={task.id}
                                        onMarkComplete={() => markComplete(task)}
                                        status={status}
                                        time={task.scheduledTime ?? ""}
                                        type={task.frequency?.includes("walk") ? "exercise" : "custom"}
                                    />
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
                            <p className="text-base font-black text-[#17233a]">Report a symptom</p>
                            <p className="text-base leading-7 text-[#5b6b83]">Log how you feel and share updates with your care team.</p>
                        </div>
                        <span className="text-2xl text-[#147465]">→</span>
                    </Card>
                </Link>
            </div>
        </div>
    );
}
