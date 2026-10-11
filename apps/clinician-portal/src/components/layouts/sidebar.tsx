"use client";

import Link from "next/link";
import Image from "next/image";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { HiOutlineArrowRightOnRectangle, HiOutlineCalendarDays, HiOutlineChartBarSquare, HiOutlineChatBubbleLeftRight, HiOutlineClipboardDocumentList, HiOutlineCog6Tooth, HiOutlineExclamationTriangle, HiOutlineUsers } from "react-icons/hi2";
import { useDispatch, useSelector } from "react-redux";
import { clearStoredSession } from "@/services/auth-session";
import { api } from "@/services/api";
import { logout } from "@/store/slices/auth-slice";
import type { AppDispatch, RootState } from "@/store/store";
import { ClinicianRole, PortalUserRole } from "@/types";

const primaryNavigation = [
    { href: "/dashboard", icon: HiOutlineChartBarSquare, label: "Risk Radar" },
    { href: "/patients", icon: HiOutlineUsers, label: "Patient Roster" },
    { href: "/appointments", icon: HiOutlineCalendarDays, label: "Appointments" },
    { href: "/review-queue", icon: HiOutlineClipboardDocumentList, label: "Review Queue" },
    { href: "/medwatch", icon: HiOutlineExclamationTriangle, label: "ADR Reviews" },
    { href: "/messages", icon: HiOutlineChatBubbleLeftRight, label: "Messages" },
];

interface SidebarClinicianProfile {
    first_name: string;
    last_name: string;
    role: ClinicianRole;
}

type SidebarRole = ClinicianRole | typeof PortalUserRole.CLINICIAN;

function getRoleMeta(role: SidebarRole) {
    switch (role) {
        case ClinicianRole.ADMIN:
            return { label: "Clinic Admin", tone: "bg-blue-500/20 text-blue-200" };
        case ClinicianRole.NURSE:
            return { label: "Nurse / MA", tone: "bg-purple-500/20 text-purple-200" };
        case ClinicianRole.PROVIDER:
            return { label: "Provider", tone: "bg-emerald-500/20 text-emerald-200" };
        default:
            return { label: "Clinician", tone: "bg-slate-500/20 text-slate-200" };
    }
}

export function Sidebar() {
    const pathname = usePathname();
    const router = useRouter();
    const dispatch = useDispatch<AppDispatch>();
    const user = useSelector((state: RootState) => state.auth.user);
    const token = useSelector((state: RootState) => state.auth.accessToken);
    const [profile, setProfile] = useState<SidebarClinicianProfile | null>(null);

    useEffect(() => {
        let isMounted = true;

        async function loadProfile() {
            if (!token) {
                setProfile(null);
                return;
            }

            try {
                const result = await api.get<SidebarClinicianProfile>("/api/v1/clinicians/me", { token });
                if (isMounted) {
                    setProfile(result);
                }
            } catch {
                if (isMounted) {
                    setProfile(null);
                }
            }
        }

        void loadProfile();

        return () => {
            isMounted = false;
        };
    }, [token]);

    const email = user?.email ?? "Email unavailable";
    const displayName = profile ? `${profile.first_name} ${profile.last_name}` : "Clinician";
    const roleMeta = getRoleMeta(profile?.role ?? user?.role ?? PortalUserRole.CLINICIAN);
    const initials = displayName
        .split(" ")
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part.charAt(0))
        .join("")
        .toUpperCase() || "CL";

    const handleLogout = () => {
        clearStoredSession();
        dispatch(logout());
        router.replace("/login");
    };

    return (
        <aside className="flex shrink-0 flex-col bg-slate-900 text-white md:w-64 md:overflow-y-auto">
            <div className="hidden border-b border-slate-800 px-6 py-5 md:block">
                <p className="flex items-center gap-2.5 text-xl font-semibold tracking-tight">
                    <Image src="/brand/mark-sidebar.svg" alt="" width={28} height={28} />
                    <span>MediAgent<span className="text-blue-400">Pro</span></span>
                </p>
            </div>

            <nav aria-label="Clinician navigation" className="flex gap-2 overflow-x-auto px-3 py-2 md:block md:flex-1 md:space-y-2 md:px-4 md:py-6">
                {primaryNavigation.map((item) => {
                    const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                    const Icon = item.icon;

                    return (
                        <Link
                            aria-current={active ? "page" : undefined}
                            className={`flex shrink-0 items-center gap-3 whitespace-nowrap rounded-lg px-4 py-3 text-sm font-medium transition ${active ? "bg-blue-600 text-white shadow-sm" : "text-slate-300 hover:bg-slate-800 hover:text-white"}`}
                            href={item.href}
                            key={item.href}
                        >
                            <Icon aria-hidden="true" className="h-5 w-5" />
                            <span>{item.label}</span>
                        </Link>
                    );
                })}

                <div className="shrink-0 md:border-t md:border-slate-800 md:pt-4">
                    <p className="hidden px-4 text-xs font-bold uppercase tracking-[0.2em] text-slate-400 md:block">Administration</p>
                    <Link
                        aria-current={pathname.startsWith("/settings") ? "page" : undefined}
                        className={`flex items-center gap-3 whitespace-nowrap rounded-lg px-4 py-3 text-sm font-medium transition md:mt-3 ${pathname.startsWith("/settings") ? "bg-blue-600 text-white shadow-sm" : "text-slate-300 hover:bg-slate-800 hover:text-white"}`}
                        href="/settings"
                    >
                        <HiOutlineCog6Tooth aria-hidden="true" className="h-5 w-5" />
                        <span>Clinic Settings</span>
                    </Link>
                </div>
            </nav>

            <div className="flex items-center justify-between gap-2 border-t border-slate-800 px-3 py-1 md:block md:px-4 md:py-4">
                <div role="group" aria-label="Signed-in clinician" className="flex min-w-0 flex-1 items-center gap-3 rounded-xl px-2 py-2 md:bg-slate-800 md:px-3 md:py-3">
                    <div className="hidden h-10 w-10 shrink-0 items-center justify-center rounded-full bg-slate-700 text-sm font-semibold md:flex">
                        {initials}
                    </div>
                    <div className="min-w-0">
                        <p className="break-words text-sm font-medium text-white">{displayName || "Clinician"}</p>
                        <p className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold ${roleMeta.tone}`}>{roleMeta.label}</p>
                        <p className="mt-1 hidden truncate text-[11px] text-slate-400 md:block">{email}</p>
                    </div>
                </div>
                <button
                    className="flex min-h-11 shrink-0 items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-200 transition hover:bg-slate-800 hover:text-white md:mt-3 md:w-full md:border md:border-slate-700"
                    onClick={handleLogout}
                    type="button"
                >
                    <HiOutlineArrowRightOnRectangle className="h-4 w-4" />
                    Logout
                </button>
            </div>
        </aside>
    );
}
