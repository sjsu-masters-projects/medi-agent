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
        <div className="flex items-start justify-between gap-4 px-5 pt-10 pb-4">
            <div className="flex items-start gap-3">
                {backButton ? (
                    <button
                        className="rounded-lg border border-gray-200 bg-white p-2 text-gray-600 shadow-sm"
                        onClick={() => router.back()}
                        type="button"
                    >
                        ←
                    </button>
                ) : null}
                <div>
                    <h1 className="text-xl font-bold text-gray-900">{title}</h1>
                    {subtitle ? <p className="mt-1 text-sm text-gray-500">{subtitle}</p> : null}
                </div>
            </div>
            {rightAction}
        </div>
    );
}
