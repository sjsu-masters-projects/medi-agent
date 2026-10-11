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

export function PageHeader({ backButton = false, rightAction, subtitle, title }: PageHeaderProps) {
    const router = useRouter();
    const spanish = useSharedPatientProfile()?.profile?.preferredLanguage === "es-MX";

    return (
        <header className="px-[22px] pt-6 pb-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex min-w-0 flex-1 items-start gap-2">
                    {backButton ? (
                        <button
                            aria-label={spanish ? "Volver" : "Go back"}
                            className="ma-press -ml-2 flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-ink hover:bg-surface-2"
                            onClick={() => router.back()}
                            type="button"
                        >
                            <Icon name="back" className="h-[22px] w-[22px]" />
                        </button>
                    ) : null}
                    <div className="min-w-0">
                        <h1 className="text-[32px] font-semibold leading-[1.1] tracking-[-0.02em] text-ink">{title}</h1>
                        {subtitle ? <p className="mt-2 max-w-prose text-[15px] leading-relaxed text-muted">{subtitle}</p> : null}
                    </div>
                </div>
                {rightAction ? <div className="flex shrink-0 flex-wrap items-center gap-2">{rightAction}</div> : null}
            </div>
        </header>
    );
}
