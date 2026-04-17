"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { HiOutlineArrowRightOnRectangle, HiOutlineChartBarSquare, HiOutlineChatBubbleLeftRight, HiOutlineCog6Tooth, HiOutlineExclamationTriangle, HiOutlineUsers } from "react-icons/hi2";
import { useDispatch, useSelector } from "react-redux";
import { clearStoredSession } from "@/services/auth-session";
import { api } from "@/services/api";
import { logout } from "@/store/slices/auth-slice";
import type { AppDispatch, RootState } from "@/store/store";
import { ClinicianRole, PortalUserRole } from "@/types";

const primaryNavigation = [
    { href: "/dashboard", icon: HiOutlineChartBarSquare, label: "Risk Radar" },
    { href: "/patients", icon: HiOutlineUsers, label: "Patient Roster" },
    { href: "/medwatch", icon: HiOutlineExclamationTriangle, label: "MedWatch Queue" },
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

    const email = user?.email ?? "clinician@mediagent.local";
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
                        {initials}
                    </div>
                    <div>
                        <p className="text-sm font-medium text-white">{displayName || "Clinician"}</p>
                        <p className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold ${roleMeta.tone}`}>{roleMeta.label}</p>
                        <p className="mt-1 truncate text-[11px] text-slate-400">{email}</p>
                    </div>
                </div>
                <button
                    className="mt-3 flex w-full items-center justify-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm font-medium text-slate-200 transition hover:bg-slate-800 hover:text-white"
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
