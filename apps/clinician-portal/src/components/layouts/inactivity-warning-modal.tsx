"use client";

import { Button, Modal } from "@/components/ui";

export function formatCountdown(remainingMs: number): string {
    const totalSeconds = Math.max(0, Math.ceil(remainingMs / 1000));
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

interface InactivityWarningModalProps {
    onStay: () => void;
    remainingMs: number | null;
}

export function InactivityWarningModal({ onStay, remainingMs }: InactivityWarningModalProps) {
    return (
        <Modal onClose={onStay} open={remainingMs !== null} title="Still there?">
            <p aria-live="polite" className="text-sm text-ink" role="timer">
                You&apos;ll be signed out in {formatCountdown(remainingMs ?? 0)} for inactivity.
            </p>
            <div className="mt-5 flex justify-end">
                <Button onClick={onStay} type="button">
                    Stay signed in
                </Button>
            </div>
        </Modal>
    );
}
