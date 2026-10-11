"use client";

import { useEffect, useState } from "react";

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

/** Three moving bars shown on Listen while audio plays. */
export function ListenBars() {
    return (
        <span className="inline-flex h-3.5 items-center gap-[2px]" aria-hidden="true">
            {[0, 0.2, 0.4].map((delay) => (
                <span key={delay} className="h-full w-[3px] origin-center rounded-full bg-current" style={{ animation: `ma-bars 600ms ${delay}s ease-in-out infinite` }} />
            ))}
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
