"use client";

import { useState } from "react";
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
        <div className="space-y-4 bg-gray-50 pb-8">
            <PageHeader
                rightAction={<Button variant="secondary">Schedule visit</Button>}
                subtitle="Upcoming appointments and preparation notes."
                title="Visits"
            />
            <div className="-mt-4 space-y-4 px-5">
                {appointments[0] ? (
                    <Card className="border-sky-100 bg-gradient-to-br from-sky-600 to-sky-700 text-white shadow-lg shadow-sky-100">
                        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-100">Next visit</p>
                        <h2 className="mt-2 text-xl font-semibold text-white">Care team follow-up</h2>
                        <p className="mt-2 text-sm text-sky-100">
                            {new Date(appointments[0].scheduledAt).toLocaleString("en-US", {
                                dateStyle: "medium",
                                timeStyle: "short",
                            })}
                        </p>
                        <p className="mt-1 text-sm text-sky-100">{appointments[0].location}</p>
                    </Card>
                ) : null}
                {appointments.length === 0 ? (
                    <EmptyState description="Your upcoming appointments will appear here." icon="📅" title="No visits scheduled" />
                ) : null}
                {appointments.map((appointment) => (
                    <button className="w-full text-left" key={appointment.id} onClick={() => setSelected(appointment)} type="button">
                        <Card className="space-y-4 border-slate-100 transition hover:border-sky-200 hover:shadow-md">
                            <div className="flex items-start justify-between gap-4">
                                <div>
                                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Appointment</p>
                                    <h2 className="mt-1 text-base font-semibold text-slate-900">Care team visit</h2>
                                    <p className="mt-1 text-sm text-slate-500">{appointment.reason}</p>
                                </div>
                                <Badge variant="info">Scheduled</Badge>
                            </div>
                            <div className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
                                <p>{new Date(appointment.scheduledAt).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" })}</p>
                                <p className="mt-1">{appointment.location}</p>
                            </div>
                        </Card>
                    </button>
                ))}
            </div>
            <Modal onClose={() => setSelected(null)} open={Boolean(selected)} title="Visit details">
                <div className="space-y-4">
                    <div className="rounded-2xl bg-slate-50 px-4 py-3">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Scheduled</p>
                        <p className="mt-1 text-sm text-slate-700">
                        {selected
                            ? new Date(selected.scheduledAt).toLocaleString("en-US", {
                                  dateStyle: "full",
                                  timeStyle: "short",
                              })
                            : null}
                        </p>
                    </div>
                    <p className="text-sm text-slate-600">{selected?.reason}</p>
                    <Button fullWidth variant="primary">
                        Add to calendar
                    </Button>
                </div>
            </Modal>
        </div>
    );
}
