"use client";

import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useSharedPatientProfile } from "@/contexts/patient-profile-context";
import { Icon } from "@/components/ui/icons";

interface PageHeaderProps {
    title: string;
    subtitle?: string;
    backButton?: boolean;
    rightAction?: ReactNode;
}

/** Large-title header. Pushed screens (back button) use a compact title row instead. */
export function PageHeader({ backButton = false, rightAction, subtitle, title }: PageHeaderProps) {
    const router = useRouter();
    const spanish = useSharedPatientProfile()?.profile?.preferredLanguage === "es-MX";

    if (backButton) {
        return (
            <header className="px-3 pt-3 pb-2">
                <div className="flex min-h-11 items-center gap-1">
                    <button
                        aria-label={spanish ? "Volver" : "Go back"}
                        className="ma-press flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-ink hover:bg-surface-2"
                        onClick={() => router.back()}
                        type="button"
                    >
                        <Icon name="back" className="h-[22px] w-[22px]" />
                    </button>
                    <div className="min-w-0 flex-1" />
                    {rightAction ? <div className="flex shrink-0 flex-wrap items-center gap-2">{rightAction}</div> : null}
                </div>
                <div className="px-2.5 pt-2">
                    <h1 className="break-words text-[28px] font-semibold leading-[1.15] tracking-[-0.02em] text-ink">{title}</h1>
                    {subtitle ? <p className="mt-1.5 max-w-prose text-[15px] leading-relaxed text-muted">{subtitle}</p> : null}
                </div>
            </header>
        );
    }

    return (
        <header className="px-[22px] pt-4 pb-2">
            <div className="flex items-center justify-between gap-3">
                <h1 className="min-w-0 break-words text-[32px] font-semibold leading-[1.1] tracking-[-0.02em] text-ink">{title}</h1>
                {rightAction ? <div className="flex shrink-0 flex-wrap items-center gap-2">{rightAction}</div> : null}
            </div>
            {subtitle ? <p className="mt-1.5 max-w-prose text-[15px] leading-relaxed text-muted">{subtitle}</p> : null}
        </header>
    );
}
