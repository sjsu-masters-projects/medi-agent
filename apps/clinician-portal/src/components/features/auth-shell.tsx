"use client";

import Image from "next/image";
import { useEffect, useState, type ReactNode } from "react";
import { Icon } from "@/components/ui/icons";

/**
 * Decorative supervised-flow illustration for the entry screens: Documents → AI draft →
 * Clinician gate → Patient Today. A point of light rises and pauses at the gate.
 * aria-hidden; static (light hidden) under reduced motion; paused while the tab is hidden.
 */
export function SupervisedFlowStack() {
    const [paused, setPaused] = useState(false);
    useEffect(() => {
        const update = () => setPaused(document.hidden);
        document.addEventListener("visibilitychange", update);
        return () => document.removeEventListener("visibilitychange", update);
    }, []);
    const play = { animationPlayState: paused ? "paused" : "running" } as const;
    const plane = "absolute left-[80px] flex h-[240px] w-[240px] flex-col gap-3.5 rounded-[28px] p-[30px] [transform:rotateX(60deg)_rotateZ(-45deg)]";

    return (
        <div aria-hidden="true" className="relative h-[420px] w-[640px] origin-top-left scale-[.68] xl:scale-[.84] 2xl:scale-100">
            {/* 01 Documents */}
            <div className={`${plane} top-[210px] border border-[rgba(148,163,184,.35)] bg-[rgba(148,163,184,.08)]`}>
                <div className="flex h-full gap-3">{[0, 1, 2].map((index) => <div key={index} className="flex-1 rounded-lg border border-[rgba(148,163,184,.3)] bg-[rgba(148,163,184,.18)]" />)}</div>
            </div>
            {/* 02 AI draft */}
            <div className={`${plane} top-[138px] border-[1.5px] border-dashed border-[rgba(96,165,250,.6)] bg-[rgba(59,130,246,.12)]`}>
                <Icon name="spark" className="h-[34px] w-[34px] text-[#93C5FD]" />
                {[90, 70, 80, 55].map((width) => <div key={width} className="h-3.5 rounded-[7px] bg-[rgba(147,197,253,.45)]" style={{ width: `${width}%` }} />)}
            </div>
            {/* 03 Clinician gate */}
            <div className={`${plane} top-[66px] border-[1.5px] border-[rgba(45,212,191,.8)] bg-[rgba(15,118,110,.22)]`}>
                <span className="pointer-events-none absolute -inset-0.5 rounded-[28px]" style={{ animation: "ma-gate 6s ease-in-out infinite", ...play }} />
                <div className="flex flex-1 items-center justify-center">
                    <div className="flex h-24 w-24 items-center justify-center rounded-[26px] bg-ok text-white shadow-[0_0_0_8px_rgba(45,212,191,.18)]"><Icon name="check" className="h-[54px] w-[54px]" strokeWidth={2.2} /></div>
                </div>
            </div>
            {/* 04 Patient Today */}
            <div className={`${plane} top-[-6px] border border-white/90 bg-[rgba(255,253,249,.94)] shadow-[0_30px_50px_-20px_rgba(0,0,0,.6)]`}>
                {[90, 70, 80, 60].map((width, index) => (
                    <div key={width} className="flex items-center gap-2.5">
                        <div className={`h-[22px] w-[22px] flex-none rounded-[7px] ${index < 2 ? "bg-[#147465]" : "bg-[#E3F0EC]"}`} />
                        <div className="h-3 rounded-md bg-[#E8E1D6]" style={{ width: `${width}%` }} />
                    </div>
                ))}
            </div>
            {/* guide and rising light */}
            <div className="absolute left-[199px] top-[114px] h-[216px] border-l border-dashed border-[rgba(94,234,212,.35)]" />
            <span className="absolute left-[194px] top-[324px] block h-3 w-3 rounded-full bg-[#5EEAD4] shadow-[0_0_16px_4px_rgba(94,234,212,.7)] motion-reduce:hidden"
                style={{ animation: "ma-rise 6s ease-in-out infinite", ...play }} />
            {/* flat labels */}
            {[
                { y: 114, n: "04", t: "Patient Today", s: "Only approved items appear", c: "#F5C46A" },
                { y: 186, n: "03 · GATE", t: "Clinician review", s: "Nothing passes without approval", c: "#5EEAD4" },
                { y: 258, n: "02", t: "AI draft", s: "Not visible to the patient", c: "#93C5FD" },
                { y: 330, n: "01", t: "Documents", s: "Source evidence with citations", c: "#A9B6CA" },
            ].map((label) => (
                <div key={label.n}>
                    <div className="absolute left-[378px] h-px w-9 opacity-60" style={{ top: label.y - 1, background: label.c }} />
                    <div className="absolute left-[424px] flex flex-col gap-[3px]" style={{ top: label.y - 22 }}>
                        <span className="font-mono text-xs tracking-[0.08em]" style={{ color: label.c }}>{label.n}</span>
                        <span className="text-[15px] font-semibold text-rail-ink">{label.t}</span>
                        <span className="text-[13px] text-[#8B9AB3]">{label.s}</span>
                    </div>
                </div>
            ))}
        </div>
    );
}

