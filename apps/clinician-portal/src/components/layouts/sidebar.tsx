"use client";

import Link from "next/link";
import Image from "next/image";
import { useEffect, useState, useSyncExternalStore } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useDispatch, useSelector } from "react-redux";
import { Icon, type IconName } from "@/components/ui/icons";
import { clearStoredSession } from "@/services/auth-session";
import { readStoredClinicContext } from "@/services/clinic-context";
import { api } from "@/services/api";
import { logout } from "@/store/slices/auth-slice";
import type { AppDispatch, RootState } from "@/store/store";
import { ClinicianRole, PortalUserRole } from "@/types";

const primaryNavigation: { href: string; icon: IconName; label: string }[] = [
    { href: "/dashboard", icon: "grid", label: "Risk Radar" },
    { href: "/patients", icon: "users", label: "Patient Roster" },
    { href: "/appointments", icon: "cal", label: "Appointments" },
    { href: "/review-queue", icon: "inbox", label: "Review Queue" },
    { href: "/medwatch", icon: "alert", label: "ADR Reviews" },
    { href: "/messages", icon: "chat", label: "Messages" },
];

interface SidebarClinicianProfile {
    first_name: string;
    last_name: string;
    role: ClinicianRole;
    clinic_name?: string | null;
}

type SidebarRole = ClinicianRole | typeof PortalUserRole.CLINICIAN;

function getRoleMeta(role: SidebarRole) {
    switch (role) {
        case ClinicianRole.ADMIN:
            return { label: "Clinic Admin" };
        case ClinicianRole.NURSE:
            return { label: "Nurse / MA" };
        case ClinicianRole.PROVIDER:
            return { label: "Provider" };
        default:
            return { label: "Clinician" };
    }
}

function noopSubscribe() {
    return () => undefined;
}

function storedClinicName() {
    try { return readStoredClinicContext()?.clinicName ?? null; } catch { return null; }
}

function NavItem({ href, icon, label, active, count }: { href: string; icon: IconName; label: string; active: boolean; count?: number }) {
    return (
        <Link
            aria-current={active ? "page" : undefined}
            className={`group flex h-[38px] shrink-0 items-center gap-2.5 whitespace-nowrap rounded-[10px] px-2.5 text-sm transition-colors duration-[160ms] ${active ? "bg-rail-active font-medium text-rail-ink" : "text-rail-muted hover:bg-white/5 hover:text-rail-ink"}`}
            href={href}
        >
            <Icon name={icon} className={`h-[18px] w-[18px] shrink-0 ${active ? "text-rail-accent" : "text-rail-muted group-hover:text-rail-ink"}`} />
            <span className="flex-1">{label}</span>
            {count ? <span className={`ml-auto font-mono text-xs ${active ? "text-[#93C5FD]" : "text-rail-faint"}`}>{count}</span> : null}
        </Link>
    );
}

export function Sidebar() {
    const pathname = usePathname();
    const router = useRouter();
    const dispatch = useDispatch<AppDispatch>();
    const user = useSelector((state: RootState) => state.auth.user);
    const token = useSelector((state: RootState) => state.auth.accessToken);
    // Counts come from data the dashboard already loaded; the sidebar never fetches its own.
    const pendingAdr = useSelector((state: RootState) => state.dashboard?.summary?.pending_adr_reviews);
    const [profile, setProfile] = useState<SidebarClinicianProfile | null>(null);
    const storedClinic = useSyncExternalStore(noopSubscribe, storedClinicName, () => null);
    const clinicName = profile?.clinic_name || storedClinic;

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
    const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

    const handleLogout = () => {
        clearStoredSession();
        dispatch(logout());
        router.replace("/login");
    };

    return (
        <aside className="flex shrink-0 flex-col border-white/10 bg-rail text-rail-ink md:h-dvh md:w-[232px] md:overflow-y-auto md:border-r md:px-3.5 md:py-5">
            <div className="hidden items-center gap-2.5 px-2 pb-[22px] md:flex">
                <Image src="/brand/mark-sidebar.svg" alt="" width={30} height={30} className="rounded-md" />
                <span className="text-[17px] font-semibold tracking-[-0.01em]">MediAgent<span className="text-rail-accent">Pro</span></span>
            </div>

            <nav aria-label="Clinician navigation" className="flex gap-1 overflow-x-auto px-3 py-2 md:flex-1 md:flex-col md:gap-0.5 md:overflow-visible md:p-0">
                {primaryNavigation.map((item) => (
                    <NavItem key={item.href} {...item} active={isActive(item.href)} count={item.href === "/medwatch" ? pendingAdr : undefined} />
                ))}

                <div className="flex shrink-0 md:block">
                    <p className="hidden px-2.5 pb-2 pt-[18px] font-mono text-[11px] uppercase tracking-[0.08em] text-rail-faint md:block">Administration</p>
                    <NavItem href="/settings" icon="gear" label="Clinic Settings" active={pathname.startsWith("/settings")} />
                </div>
            </nav>

            <div className="flex items-center justify-between gap-2 border-t border-white/10 px-3 py-2 md:mt-4 md:flex-col md:items-stretch md:border-t-0 md:p-0">
                <div role="group" aria-label="Signed-in clinician" className="flex min-w-0 flex-1 items-center gap-2.5 rounded-xl px-1 py-1 md:bg-white/5 md:p-2.5">
                    <div aria-hidden="true" className="hidden h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full bg-[#1E293B] text-[13px] font-semibold md:flex">
                        {initials}
                    </div>
                    <div className="min-w-0">
                        <p className="break-words text-[13px] font-semibold leading-tight text-rail-ink">{displayName || "Clinician"}</p>
                        <p className="mt-0.5 text-xs leading-tight text-[#8B9AB3]">
                            <span>{roleMeta.label}</span>
                            {clinicName ? <span className="hidden md:inline"> · {clinicName}</span> : null}
                        </p>
                        <p className="mt-1 hidden truncate text-[11px] text-rail-faint md:block" title={email}>{email}</p>
                    </div>
                </div>
                <button
                    className="ma-press flex h-9 shrink-0 items-center justify-center gap-2 rounded-lg border border-white/10 px-3 text-sm text-rail-muted hover:bg-white/5 hover:text-rail-ink md:w-full"
                    onClick={handleLogout}
                    type="button"
                >
                    <Icon name="logout" className="h-4 w-4" />
                    Logout
                </button>
            </div>
        </aside>
    );
}
