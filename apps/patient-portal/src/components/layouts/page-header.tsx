"use client";

import type { ReactNode } from "react";
import { useRouter } from "next/navigation";

interface PageHeaderProps {
    title: string;
    subtitle?: string;
    backButton?: boolean;
    rightAction?: ReactNode;
}

export function PageHeader({ backButton = false, rightAction, subtitle, title }: PageHeaderProps) {
    const router = useRouter();

    return (
        <div className="relative overflow-hidden rounded-b-[34px] bg-[#147465] px-5 pt-11 pb-7 text-white shadow-[0_22px_60px_rgba(20,116,101,0.24)]">
            <div className="pointer-events-none absolute -top-16 -right-14 h-44 w-44 rounded-full bg-white/12" />
            <div className="pointer-events-none absolute -bottom-20 left-8 h-48 w-48 rounded-full bg-[#d8aa57]/18" />
            <div className="flex items-start justify-between gap-4">
                <div className="relative flex items-start gap-3">
                    {backButton ? (
                        <button
                            aria-label="Go back"
                            className="flex h-11 w-11 items-center justify-center rounded-2xl border border-white/20 bg-white/15 text-lg text-white backdrop-blur transition hover:bg-white/25"
                            onClick={() => router.back()}
                            type="button"
                        >
                            ←
                        </button>
                    ) : null}
                    <div>
                        <h1 className="text-[1.75rem] font-bold leading-tight tracking-[-0.02em] text-white">{title}</h1>
                        {subtitle ? <p className="mt-2 max-w-[18rem] text-base leading-7 text-white/82">{subtitle}</p> : null}
                    </div>
                </div>
                <div className="relative">{rightAction}</div>
            </div>
        </div>
    );
}