/** Split entry layout: dark product panel on the left, form card on the right. */
export function AuthShell({ headline, subcopy, footer, children, wide = false }: {
    headline: ReactNode;
    subcopy: ReactNode;
    footer?: ReactNode;
    children: ReactNode;
    wide?: boolean;
}) {
    return (
        <div className="flex min-h-screen bg-background">
            <aside className="relative hidden w-[52%] max-w-[880px] flex-col overflow-hidden bg-rail px-12 pb-10 pt-12 text-rail-ink lg:flex xl:px-14">
                <div className="radar-floor radar-floor--dark" aria-hidden="true" />
                <div aria-hidden="true" className="pointer-events-none absolute -left-24 top-1/3 h-[420px] w-[520px] rounded-full bg-[radial-gradient(ellipse,rgba(45,212,191,.12),transparent_65%)]" />
                <div className="relative flex items-center gap-3">
                    <Image src="/brand/mark-sidebar.svg" alt="" width={34} height={34} className="rounded-md" />
                    <p className="text-lg font-semibold tracking-[-0.01em]">MediAgent<span className="text-rail-accent">Pro</span></p>
                </div>
                <div className="relative mt-11 max-w-[600px] space-y-4">
                    <h1 className="text-[40px] font-semibold leading-[1.06] tracking-[-0.03em] text-rail-ink xl:text-[44px]">{headline}</h1>
                    <p className="text-[17px] leading-[1.55] text-rail-muted">{subcopy}</p>
                </div>
                <div className="relative mt-8 h-[286px] xl:h-[353px] 2xl:h-[420px]">
                    <SupervisedFlowStack />
                </div>
                {footer ? <p className="relative mt-auto pt-8 text-sm text-[#8B9AB3]">{footer}</p> : null}
            </aside>

            <main className="relative flex flex-1 items-center justify-center px-5 py-10 sm:px-8">
                <div className={`ma-enter w-full ${wide ? "max-w-xl" : "max-w-[440px]"}`}>
                    <div className="mb-6 flex items-center gap-2.5 lg:hidden">
                        <Image src="/brand/mark-sidebar.svg" alt="" width={30} height={30} className="rounded-md" />
                        <p className="text-[17px] font-semibold text-ink">MediAgent<span className="text-primary">Pro</span></p>
                    </div>
                    <div className="rounded-2xl border border-line bg-surface p-7 shadow-[0_24px_48px_-28px_rgba(15,23,42,.28),var(--shadow-card)] sm:p-8">
                        {children}
                    </div>
                </div>
            </main>
        </div>
    );
}

/** "STEP n OF 3 · CLINIC ACCESS" progress: done bars teal, current long primary, future grey. */
export function AuthSteps({ step, total = 3, label }: { step: number; total?: number; label: string }) {
    return (
        <div className="flex items-center gap-2.5">
            <div aria-hidden="true" className="flex items-center gap-1">
                {Array.from({ length: total }).map((_, index) => (
                    <span key={index} className={`h-1.5 rounded-full transition-[width,background-color] duration-[240ms] ${index + 1 === step ? "w-6 bg-primary" : index + 1 < step ? "w-1.5 bg-ok" : "w-1.5 bg-[#CBD5E1]"}`} />
                ))}
            </div>
            <p className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">Step {step} of {total} · {label}</p>
        </div>
    );
}

/** Verified clinic badge shown after a clinic code resolves. */
export function VerifiedClinic({ name, code, children }: { name: string; code: string; children?: ReactNode }) {
    return (
        <div className="ma-enter flex items-center gap-3 rounded-[14px] border border-ok-line bg-ok-soft p-3.5">
            <span aria-hidden="true" className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-ok text-white"><Icon name="check" className="h-5 w-5" strokeWidth={2.4} /></span>
            <div className="min-w-0 text-sm">
                {children}
                <p className="break-words font-semibold text-ink">{name}</p>
                <p className="font-mono text-xs tracking-[0.04em] text-ok-ink">{code}</p>
            </div>
        </div>
    );
}
