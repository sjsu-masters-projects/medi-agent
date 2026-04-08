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
        <div className="rounded-b-[28px] bg-sky-700 px-5 pt-10 pb-6 text-white shadow-sm">
            <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3">
                    {backButton ? (
                        <button
                            className="rounded-full border border-white/20 bg-white/15 p-2 text-white backdrop-blur"
                            onClick={() => router.back()}
                            type="button"
                        >
                            ←
                        </button>
                    ) : null}
                    <div>
                        <h1 className="text-2xl font-bold text-white">{title}</h1>
                        {subtitle ? <p className="mt-1 text-sm text-sky-100">{subtitle}</p> : null}
                    </div>
                </div>
                {rightAction}
            </div>
        </div>
    );
}
