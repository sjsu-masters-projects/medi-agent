"use client";

import Link from "next/link";

interface BottomNavProps {
    currentPath: string;
}

function NavItem({
    active,
    href,
    icon,
    label,
}: {
    active: boolean;
    href: string;
    icon: string;
    label: string;
}) {
    return (
        <Link className="flex min-w-[52px] flex-col items-center gap-1 px-3 py-2" href={href}>
            <span className={`text-xl leading-none ${active ? "text-blue-600" : "text-gray-400"}`}>
                {icon}
            </span>
            <span className={`text-[10px] font-medium ${active ? "text-blue-600" : "text-gray-400"}`}>
                {label}
            </span>
        </Link>
    );
}

export function BottomNav({ currentPath }: BottomNavProps) {
    return (
        <nav className="fixed bottom-0 left-1/2 z-50 flex w-full max-w-[448px] -translate-x-1/2 items-center justify-around border-t border-gray-200 bg-white">
            <NavItem active={currentPath === "/today"} href="/today" icon="🏠" label="Today" />
            <NavItem active={currentPath === "/records"} href="/records" icon="📁" label="Records" />
            <Link
                className="flex h-14 w-14 -translate-y-5 items-center justify-center rounded-full bg-blue-600 text-2xl text-white shadow-lg"
                href="/chat"
            >
                💬
            </Link>
            <NavItem active={currentPath === "/visits"} href="/visits" icon="📅" label="Visits" />
            <NavItem active={currentPath === "/profile"} href="/profile" icon="👤" label="Profile" />
        </nav>
    );
}
