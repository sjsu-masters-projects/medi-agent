"use client";

import Link from "next/link";
import Image from "next/image";
import { useEffect, useState, useSyncExternalStore } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useDispatch, useSelector } from "react-redux";
import { useOptionalNotificationCentre } from "@/components/features/notification-provider";
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
    { href: "/adr-reviews", icon: "alert", label: "ADR Reviews" },
    { href: "/medwatch", icon: "file", label: "MedWatch" },
    { href: "/messages", icon: "chat", label: "Messages" },
    { href: "/alerts", icon: "bell", label: "Alerts" },
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

// Collapsed state is a per-browser convenience; it must render correctly without storage.
const COLLAPSE_KEY = "clinician-portal.sidebar-collapsed";
const COLLAPSE_EVENT = "clinician-sidebar-collapse";

function subscribeCollapsed(onChange: () => void) {
    window.addEventListener(COLLAPSE_EVENT, onChange);
    window.addEventListener("storage", onChange);
    return () => {
        window.removeEventListener(COLLAPSE_EVENT, onChange);
        window.removeEventListener("storage", onChange);
    };
}

function readCollapsed() {
    try { return window.localStorage.getItem(COLLAPSE_KEY) === "1"; } catch { return false; }
}

function writeCollapsed(collapsed: boolean) {
    try { window.localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0"); } catch { /* storage unavailable */ }
    window.dispatchEvent(new Event(COLLAPSE_EVENT));
}

function NavItem({ href, icon, label, active, count, collapsed }: { href: string; icon: IconName; label: string; active: boolean; count?: number; collapsed: boolean }) {
    return (
        <Link
            aria-current={active ? "page" : undefined}
            className={`group relative flex h-[38px] shrink-0 items-center gap-2.5 whitespace-nowrap rounded-[10px] px-2.5 text-sm transition-colors duration-[160ms] ${collapsed ? "md:justify-center md:px-0" : ""} ${active ? "bg-rail-active font-medium text-rail-ink" : "text-rail-muted hover:bg-white/5 hover:text-rail-ink"}`}
            href={href}
            title={collapsed ? (count ? `${label} (${count})` : label) : undefined}
        >
            <Icon name={icon} className={`h-[18px] w-[18px] shrink-0 ${active ? "text-rail-accent" : "text-rail-muted group-hover:text-rail-ink"}`} />
            <span className={`flex-1 ${collapsed ? "md:sr-only" : ""}`}>{label}</span>
            {count ? (
                collapsed ? (
                    <>
                        <span className="ml-auto font-mono text-xs text-rail-faint md:hidden">{count}</span>
                        <span aria-hidden="true" className="absolute right-1.5 top-1.5 hidden h-2 w-2 rounded-full bg-rail-accent ring-2 ring-rail md:block" />
                    </>
                ) : (
                    <span className={`ml-auto font-mono text-xs ${active ? "text-[#93C5FD]" : "text-rail-faint"}`}>{count}</span>
                )
            ) : null}
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
    // One notification number across the shell: the sidebar shows the same unread count
    // as the header bell. "Needs attention" is shown on the Alerts page itself.
    const unreadAlerts = useOptionalNotificationCentre()?.summary.data?.unread_count;
    const [profile, setProfile] = useState<SidebarClinicianProfile | null>(null);
    const storedClinic = useSyncExternalStore(noopSubscribe, storedClinicName, () => null);
    const collapsed = useSyncExternalStore(subscribeCollapsed, readCollapsed, () => false);
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
    const accountSummary = [displayName, roleMeta.label, clinicName].filter(Boolean).join(" · ");

    const handleLogout = () => {
        clearStoredSession();
        dispatch(logout());
        router.replace("/login");
    };

    return (
        <aside
            id="clinician-sidebar"
            data-collapsed={collapsed ? "true" : "false"}
            className={`flex shrink-0 flex-col border-white/10 bg-rail text-rail-ink transition-[width] duration-200 ease-[cubic-bezier(.2,.8,.2,1)] md:h-dvh md:overflow-y-auto md:overflow-x-hidden md:border-r md:py-5 ${collapsed ? "md:w-[68px] md:px-2.5" : "md:w-[232px] md:px-3.5"}`}
        >
            <div className={`hidden items-center pb-[22px] md:flex ${collapsed ? "flex-col gap-3" : "gap-2.5 px-2"}`}>
                <Image src="/brand/mark-sidebar.svg" alt="" width={30} height={30} className="shrink-0 rounded-md" />
                {collapsed ? null : <span className="flex-1 whitespace-nowrap text-[17px] font-semibold tracking-[-0.01em]">MediAgent<span className="text-rail-accent">Pro</span></span>}
                <button
                    aria-controls="clinician-sidebar"
                    aria-expanded={!collapsed}
                    aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                    className="ma-press flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-rail-muted hover:bg-white/5 hover:text-rail-ink"
                    onClick={() => writeCollapsed(!collapsed)}
                    title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
                    type="button"
                >
                    <Icon name="chevron" className={`h-4 w-4 transition-transform duration-200 ${collapsed ? "" : "rotate-180"}`} />
                </button>
            </div>

            <nav aria-label="Clinician navigation" className="flex gap-1 overflow-x-auto px-3 py-2 md:flex-1 md:flex-col md:gap-0.5 md:overflow-visible md:p-0">
                {primaryNavigation.map((item) => (
                    <NavItem key={item.href} {...item} active={isActive(item.href)} collapsed={collapsed} count={item.href === "/adr-reviews" ? pendingAdr : item.href === "/alerts" ? unreadAlerts : undefined} />
                ))}

                <div className="flex shrink-0 md:block">
                    {collapsed
                        ? <span aria-hidden="true" className="mx-2.5 my-3 hidden h-px bg-white/10 md:block" />
                        : <p className="hidden px-2.5 pb-2 pt-[18px] font-mono text-[11px] uppercase tracking-[0.08em] text-rail-faint md:block">Administration</p>}
                    <NavItem href="/settings" icon="gear" label="Clinic Settings" active={pathname.startsWith("/settings")} collapsed={collapsed} />
                </div>
            </nav>

            <div className="flex items-center justify-between gap-2 border-t border-white/10 px-3 py-2 md:mt-4 md:flex-col md:items-stretch md:border-t-0 md:p-0">
                <div
                    role="group"
                    aria-label="Signed-in clinician"
                    className={`flex min-w-0 flex-1 items-center gap-2.5 rounded-xl px-1 py-1 md:bg-white/5 ${collapsed ? "md:flex-none md:justify-center md:bg-transparent md:p-0" : "md:p-2.5"}`}
                    title={collapsed ? accountSummary : user?.email ?? undefined}
                >
                    <div aria-hidden="true" className="hidden h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full bg-[#1E293B] text-[13px] font-semibold md:flex">
                        {initials}
                    </div>
                    <div className={`min-w-0 ${collapsed ? "md:sr-only" : ""}`}>
                        <p className="break-words text-[13px] font-semibold leading-tight text-rail-ink">{displayName}</p>
                        <p className="mt-0.5 text-xs leading-tight text-[#8B9AB3]">{roleMeta.label}</p>
                        {/* Clinic names run long; wrap to two lines rather than cut them off. */}
                        {clinicName ? <p className="mt-0.5 hidden text-xs leading-snug text-[#8B9AB3] [overflow-wrap:anywhere] line-clamp-2 md:block">{clinicName}</p> : null}
                    </div>
                </div>
                <button
                    aria-label={collapsed ? "Logout" : undefined}
                    className={`ma-press flex h-9 shrink-0 items-center justify-center gap-2 rounded-lg border border-white/10 px-3 text-sm text-rail-muted hover:bg-white/5 hover:text-rail-ink md:w-full ${collapsed ? "md:mx-auto md:w-9 md:px-0" : ""}`}
                    onClick={handleLogout}
                    title={collapsed ? "Logout" : undefined}
                    type="button"
                >
                    <Icon name="logout" className="h-4 w-4" />
                    <span className={collapsed ? "md:sr-only" : ""}>Logout</span>
                </button>
            </div>
        </aside>
    );
}
