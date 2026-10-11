"use client";

import type { ReactNode } from "react";
import { HiOutlineExclamationTriangle } from "react-icons/hi2";
import { useSharedPatientProfile } from "@/contexts/patient-profile-context";

interface ErrorStateProps {
    title?: string;
    description?: string;
    icon?: ReactNode;
    onRetry?: () => void;
    action?: ReactNode;
}

export function ErrorState({
    action,
    description,
    icon = <HiOutlineExclamationTriangle />,
    onRetry,
    title,
}: ErrorStateProps) {
    const spanish = useSharedPatientProfile()?.profile?.preferredLanguage === "es-MX";
    return (
        <div className="flex flex-col items-center justify-center gap-4 rounded-[22px] border border-danger-ink/20 bg-danger-tint px-6 py-10 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-surface text-2xl text-danger-ink">{icon}</span>
            <div className="space-y-1">
                <h3 className="text-lg font-semibold text-ink">{title ?? (spanish ? "No se pudo cargar" : "Error")}</h3>
                <p className="text-[15px] leading-6 text-muted">{description ?? (spanish ? "Algo salió mal. Intenta de nuevo." : "Something went wrong. Please try again.")}</p>
            </div>
            {onRetry ? (
                <button
                    className="min-h-11 rounded-2xl border border-danger-ink/20 bg-surface px-4 py-2 text-sm font-semibold text-danger-ink transition hover:bg-danger-tint"
                    onClick={onRetry}
                    type="button"
                >
                    {spanish ? "Intentar de nuevo" : "Try again"}
                </button>
            ) : null}
            {action}
        </div>
    );
}
