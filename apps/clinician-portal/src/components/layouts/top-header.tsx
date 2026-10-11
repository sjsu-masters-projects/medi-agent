"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon, type IconName } from "@/components/ui/icons";
import { NotificationBell } from "@/components/features/notification-centre";

const sections: Record<string, { title: string; icon: IconName }> = {
    "/dashboard": { title: "Risk Radar", icon: "grid" },
    "/patients": { title: "Patient roster", icon: "users" },
    "/appointments": { title: "Appointments", icon: "cal" },
    "/review-queue": { title: "Patient upload reviews", icon: "inbox" },
    "/medwatch": { title: "ADR reviews", icon: "alert" },
    "/messages": { title: "Messages", icon: "chat" },
    "/alerts": { title: "Alerts", icon: "bell" },
    "/smart-import": { title: "External record import", icon: "download" },
    "/settings": { title: "Clinic settings", icon: "gear" },
    "/settings/mfa": { title: "Account security", icon: "shield" },
};

export function TopHeader() {
    const pathname = usePathname();
    const exact = sections[pathname];
    const patientDetail = !exact && pathname.startsWith("/patients/");
    const title = exact?.title ?? (pathname.endsWith("/upload") ? "Document upload" : "Patient detail");
    return (
        <header className="flex min-h-[60px] shrink-0 flex-wrap items-center justify-between gap-3 border-b border-line bg-surface px-4 py-2.5 sm:px-7">
            <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-2 text-sm">
                {patientDetail ? (
                    <>
                        <Link href="/patients" className="inline-flex items-center gap-2 rounded-md text-muted transition-colors hover:text-ink">
                            <Icon name="users" className="h-4 w-4" />
                            Patient roster
                        </Link>
                        <Icon name="chevron" className="h-3.5 w-3.5 text-[#94A3B8]" />
                        <p aria-current="page" className="truncate font-medium text-ink">{title}</p>
                    </>
                ) : (
                    <p className="inline-flex items-center gap-2 font-medium text-ink-2">
                        <Icon name={exact?.icon ?? "grid"} className="h-4 w-4 text-muted" />
                        {title}
                    </p>
                )}
            </nav>
            <div className="flex items-center gap-2">
            {pathname === "/dashboard" ? (
                <Link href="/settings" className="ma-press inline-flex h-[34px] items-center gap-2 rounded-[9px] border border-line-strong bg-surface px-3.5 text-[13px] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink">
                    <Icon name="plus" className="h-4 w-4" />
                    Patient invitations
                </Link>
            ) : null}
            <NotificationBell />
            </div>
        </header>
    );
}
