"use client";

import { useRef, useState, type ReactNode, type TouchEvent } from "react";

/** Optional gesture affordance. The existing refresh control remains the keyboard path. */
export function PullToRefresh({ children, onRefresh, busy = false, indicateBusy = true, label }: {
    children: ReactNode;
    onRefresh: () => void | Promise<unknown>;
    busy?: boolean;
    /** False: parent `busy` still blocks gestures but only a gesture shows the mark. */
    indicateBusy?: boolean;
    label: string;
}) {
    const start = useRef<{ x: number; y: number } | null>(null);
    const distance = useRef(0);
    const locked = useRef(false);
    const [pull, setPull] = useState(0);
    const [awaiting, setAwaiting] = useState(false);
    const pending = busy || awaiting;
    function reset() { start.current = null; distance.current = 0; setPull(0); }
    function begin(event: TouchEvent<HTMLDivElement>) {
        reset();
        if (pending || locked.current || event.touches.length !== 1) return;
        const target = event.target as HTMLElement;
        if (target.closest('button, a, input, select, textarea, [role="dialog"], [contenteditable="true"]')) return;
        if ((document.scrollingElement?.scrollTop ?? window.scrollY) > 0) return;
        for (let node: HTMLElement | null = target; node; node = node.parentElement) {
            if (node.scrollTop > 0 || (node.scrollHeight > node.clientHeight && /auto|scroll/.test(getComputedStyle(node).overflowY))) return;
        }
        start.current = { x: event.touches[0].clientX, y: event.touches[0].clientY };
    }
    function move(event: TouchEvent<HTMLDivElement>) {
        if (!start.current) return;
        if (event.touches.length !== 1) { reset(); return; }
        const dx = event.touches[0].clientX - start.current.x;
        const dy = event.touches[0].clientY - start.current.y;
        if (dy < 0 || Math.abs(dx) > Math.abs(dy)) { reset(); return; }
        distance.current = Math.min(dy * 0.5, 110);
        setPull(distance.current);
    }
    async function release() {
        const ready = distance.current >= 80 && !pending && !locked.current;
        reset();
        if (!ready) return;
        locked.current = true;
        try {
            const result = onRefresh();
            // A void dispatch is not proof of a pending network operation; parent busy owns it.
            if (result && typeof result.then === "function") {
                setAwaiting(true);
                await result;
            }
        } catch {
            // The existing loader owns its error notice; a gesture must not leave a rejected event promise.
        } finally { locked.current = false; setAwaiting(false); }
    }
    const shown = indicateBusy ? pending : awaiting;
    const height = shown ? 56 : pull;
    return (
        <div onTouchStart={begin} onTouchMove={move} onTouchEnd={() => { void release(); }} onTouchCancel={reset}>
            <div className="flex items-end justify-center overflow-hidden transition-[height] duration-[240ms]" style={{ height }}>
                {height > 8 && <svg width="40" height="40" viewBox="0 0 512 512" className="mb-2" role="img" aria-label={label}>
                    <rect width="512" height="512" rx="112" fill="var(--color-brand)" />
                    <path d="M150 362V166L226 300L362 150V362" fill="none" stroke="#FFF8EE" strokeWidth="58" strokeLinecap="round" strokeLinejoin="round" pathLength="1" strokeDasharray="1" style={pending ? { animation: "ma-draw 1.2s ease-in-out infinite" } : { strokeDashoffset: 1 - Math.min(pull / 80, 1) }} />
                    <path d="M150 166L226 300L362 150" fill="none" stroke="#F5C46A" strokeWidth="58" strokeLinecap="round" strokeLinejoin="round" />
                </svg>}
            </div>
            {children}
        </div>
    );
}
