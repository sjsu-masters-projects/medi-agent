"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
    HiOutlineCalendarDays,
    HiOutlineClock,
    HiOutlineMapPin,
    HiOutlineUser,
} from "react-icons/hi2";
import { useSelector } from "react-redux";
import { PageHeader } from "@/components/layouts";
import { Badge, Button, Card, EmptyState, ErrorState, Skeleton } from "@/components/ui";
import {
    fetchAppointments,
    formatAppointmentDate,
    formatAppointmentStatus,
    formatAppointmentTime,
    formatAppointmentType,
    isUpcomingAppointment,
    sortAppointmentsForDisplay,
} from "@/services/appointments";
import type { RootState } from "@/store/store";
import { AppointmentStatus, type Appointment } from "@/types";

function statusVariant(status: AppointmentStatus): "success" | "warning" | "danger" | "neutral" {
    if (status === AppointmentStatus.SCHEDULED) {
        return "success";
    }
    if (status === AppointmentStatus.COMPLETED) {
        return "neutral";
    }
    if (status === AppointmentStatus.NO_SHOW) {
        return "warning";
    }
    return "danger";
}

function AppointmentCard({ appointment }: { appointment: Appointment }) {
    const upcoming = isUpcomingAppointment(appointment);

    return (
        <Card className="space-y-3">
            <div className="flex items-start justify-between gap-3">
                <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-[#7b8798]">
                        {formatAppointmentType(appointment.appointmentType)}
                    </p>
                    <h2 className="mt-1 text-lg font-semibold text-[#17233a]">
                        {formatAppointmentDate(appointment.scheduledAt)}
                    </h2>
                </div>
                <Badge variant={statusVariant(appointment.status)}>
                    {formatAppointmentStatus(appointment.status)}
                </Badge>
            </div>

            <dl className="space-y-2 text-base leading-7 text-[#5b6b83]">
                <div className="flex items-center gap-2">
                    <HiOutlineClock aria-hidden className="text-[#147465]" />
                    <dt className="sr-only">Time</dt>
                    <dd>
                        {formatAppointmentTime(
                            appointment.scheduledAt,
                            appointment.durationMinutes,
                        )}
                    </dd>
                </div>

                {appointment.clinicianName ? (
                    <div className="flex items-center gap-2">
                        <HiOutlineUser aria-hidden className="text-[#147465]" />
                        <dt className="sr-only">Clinician</dt>
                        <dd>{appointment.clinicianName}</dd>
                    </div>
                ) : null}

                {appointment.location ? (
                    <div className="flex items-center gap-2">
                        <HiOutlineMapPin aria-hidden className="text-[#147465]" />
                        <dt className="sr-only">Location</dt>
                        <dd>{appointment.location}</dd>
                    </div>
                ) : null}
            </dl>

            {appointment.reason ? (
                <div className="rounded-2xl bg-[#f7f4ef] px-4 py-3 ring-1 ring-[#eaded3]">
                    <p className="text-xs font-semibold uppercase tracking-wide text-[#7b8798]">
                        Reason for visit
                    </p>
                    <p className="mt-1 text-base leading-7 text-[#48627c]">{appointment.reason}</p>
                </div>
            ) : null}

            {upcoming && appointment.notes ? (
                <div className="rounded-2xl bg-[#e6f4f1] px-4 py-3 ring-1 ring-[#b9ded6]">
                    <p className="text-xs font-semibold uppercase tracking-wide text-[#147465]">
                        Preparation notes
                    </p>
                    <p className="mt-1 text-base leading-7 text-[#2c4f4a]">{appointment.notes}</p>
                </div>
            ) : null}
        </Card>
    );
}

export default function VisitsPage() {
    const router = useRouter();
    const accessToken = useSelector((state: RootState) => state.auth.accessToken);
    const authLoading = useSelector((state: RootState) => state.auth.loading);

    const [appointments, setAppointments] = useState<Appointment[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const loadAppointments = useCallback(async () => {
        if (!accessToken) {
            return;
        }

        setLoading(true);
        setError(null);
        try {
            setAppointments(await fetchAppointments(accessToken));
        } catch (caught) {
            setError(
                (caught as Error).message || "Unable to load your visits. Please try again.",
            );
        } finally {
            setLoading(false);
        }
    }, [accessToken]);

    useEffect(() => {
        if (authLoading) {
            return;
        }
        if (!accessToken) {
            setLoading(false);
            return;
        }
        void loadAppointments();
    }, [accessToken, authLoading, loadAppointments]);

    const ordered = useMemo(
        () => sortAppointmentsForDisplay(appointments),
        [appointments],
    );
    const upcomingCount = useMemo(
        () => appointments.filter(isUpcomingAppointment).length,
        [appointments],
    );

    const subtitle = upcomingCount > 0
        ? `${upcomingCount} upcoming ${upcomingCount === 1 ? "visit" : "visits"}.`
        : "Upcoming appointments and preparation notes.";

    return (
        <div className="patient-page space-y-4 pb-8">
            <PageHeader subtitle={subtitle} title="Visits" />

            <div className="patient-stack -mt-4 space-y-4 px-5">
                {loading ? (
                    <div className="space-y-4">
                        <Skeleton className="h-44 w-full" />
                        <Skeleton className="h-44 w-full" />
                    </div>
                ) : null}

                {!loading && error ? (
                    <ErrorState
                        description={error}
                        onRetry={() => {
                            void loadAppointments();
                        }}
                        title="Could not load visits"
                    />
                ) : null}

                {!loading && !error && ordered.length === 0 ? (
                    <EmptyState
                        description="Once your clinician schedules a visit, it will appear here with preparation notes and reminders."
                        icon={<HiOutlineCalendarDays />}
                        title="No visits scheduled yet"
                    />
                ) : null}

                {!loading && !error && ordered.length > 0
                    ? ordered.map((appointment) => (
                          <AppointmentCard appointment={appointment} key={appointment.id} />
                      ))
                    : null}

                {!loading && !error ? (
                    <Card className="border-[#b9ded6] bg-[#e6f4f1]">
                        <p className="text-base font-bold text-[#17233a]">
                            Need to schedule a visit?
                        </p>
                        <p className="mt-1 text-base leading-7 text-[#5b6b83]">
                            Message your care team directly through the chat to request an
                            appointment or follow-up.
                        </p>
                        <Button
                            className="mt-3"
                            fullWidth
                            onClick={() => {
                                router.push("/chat");
                            }}
                            size="lg"
                            variant="secondary"
                        >
                            Message care team
                        </Button>
                    </Card>
                ) : null}
            </div>
        </div>
    );
}
