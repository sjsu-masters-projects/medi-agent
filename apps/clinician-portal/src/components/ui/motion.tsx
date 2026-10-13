"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

/** Three animated dots. Mount only while work is actually happening. */
export function ProcessingDots({ className = "bg-muted" }: { className?: string }) {
    return (
        <span className="inline-flex items-center gap-[3px]" aria-hidden="true">
            {[0, 0.15, 0.3].map((delay) => (
                <span key={delay} className={`h-1 w-1 rounded-full ${className}`} style={{ animation: `ma-dot 1.2s ${delay}s infinite` }} />
            ))}
        </span>
    );
}

/** Pulsing dot for running jobs only. */
export function LiveDot({ color = "#14B8A6" }: { color?: string }) {
    return (
        <span className="relative inline-block h-2 w-2 shrink-0" aria-hidden="true">
            <span className="absolute inset-0 rounded-full" style={{ background: color, animation: "ma-pulse 1.8s ease-out infinite" }} />
            <span className="absolute inset-0 rounded-full" style={{ background: color }} />
        </span>
    );
}

export function useReducedMotion() {
    const [reduced, setReduced] = useState(false);
    useEffect(() => {
        const query = window.matchMedia?.("(prefers-reduced-motion: reduce)");
        if (!query) return;
        const update = () => setReduced(query.matches);
        update();
        query.addEventListener?.("change", update);
        return () => query.removeEventListener?.("change", update);
    }, []);
    return reduced;
}

/**
 * FLIP list reordering: rows glide to their new position when sort or filter changes.
 *   const flip = useFlip(rows.map((row) => row.id).join(","));
 *   rows.map((row) => <div key={row.id} ref={flip(row.id)} />)
 */
export function useFlip<T extends HTMLElement = HTMLDivElement>(orderKey: string) {
    const nodes = useRef(new Map<string, T>());
    const previous = useRef(new Map<string, number>());
    const mounted = useRef(false);
    const reduced = useReducedMotion();
    useLayoutEffect(() => {
        const next = new Map<string, number>();
        nodes.current.forEach((element, id) => {
            const top = element.offsetTop;
            next.set(id, top);
            if (!mounted.current || reduced || typeof element.animate !== "function") return;
            const before = previous.current.get(id);
            if (before === undefined) {
                element.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 160, easing: "ease-out" });
            } else if (before !== top) {
                element.animate([{ transform: `translateY(${before - top}px)` }, { transform: "none" }], { duration: 240, easing: "cubic-bezier(.2,.8,.2,1)" });
            }
        });
        previous.current = next;
        mounted.current = true;
    }, [orderKey, reduced]);
    return (id: string) => (element: T | null) => {
        if (element) nodes.current.set(id, element);
        else nodes.current.delete(id);
    };
}
