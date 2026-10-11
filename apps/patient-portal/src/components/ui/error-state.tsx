"use client";

import type { ReactNode } from "react";
import { useSharedPatientProfile } from "@/contexts/patient-profile-context";
import { Icon } from "./icons";

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
    icon,
    onRetry,
    title,
}: ErrorStateProps) {
    const spanish = useSharedPatientProfile()?.profile?.preferredLanguage === "es-MX";
    return (
        <div className="flex flex-col items-center justify-center gap-3 rounded-[22px] bg-surface px-6 py-8 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-danger-tint text-2xl text-danger-ink">{icon ?? <Icon name="alert" className="h-6 w-6" />}</span>
            <div className="space-y-1">
                <h3 className="text-[17px] font-semibold text-ink">{title ?? (spanish ? "No se pudo cargar" : "Error")}</h3>
                <p className="text-[15px] leading-6 text-muted">{description ?? (spanish ? "Algo salió mal. Intenta de nuevo." : "Something went wrong. Please try again.")}</p>
            </div>
            {onRetry ? (
                <button
                    className="ma-press mt-1 min-h-11 rounded-[14px] bg-surface-2 px-4 py-2 text-sm font-semibold text-ink-2 hover:bg-line-strong"
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
