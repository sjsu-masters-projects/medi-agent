"use client";

import { useMemo } from "react";
import { usePathname } from "next/navigation";
import { HiOutlineBell, HiOutlineUserPlus } from "react-icons/hi2";
import { Button } from "@/components/ui";

export function TopHeader() {
    const pathname = usePathname();

    const header = useMemo(() => {
        if (pathname === "/dashboard") {
            return {
                title: "Risk Radar Dashboard",
                subtitle: "",
                rightContent: (
                    <div className="flex items-center gap-4">
                        <div className="relative text-slate-400">
                            <HiOutlineBell className="h-5 w-5" />
                            <span className="absolute -right-0.5 top-0 h-2.5 w-2.5 rounded-full border-2 border-white bg-red-600" />
                        </div>
                        <Button className="px-4 py-2 text-xs font-semibold leading-tight">
                            <span className="inline-flex items-center gap-1">
                                <HiOutlineUserPlus className="h-4 w-4" />
                                Invite
                            </span>
                            <br />
                            Patient
                        </Button>
                    </div>
                ),
            };
        }

        if (pathname === "/settings") {
            return {
                title: "Clinic Setup & Administration",
                subtitle: "Manage your organization's profile, team access, and patient onboarding.",
                rightContent: (
                    <div className="flex items-center gap-2 text-sm text-slate-500">
                        <span className="h-2 w-2 rounded-full bg-green-600" />
                        <span>System Online</span>
                    </div>
                ),
            };
        }

        if (pathname === "/patients") {
            return {
                title: "Patient Roster",
                subtitle: "Review panel risk, adherence, and recent activity across shared care.",
                rightContent: null,
            };
        }

        if (pathname === "/medwatch") {
            return {
                title: "MedWatch Queue",
                subtitle: "Review pending FDA safety drafts and clinician follow-through.",
                rightContent: null,
            };
        }

        if (pathname === "/messages") {
            return {
                title: "Messages",
                subtitle: "Coordinate staff and patient follow-up from one inbox.",
                rightContent: null,
            };
        }

        return {
            title: pathname.startsWith("/patients/") ? "Patient Detail" : "Clinical Intelligence",
            subtitle: "",
            rightContent: null,
        };
    }, [pathname]);

    return (
        <header className="flex items-start justify-between border-b border-slate-200 bg-white px-8 py-5">
            <div>
                <h1 className="text-[28px] font-bold leading-tight text-slate-900">{header.title}</h1>
                {header.subtitle ? <p className="mt-1 text-sm text-slate-500">{header.subtitle}</p> : null}
            </div>
            {header.rightContent}
        </header>
    );
}
