"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import {
    HiOutlineCalendarDays,
    HiOutlineChatBubbleLeftRight,
    HiOutlineFolder,
    HiOutlineHome,
    HiOutlineUser,
} from "react-icons/hi2";

interface BottomNavProps {
    currentPath: string;
}

const navItems = [
    { href: "/today", icon: HiOutlineHome, label: "Today" },
    { href: "/records", icon: HiOutlineFolder, label: "Records" },
    { href: "/visits", icon: HiOutlineCalendarDays, label: "Visits" },
    { href: "/profile", icon: HiOutlineUser, label: "Profile" },
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
            className={`flex min-h-[58px] min-w-[58px] flex-col items-center justify-center gap-1 rounded-2xl px-2 transition-all ${
                active ? "bg-[#e6f4f1] text-[#147465]" : "text-[#718096] hover:bg-[#f6f1ea]"
            }`}
            href={href}
        >
            <span className="text-[1.35rem]">{icon}</span>
            <span className="text-[11px] font-bold">{label}</span>
        </Link>
    );
}

export function BottomNav({ currentPath }: BottomNavProps) {
    return (
        <nav className="fixed bottom-0 left-1/2 z-50 w-full max-w-[480px] -translate-x-1/2 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
            <div className="relative flex min-h-[82px] items-center justify-around rounded-[30px] border border-white/80 bg-white/92 px-2 shadow-[0_-18px_60px_rgba(31,45,69,0.14)] ring-1 ring-[#eadfd4]/80 backdrop-blur-xl">
                <NavItem
                    active={currentPath === "/today"}
                    href="/today"
                    icon={<HiOutlineHome />}
                    label="Today"
                />
                <NavItem
                    active={currentPath === "/records"}
                    href="/records"
                    icon={<HiOutlineFolder />}
                    label="Records"
                />
                <Link
                    aria-current={currentPath === "/chat" ? "page" : undefined}
                    aria-label="Open care chat"
                    className={`flex h-[66px] w-[66px] -translate-y-5 items-center justify-center rounded-[26px] border-4 border-white text-3xl text-white shadow-[0_18px_38px_rgba(20,116,101,0.28)] transition-all active:scale-95 ${
                        currentPath === "/chat" ? "bg-[#0f5f53]" : "bg-[#147465]"
                    }`}
                    href="/chat"
                >
                    <HiOutlineChatBubbleLeftRight />
                </Link>
                {navItems.slice(2).map((item) => {
                    const Icon = item.icon;
                    return (
                        <NavItem
                            active={currentPath === item.href}
                            href={item.href}
                            icon={<Icon />}
                            key={item.href}
                            label={item.label}
                        />
                    );
                })}
            </div>
        </nav>
    );
}
