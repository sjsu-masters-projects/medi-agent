"use client";

import { usePathname } from "next/navigation";

const pageTitles: Record<string, string> = {
    "/dashboard": "Risk Radar Dashboard",
    "/medwatch": "MedWatch Queue",
    "/messages": "Messages",
    "/patients": "Patient Roster",
    "/settings": "Clinic Settings",
};

export function TopHeader() {
    const pathname = usePathname();
    const title =
        pageTitles[pathname] ??
        (pathname.startsWith("/patients/") ? "Patient Detail" : "Clinical Intelligence");

    return (
        <header className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-4">
            <div>
                <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
                <p className="text-sm text-gray-500">Monitor risk, coordinate care, and act on alerts.</p>
            </div>
            <div className="flex items-center gap-4">
                <div className="rounded-full border border-gray-200 bg-gray-50 px-4 py-2 text-sm text-gray-500">
                    Search patients...
                </div>
                <button className="rounded-full border border-gray-200 bg-white p-2 text-gray-500 shadow-sm">
                    🔔
                </button>
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-600 text-sm font-semibold text-white">
                    DS
                </div>
            </div>
        </header>
    );
}
