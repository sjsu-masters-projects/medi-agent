"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useSharedPatientProfile } from "@/contexts/patient-profile-context";
import { Icon } from "@/components/ui/icons";

interface BottomNavProps {
    currentPath: string;
}

const navItems = [
    { href: "/today", icon: "home", label: "Today" },
    { href: "/records", icon: "folder", label: "Records" },
    { href: "/visits", icon: "cal", label: "Visits" },
    { href: "/profile", icon: "user", label: "Profile" },
] as const;

function NavItem({
    active,
    href,
    icon,
    label,
}: {
    active: boolean;
    href: string;
    icon: ReactNode;
    label: string;
}) {
    return (
        <Link
            aria-current={active ? "page" : undefined}
            className={`relative flex h-[52px] min-w-11 flex-col items-center justify-center gap-[3px] rounded-2xl transition-colors duration-[160ms] ${
                active ? "text-brand" : "text-nav-idle hover:text-ink-2"
            }`}
            href={href}
            prefetch={false}
        >
            <span className="text-[1.35rem]">{icon}</span>
            <span className={`text-[11px] ${active ? "font-semibold" : "font-medium"}`}>{label}</span>
        </Link>
    );
}

export function BottomNav({ currentPath }: BottomNavProps) {
    const spanish = useSharedPatientProfile()?.profile?.preferredLanguage === "es-MX";
    const labels: Record<string, string> = spanish ? { Today: "Hoy", Records: "Registros", Visits: "Citas", Profile: "Perfil" } : {};
    const destinations = ["/today", "/records", "/chat", "/visits", "/profile"];
    const activeIndex = destinations.findIndex((path) => currentPath === path || currentPath.startsWith(`${path}/`));
    return (
        <nav aria-label={spanish ? "Navegación principal" : "Primary navigation"} className="fixed bottom-[calc(18px+env(safe-area-inset-bottom))] left-1/2 z-50 w-[calc(100%-28px)] max-w-[452px] -translate-x-1/2">
            <div className="relative grid h-[68px] grid-cols-5 items-center rounded-3xl border border-[rgba(16,32,43,.06)] bg-[rgba(255,253,249,.86)] shadow-[var(--shadow-nav)] backdrop-blur-[18px] backdrop-saturate-150">
                {activeIndex >= 0 && activeIndex !== 2 ? <span aria-hidden="true" className="pointer-events-none absolute inset-y-[8px] left-0 flex w-1/5 justify-center transition-transform duration-[240ms] ease-[cubic-bezier(.2,.8,.2,1)]" style={{ transform: `translateX(${activeIndex * 100}%)` }}><span className="h-full w-[60px] rounded-2xl bg-brand-tint" /></span> : null}
                <NavItem
                    active={activeIndex === 0}
                    href="/today"
                    icon={<Icon name="home" className="h-[22px] w-[22px]" />}
                    label={labels.Today ?? "Today"}
                />
                <NavItem
                    active={activeIndex === 1}
                    href="/records"
                    icon={<Icon name="folder" className="h-[22px] w-[22px]" />}
                    label={labels.Records ?? "Records"}
                />
                <Link
                    aria-current={activeIndex === 2 ? "page" : undefined}
                    aria-label={spanish ? "Abrir conversaciones" : "Open care chat"}
                    className={`ma-press relative mx-auto -mt-[26px] flex h-[54px] w-[54px] items-center justify-center rounded-[18px] shadow-[var(--shadow-fab)] ${
                        activeIndex === 2 ? "bg-brand-deep text-gold ring-4 ring-brand-tint" : "bg-brand text-white"
                    }`}
                    href="/chat"
                    prefetch={false}
                >
                    <Icon name="chat" />
                </Link>
                {navItems.slice(2).map((item) => {
                    return (
                        <NavItem
                            active={currentPath === item.href || currentPath.startsWith(`${item.href}/`)}
                            href={item.href}
                            icon={<Icon name={item.icon} className="h-[22px] w-[22px]" />}
                            key={item.href}
                            label={labels[item.label] ?? item.label}
                        />
                    );
                })}
            </div>
        </nav>
    );
}
