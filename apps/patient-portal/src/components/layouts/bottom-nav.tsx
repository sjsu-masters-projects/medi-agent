"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { HiSparkles } from "react-icons/hi2";

interface BottomNavProps {
    currentPath: string;
}

function Icon({
    active,
    children,
}: {
    active: boolean;
    children: ReactNode;
}) {
    return (
        <span className={`flex h-5 w-5 items-center justify-center ${active ? "text-sky-700" : "text-slate-400"}`}>
            {children}
        </span>
    );
}

function HomeIcon({ active }: { active: boolean }) {
    return (
        <Icon active={active}>
            <svg fill="none" height="18" viewBox="0 0 20 20" width="18">
                <path d="M3.5 9.25 10 4l6.5 5.25v7.25h-4.75v-4H8.25v4H3.5V9.25Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
            </svg>
        </Icon>
    );
}

function FolderIcon({ active }: { active: boolean }) {
    return (
        <Icon active={active}>
            <svg fill="none" height="18" viewBox="0 0 20 20" width="18">
                <path d="M3.5 5.75h4l1.25 1.5H16.5v6.75a1 1 0 0 1-1 1H4.5a1 1 0 0 1-1-1V5.75Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
            </svg>
        </Icon>
    );
}

function CalendarIcon({ active }: { active: boolean }) {
    return (
        <Icon active={active}>
            <svg fill="none" height="18" viewBox="0 0 20 20" width="18">
                <path d="M5.5 4.5v2M14.5 4.5v2M4 7h12m-10.75 3.25h2.25m2.5 0h2.25m-7 3h2.25m2.5 0h2.25M5 5.5h10a1 1 0 0 1 1 1v8.25a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6.5a1 1 0 0 1 1-1Z" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" />
            </svg>
        </Icon>
    );
}

function UserIcon({ active }: { active: boolean }) {
    return (
        <Icon active={active}>
            <svg fill="none" height="18" viewBox="0 0 20 20" width="18">
                <path d="M10 10.25a3.125 3.125 0 1 0 0-6.25 3.125 3.125 0 0 0 0 6.25ZM4.5 16.25a5.5 5.5 0 0 1 11 0" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
            </svg>
        </Icon>
    );
}

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
        <Link className="flex min-w-[52px] flex-col items-center gap-1 px-3 py-2" href={href}>
            {icon}
            <span className={`text-[10px] font-medium ${active ? "text-sky-700" : "text-slate-400"}`}>{label}</span>
        </Link>
    );
}

export function BottomNav({ currentPath }: BottomNavProps) {
    return (
        <nav className="fixed bottom-0 left-1/2 z-50 flex h-20 w-full max-w-[448px] -translate-x-1/2 items-center justify-around border-t border-slate-200 bg-white/95 px-3 backdrop-blur">
            <NavItem active={currentPath === "/today"} href="/today" icon={<HomeIcon active={currentPath === "/today"} />} label="Today" />
            <NavItem active={currentPath === "/records"} href="/records" icon={<FolderIcon active={currentPath === "/records"} />} label="Records" />
            <Link
                className="flex h-14 w-14 -translate-y-5 items-center justify-center rounded-full border-4 border-white bg-sky-700 text-2xl text-white shadow-[0_10px_18px_-8px_rgba(2,132,199,0.65)]"
                href="/chat"
            >
                <HiSparkles className="h-6 w-6" />
            </Link>
            <NavItem active={currentPath === "/visits"} href="/visits" icon={<CalendarIcon active={currentPath === "/visits"} />} label="Visits" />
            <NavItem active={currentPath === "/profile"} href="/profile" icon={<UserIcon active={currentPath === "/profile"} />} label="Profile" />
        </nav>
    );
}
