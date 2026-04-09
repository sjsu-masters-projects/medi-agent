"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { HiOutlineChartBarSquare, HiOutlineChatBubbleLeftRight, HiOutlineCog6Tooth, HiOutlineExclamationTriangle, HiOutlineUsers } from "react-icons/hi2";

const primaryNavigation = [
    { href: "/dashboard", icon: HiOutlineChartBarSquare, label: "Risk Radar" },
    { href: "/patients", icon: HiOutlineUsers, label: "Patient Roster" },
    { href: "/medwatch", icon: HiOutlineExclamationTriangle, label: "MedWatch Queue" },
    { href: "/messages", icon: HiOutlineChatBubbleLeftRight, label: "Messages" },
];

export function Sidebar() {
    const pathname = usePathname();

    return (
        <aside className="flex w-64 flex-col bg-slate-950 text-white">
            <div className="border-b border-slate-800 px-6 py-5">
                <p className="text-xl font-semibold tracking-tight">
                    MediAgent<span className="text-blue-400">Pro</span>
                </p>
            </div>

            <nav className="flex-1 space-y-2 px-4 py-6">
                {primaryNavigation.map((item) => {
                    const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                    const Icon = item.icon;

                    return (
                        <Link
                            className={`flex items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium transition ${active ? "bg-blue-600 text-white shadow-sm" : "text-slate-300 hover:bg-slate-800 hover:text-white"}`}
                            href={item.href}
                            key={item.href}
                        >
                            <Icon className="h-5 w-5" />
                            <span>{item.label}</span>
                        </Link>
                    );
                })}

                <div className="border-t border-slate-800 pt-4">
                    <p className="px-4 text-xs font-bold uppercase tracking-[0.2em] text-slate-500">Administration</p>
                    <Link
                        className={`mt-3 flex items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium transition ${pathname === "/settings" ? "bg-blue-600 text-white shadow-sm" : "text-slate-300 hover:bg-slate-800 hover:text-white"}`}
                        href="/settings"
                    >
                        <HiOutlineCog6Tooth className="h-5 w-5" />
                        <span>Clinic Settings</span>
                    </Link>
                </div>
            </nav>

            <div className="border-t border-slate-800 px-4 py-4">
                <div className="flex items-center gap-3 rounded-xl bg-slate-800 px-3 py-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-700 text-sm font-semibold">
                        DS
                    </div>
                    <div>
                        <p className="text-sm font-medium text-white">Dr. Smith</p>
                        <p className="text-xs text-slate-400">City Health PCP</p>
                    </div>
                </div>
            </div>
        </aside>
    );
}
