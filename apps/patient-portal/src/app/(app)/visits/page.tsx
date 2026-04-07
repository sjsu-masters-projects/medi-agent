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
            <div className="space-y-4 px-5">
                {appointments.length === 0 ? (
                    <EmptyState description="Your upcoming appointments will appear here." icon="📅" title="No visits scheduled" />
                ) : null}
                {appointments.map((appointment) => (
                    <button className="w-full text-left" key={appointment.id} onClick={() => setSelected(appointment)} type="button">
                        <Card className="space-y-3 transition hover:border-blue-200 hover:shadow-md">
                            <div className="flex items-start justify-between gap-4">
                                <div>
                                    <h2 className="text-sm font-semibold text-gray-900">Care team visit</h2>
                                    <p className="text-sm text-gray-500">{appointment.reason}</p>
                                </div>
                                <Badge variant="info">Scheduled</Badge>
                            </div>
                            <div className="space-y-1 text-sm text-gray-600">
                                <p>{new Date(appointment.scheduledAt).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" })}</p>
                                <p>{appointment.location}</p>
                            </div>
                        </Card>
                    </button>
                ))}
            </div>
            <Modal onClose={() => setSelected(null)} open={Boolean(selected)} title="Visit details">
                <div className="space-y-4">
                    <p className="text-sm text-gray-600">
                        {selected
                            ? new Date(selected.scheduledAt).toLocaleString("en-US", {
                                  dateStyle: "full",
                                  timeStyle: "short",
                              })
                            : null}
                    </p>
                    <p className="text-sm text-gray-600">{selected?.reason}</p>
                    <Button fullWidth variant="primary">
                        Add to calendar
                    </Button>
                </div>
            </Modal>
        </div>
    );
}
