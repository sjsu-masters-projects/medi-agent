"use client";

import Link from "next/link";
import { HiOutlineCalendarDays, HiOutlineCheck } from "react-icons/hi2";
import { CircularProgress, MedicationCard, ObligationCard } from "@/components/features";
import type { TaskCardStatus } from "@/components/features/task-card.types";
import { Badge, Card, EmptyState, Skeleton } from "@/components/ui";
import { useFeedData } from "@/hooks/use-feed-data";
import type { FeedTask } from "@/types";

function splitMedicationName(name: string) {
    const match = name.match(/^(.*?)(\s+\d.*)$/);
    return {
        dosage: match?.[2]?.trim() ?? "",
        name: match?.[1]?.trim() ?? name,
    };
}

function mapTaskStatus(status: FeedTask["status"]): TaskCardStatus {
    if (status === "pending") {
        return "active";
    }

    if (status === "skipped") {
        return "upcoming";
    }

    return status;
}

function formatTimeLabel(scheduledTime?: string, status?: FeedTask["status"]) {
    if (!scheduledTime) {
        return "Any time";
    }

    const [hours = "0", minutes = "0"] = scheduledTime.split(":");
    const value = new Date();
    value.setHours(Number(hours), Number(minutes), 0, 0);
    const label = value.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
    return status === "pending" ? `${label} • Now` : label;
}

export default function TodayPage() {
    const { adherenceStats, loading, markComplete, summary, tasks, usingMockData } = useFeedData();
    const completionPercent = Math.round(adherenceStats.overallScore * 100);
    const completedLabel = `${summary.completed} of ${summary.total || tasks.length} tasks completed`;

    if (loading && tasks.length === 0) {
        return (
            <div className="space-y-4 px-5 py-10">
                <Skeleton className="h-24 w-full" variant="rect" />
                <Skeleton className="h-28 w-full" variant="rect" />
                <Skeleton className="h-28 w-full" variant="rect" />
            </div>
        );
    }

    return (
        <div className="bg-white pb-8">
            <div className="rounded-b-[28px] bg-sky-700 px-5 pt-10 pb-6 text-white shadow-sm">
                <div className="flex items-start justify-between gap-4">
                    <div>
                        <h1 className="text-[30px] font-bold leading-tight">Hi, Sarah</h1>
                        <p className="mt-1 text-sm text-sky-100">
                            {new Date().toLocaleDateString("en-US", {
                                day: "numeric",
                                month: "long",
                                weekday: "long",
                            })}
                        </p>
                    </div>
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-white text-lg font-bold text-sky-700 shadow-sm">
                        S
                    </div>
                </div>

                <div className="mt-4 flex items-center justify-between gap-4 rounded-2xl bg-white/15 p-4 backdrop-blur">
                    <div className="space-y-1">
                        <p className="text-lg font-semibold text-white">Daily Progress</p>
                        <p className="text-sm text-sky-100">{completedLabel}</p>
                        <p className="text-xs text-sky-100">{adherenceStats.currentStreakDays}-day streak</p>
                    </div>
                    <div className="space-y-2 text-right">
                        {usingMockData ? <Badge variant="info">Demo data</Badge> : null}
                        <CircularProgress
                            percent={completionPercent}
                            progressClassName="stroke-white"
                            textClassName="text-white"
                            trackClassName="stroke-white/30"
                        />
                    </div>
                </div>
            </div>

            <div className="space-y-5 px-5 pt-6">
                <div className="flex items-center justify-between">
                    <h2 className="text-lg font-semibold text-slate-800">Today&apos;s Schedule</h2>
                    <p className="text-sm text-slate-500">{tasks.length} tasks</p>
                </div>
                {tasks.length === 0 ? (
                    <EmptyState
                        description="Your clinicians have not assigned anything for today."
                        icon={<HiOutlineCalendarDays />}
                        title="Nothing scheduled"
                    />
                ) : null}
                <div className="ml-2 border-l-2 border-rose-100 pl-6">
                {tasks.map((task) => {
                    const status = mapTaskStatus(task.status);
                    const dotClasses =
                        status === "completed"
                            ? "bg-blue-700 text-white"
                            : status === "active"
                              ? "border-4 border-blue-700 bg-white"
                              : status === "missed"
                                ? "bg-red-500"
                                : "bg-slate-200";

                    if (task.type === "medication") {
                        const medication = splitMedicationName(task.name);
                        return (
                            <div className="relative pb-6 last:pb-0" key={task.id}>
                                <span className={`absolute -left-[34px] top-5 flex h-5 w-5 items-center justify-center rounded-full border-4 border-white ${dotClasses}`}>
                                    {status === "completed" ? <HiOutlineCheck className="h-3.5 w-3.5" /> : null}
                                </span>
                                <p className={`mb-2 text-xs font-medium ${status === "active" ? "text-sky-700" : "text-slate-400"}`}>
                                    {formatTimeLabel(task.scheduledTime, task.status)}
                                </p>
                                <MedicationCard
                                    dosage={medication.dosage}
                                    id={task.id}
                                    instructions={task.description}
                                    name={medication.name}
                                    onMarkComplete={() => markComplete(task)}
                                    prescriber={task.provider?.name}
                                    status={status}
                                    time=""
                                />
                            </div>
                        );
                    }

                    return (
                        <div className="relative pb-6 last:pb-0" key={task.id}>
                            <span className={`absolute -left-[34px] top-5 flex h-5 w-5 items-center justify-center rounded-full border-4 border-white ${dotClasses}`}>
                                {status === "completed" ? <HiOutlineCheck className="h-3.5 w-3.5" /> : null}
                            </span>
                            <p className={`mb-2 text-xs font-medium ${status === "active" ? "text-sky-700" : "text-slate-400"}`}>
                                {formatTimeLabel(task.scheduledTime, task.status)}
                            </p>
                            <ObligationCard
                                description={task.name}
                                id={task.id}
                                onMarkComplete={() => markComplete(task)}
                                status={status}
                                time=""
                                type={task.frequency.includes("walk") ? "exercise" : "custom"}
                            />
                        </div>
                    );
                })}
                </div>
            </div>

            <div className="px-5 pt-2">
                <Link href="/symptoms">
                    <Card className="flex items-center justify-between border-sky-100 bg-sky-50">
                        <div>
                            <p className="text-sm font-semibold text-slate-900">Report a symptom</p>
                            <p className="text-sm text-slate-500">Log how you feel and share updates with your care team.</p>
                        </div>
                        <span className="text-lg text-sky-700">→</span>
                    </Card>
                </Link>
            </div>
        </div>
    );
}
