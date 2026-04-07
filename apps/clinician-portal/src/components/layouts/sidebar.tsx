"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSelector } from "react-redux";
import type { RootState } from "@/store/store";

const navigation = [
    { href: "/dashboard", icon: "📊", label: "Dashboard" },
    { href: "/patients", icon: "👥", label: "Patients" },
    { href: "/medwatch", icon: "⚠️", label: "MedWatch" },
    { href: "/messages", icon: "💬", label: "Messages" },
    { href: "/settings", icon: "⚙️", label: "Settings" },
];

export function Sidebar() {
    const pathname = usePathname();
    const user = useSelector((state: RootState) => state.auth.user);

    return (
        <aside className="flex w-64 flex-col bg-gray-900 text-white">
            <div className="border-b border-gray-800 px-6 py-5">
                <p className="text-xl font-semibold">MediAgent Pro</p>
                <p className="mt-1 text-sm text-gray-400">Clinical Intelligence Platform</p>
            </div>

            <nav className="flex-1 space-y-2 px-4 py-6">
                {navigation.map((item) => {
                    const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                    return (
                        <Link
                            className={`flex items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium transition ${active ? "bg-blue-600 text-white" : "text-gray-300 hover:bg-gray-800 hover:text-white"}`}
                            href={item.href}
                            key={item.href}
                        >
                            <span>{item.icon}</span>
                            <span>{item.label}</span>
                        </Link>
                    );
                })}
            </nav>

            <div className="border-t border-gray-800 px-4 py-4">
                <div className="flex items-center gap-3 rounded-xl bg-gray-800 px-3 py-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-600 text-sm font-semibold">
                        {user?.email?.[0]?.toUpperCase() ?? "D"}
                    </div>
                    <div className="min-w-0">
                        <p className="truncate text-sm font-medium">{user?.email ?? "Dr. Smith"}</p>
                        <p className="text-xs capitalize text-gray-400">{user?.role ?? "clinician"}</p>
                    </div>
                </div>
            </div>
        </aside>
    );
}
