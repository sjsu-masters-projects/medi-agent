"use client";

import Link from "next/link";
import { CircularProgress, MedicationCard, ObligationCard } from "@/components/features";
import { Badge, Card, EmptyState, Skeleton } from "@/components/ui";
import { useFeedData } from "@/hooks/use-feed-data";

function splitMedicationName(name: string) {
    const match = name.match(/^(.*?)(\s+\d.*)$/);
    return {
        dosage: match?.[2]?.trim() ?? "",
        name: match?.[1]?.trim() ?? name,
    };
}

function mapTaskStatus(status: "completed" | "missed" | "pending" | "skipped") {
    if (status === "pending") {
        return "active";
    }

    if (status === "skipped") {
        return "upcoming";
    }

    return status;
}

export default function TodayPage() {
    const { adherenceStats, loading, markComplete, tasks, usingMockData } = useFeedData();
    const completionPercent = Math.round(adherenceStats.overallScore * 100);

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
        <div className="space-y-5 px-5 py-10">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <p className="text-sm font-medium text-gray-500">Today</p>
                    <h1 className="text-2xl font-bold text-gray-900">Care plan overview</h1>
                    <p className="mt-1 text-sm text-gray-500">
                        {new Date().toLocaleDateString("en-US", {
                            day: "numeric",
                            month: "long",
                            weekday: "long",
                        })}
                    </p>
                </div>
                {usingMockData ? <Badge variant="info">Demo data</Badge> : null}
            </div>

            <Card className="flex items-center justify-between gap-4" padding="lg">
                <div className="space-y-2">
                    <p className="text-sm font-medium text-gray-500">Adherence score</p>
                    <h2 className="text-2xl font-bold text-gray-900">{completionPercent}% on track</h2>
                    <p className="text-sm text-gray-500">
                        {adherenceStats.currentStreakDays}-day streak across medication and obligation tasks.
                    </p>
                </div>
                <CircularProgress percent={completionPercent} />
            </Card>

            <div className="space-y-3">
                <div className="flex items-center justify-between">
                    <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
                        Today&apos;s schedule
                    </h2>
                    <p className="text-sm text-gray-500">{tasks.length} tasks</p>
                </div>
                {tasks.length === 0 ? (
                    <EmptyState
                        description="Your clinicians have not assigned anything for today."
                        icon="🗓️"
                        title="Nothing scheduled"
                    />
                ) : null}
                {tasks.map((task) => {
                    if (task.type === "medication") {
                        const medication = splitMedicationName(task.name);
                        return (
                            <MedicationCard
                                dosage={medication.dosage}
                                id={task.id}
                                instructions={task.description}
                                key={task.id}
                                name={medication.name}
                                onMarkComplete={() => markComplete(task)}
                                prescriber={task.provider?.name}
                                status={mapTaskStatus(task.status)}
                                time={task.scheduledTime ? task.scheduledTime.slice(0, 5) : "Any time"}
                            />
                        );
                    }

                    return (
                        <ObligationCard
                            description={task.name}
                            id={task.id}
                            key={task.id}
                            onMarkComplete={() => markComplete(task)}
                            status={mapTaskStatus(task.status)}
                            time={task.scheduledTime ? task.scheduledTime.slice(0, 5) : "Any time"}
                            type={task.frequency.includes("walk") ? "exercise" : "custom"}
                        />
                    );
                })}
            </div>

            <Link href="/symptoms">
                <Card className="flex items-center justify-between">
                    <div>
                        <p className="text-sm font-semibold text-gray-900">Report a symptom</p>
                        <p className="text-sm text-gray-500">Log how you feel and share updates with your care team.</p>
                    </div>
                    <span className="text-lg text-blue-600">→</span>
                </Card>
            </Link>
        </div>
    );
}
