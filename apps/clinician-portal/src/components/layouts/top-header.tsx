"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { HiOutlineUserPlus } from "react-icons/hi2";

const titles: Record<string, string> = {
    "/dashboard": "Risk Radar",
    "/patients": "Patient roster",
    "/appointments": "Appointments",
    "/review-queue": "Patient upload reviews",
    "/medwatch": "ADR reviews",
    "/messages": "Messages",
    "/smart-import": "External record import",
    "/settings": "Clinic settings",
    "/settings/mfa": "Account security",
};

export function TopHeader() {
    const pathname = usePathname();
    const title = titles[pathname] ?? (pathname.endsWith("/upload") ? "Document upload" : "Patient detail");
    const isPageTitle = pathname === "/dashboard" || pathname === "/patients" || pathname === "/settings";
    return (
        <header className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-4 sm:px-6">
            {isPageTitle ? <h1 className="text-2xl font-bold text-slate-900">{title}</h1> : <p className="text-sm font-semibold text-slate-600">{title}</p>}
            {pathname === "/dashboard" ? (
                <Link href="/settings" className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50">
                    <HiOutlineUserPlus aria-hidden="true" className="h-4 w-4" />
                    Patient invitations
                </Link>
            ) : null}
        </header>
    );
}
