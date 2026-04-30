"use client";

import { useState } from "react";
import { HiOutlineCalendarDays } from "react-icons/hi2";
import { PageHeader } from "@/components/layouts";
import { Badge, Button, Card, EmptyState, Modal } from "@/components/ui";
import type { Appointment } from "@/types";

const appointments: Appointment[] = [
    {
        appointmentType: "follow_up",
        careTeamId: "care-team-1",
        createdAt: "2026-03-20T00:00:00Z",
        durationMinutes: 30,
        id: "appt-1",
        location: "City Health Primary Care",
        patientId: "demo-patient",
        reason: "Blood pressure follow-up and medication review.",
        scheduledAt: "2026-04-15T10:30:00Z",
        status: "scheduled",
    },
];

export default function VisitsPage() {
    const [selected, setSelected] = useState<Appointment | null>(null);

    return (
        <div className="patient-page space-y-4 pb-8">
            <PageHeader
                rightAction={<Button variant="secondary">Schedule visit</Button>}
                subtitle="Upcoming appointments and preparation notes."
                title="Visits"
            />
            <div className="patient-stack -mt-4 space-y-4 px-5">
                {appointments[0] ? (
                    <Card className="border-[#b9ded6] bg-gradient-to-br from-[#147465] to-[#285d8f] text-white shadow-[0_24px_55px_rgba(20,116,101,0.24)]">
                        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#ccebe5]">Next visit</p>
                        <h2 className="mt-2 text-xl font-semibold text-white">Care team follow-up</h2>
                        <p className="mt-2 text-base leading-7 text-[#dcefeb]">
                            {new Date(appointments[0].scheduledAt).toLocaleString(undefined, {
                                dateStyle: "medium",
                                timeStyle: "short",
                            })}
                        </p>
                        <p className="mt-1 text-base text-[#dcefeb]">{appointments[0].location}</p>
                    </Card>
                ) : null}
                {appointments.length === 0 ? (
                    <EmptyState
                        description="Your upcoming appointments will appear here."
                        icon={<HiOutlineCalendarDays />}
                        title="No visits scheduled"
                    />
                ) : null}
                {appointments.map((appointment) => (
                    <button className="w-full text-left" key={appointment.id} onClick={() => setSelected(appointment)} type="button">
                        <Card className="space-y-4 transition hover:border-[#b9ded6] hover:shadow-[0_18px_44px_rgba(20,116,101,0.14)]">
                            <div className="flex items-start justify-between gap-4">
                                <div>
                                    <p className="text-xs font-semibold uppercase tracking-wide text-[#7b8798]">Appointment</p>
                                    <h2 className="mt-1 text-lg font-semibold text-[#17233a]">Care team visit</h2>
                                    <p className="mt-1 text-base leading-7 text-[#5b6b83]">{appointment.reason}</p>
                                </div>
                                <Badge variant="info">Scheduled</Badge>
                            </div>
                            <div className="rounded-2xl bg-[#fff7ed] px-4 py-3 text-base leading-7 text-[#48627c] ring-1 ring-[#eaded3]">
                                <p>{new Date(appointment.scheduledAt).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}</p>
                                <p className="mt-1">{appointment.location}</p>
                            </div>
                        </Card>
                    </button>
                ))}
            </div>
            <Modal onClose={() => setSelected(null)} open={Boolean(selected)} title="Visit details">
                <div className="space-y-4">
                    <div className="rounded-2xl bg-[#fff7ed] px-4 py-3 ring-1 ring-[#eaded3]">
                        <p className="text-xs font-semibold uppercase tracking-wide text-[#7b8798]">Scheduled</p>
                        <p className="mt-1 text-base font-semibold text-[#30415f]">
                        {selected
                            ? new Date(selected.scheduledAt).toLocaleString(undefined, {
                                  dateStyle: "full",
                                  timeStyle: "short",
                              })
                            : null}
                        </p>
                    </div>
                    <p className="text-base leading-7 text-[#5b6b83]">{selected?.reason}</p>
                    <Button fullWidth size="lg" variant="primary">
                        Add to calendar
                    </Button>
                </div>
            </Modal>
        </div>
    );
}
