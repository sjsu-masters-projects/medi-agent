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
        <div className="flex flex-col items-center justify-center gap-4 rounded-[28px] border border-[#efbeb5] bg-[#fff5f2] px-6 py-10 text-center shadow-[0_18px_48px_rgba(116,52,42,0.08)]">
            <span className="flex h-16 w-16 items-center justify-center rounded-3xl bg-white text-4xl text-[#b94032]">{icon}</span>
            <div className="space-y-1">
                <h3 className="text-lg font-bold text-[#17233a]">{title ?? (spanish ? "No se pudo cargar" : "Error")}</h3>
                <p className="text-base leading-7 text-[#5b6b83]">{description ?? (spanish ? "Algo salió mal. Intenta de nuevo." : "Something went wrong. Please try again.")}</p>
            </div>
            {onRetry ? (
                <button
                    className="min-h-11 rounded-2xl border border-[#efbeb5] bg-white px-4 py-2 text-sm font-semibold text-[#b94032] transition hover:bg-[#fff2ef]"
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
