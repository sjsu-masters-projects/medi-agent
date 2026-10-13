"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { copyText } from "@/utils/clipboard";
import { Button } from "./button";

const COPIED_FOR_MS = 2500;

interface CopyButtonProps {
    /** The text to copy; the button is disabled while it is empty. */
    value: string | null | undefined;
    children: ReactNode;
    /** Accessible name when the visible content is an icon. */
    "aria-label"?: string;
    /** A fully styled button instead of the small secondary one. */
    className?: string;
}

/** A copy action that always reports its outcome next to the button. */
export function CopyButton({ value, children, className, "aria-label": ariaLabel }: CopyButtonProps) {
    const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
    const manualRef = useRef<HTMLInputElement>(null);
    const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const text = value ?? "";

    useEffect(() => () => {
        if (timer.current) clearTimeout(timer.current);
    }, []);

    useEffect(() => {
        if (state === "failed") {
            manualRef.current?.focus();
            manualRef.current?.select();
        }
    }, [state]);

    async function handleCopy() {
        if (timer.current) clearTimeout(timer.current);
        const copied = await copyText(text);
        setState(copied ? "copied" : "failed");
        if (copied) {
            timer.current = setTimeout(() => setState("idle"), COPIED_FOR_MS);
        }
    }

    const button = className ? (
        <button aria-label={ariaLabel} className={className} disabled={!text} onClick={() => void handleCopy()} type="button">
            {children}
        </button>
    ) : (
        <Button aria-label={ariaLabel} disabled={!text} onClick={() => void handleCopy()} size="sm" variant="secondary">
            {children}
        </Button>
    );

    return (
        <span className="inline-flex flex-col items-end gap-1.5">
            <span className="inline-flex items-center gap-2">
                {button}
                <span role="status" className="text-xs font-medium text-ok-ink">
                    {state === "copied" ? "Copied" : ""}
                </span>
            </span>
            {state === "failed" ? (
                <span role="alert" className="block max-w-xs space-y-1.5 rounded-lg bg-risk-soft px-3 py-2 text-left text-xs text-risk-ink">
                    <span className="block">Copy did not work in this browser. The text is selected below; press Ctrl+C (⌘C on a Mac) to copy it.</span>
                    <input
                        aria-label="Text to copy"
                        className="h-8 w-full rounded-md border border-risk-line bg-surface px-2 font-mono text-sm text-ink"
                        onFocus={(event) => event.target.select()}
                        readOnly
                        ref={manualRef}
                        value={text}
                    />
                </span>
            ) : null}
        </span>
    );
}
