"use client";

import { HiOutlineCalendarDays } from "react-icons/hi2";
import { PageHeader } from "@/components/layouts";
import { Button, Card, EmptyState } from "@/components/ui";

export default function VisitsPage() {
    return (
        <div className="patient-page space-y-4 pb-8">
            <PageHeader
                subtitle="Upcoming appointments and preparation notes."
                title="Visits"
            />
            <div className="patient-stack -mt-4 space-y-4 px-5">
                <Card className="border-[#b9ded6] bg-gradient-to-br from-[#147465] to-[#285d8f] text-white shadow-[0_24px_55px_rgba(20,116,101,0.24)]">
                    <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#ccebe5]">
                        Coming soon
                    </p>
                    <h2 className="mt-2 text-xl font-semibold text-white">
                        Appointment scheduling
                    </h2>
                    <p className="mt-2 text-base leading-7 text-[#dcefeb]">
                        Your clinician will propose appointments based on your follow-up
                        instructions. You&apos;ll be able to confirm and track them here.
                    </p>
                </Card>

                <EmptyState
                    description="Once your clinician schedules a visit, it will appear here with preparation notes and reminders."
                    icon={<HiOutlineCalendarDays />}
                    title="No visits scheduled yet"
                />

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
                            window.location.href = "/chat";
                        }}
                        size="lg"
                        variant="secondary"
                    >
                        Message care team
                    </Button>
                </Card>
            </div>
        </div>
    );
}
