import { fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { VoiceModePanel, tailTranscript } from "@/components/features/voice-mode-panel";
import { getVoiceModeCopy } from "@/content/chat-copy";
import type { VoiceModeSnapshot } from "@/services/live-voice";

const base: VoiceModeSnapshot = { state: "listening", partial: "", error: null, notice: null, guidance: null, paused: false, startedAt: 1, maxSessionSeconds: 900 };

function show(snapshot: Partial<VoiceModeSnapshot>, locale: "en-US" | "es-MX" = "en-US", remaining: number | null = null) {
    const handlers = { onTogglePause: vi.fn(), onEnd: vi.fn(), onRetry: vi.fn(), onUseText: vi.fn() };
    render(<VoiceModePanel snapshot={{ ...base, ...snapshot }} locale={locale} remainingSeconds={remaining} ringRef={createRef()} {...handlers} />);
    return handlers;
}

describe("VoiceModePanel", () => {
    it.each(["en-US", "es-MX"] as const)("renders every state in %s", (locale) => {
        const copy = getVoiceModeCopy(locale);
        for (const [state, text] of [["listening", copy.status.listening], ["hearing", copy.status.hearing], ["thinking", copy.status.thinking], ["speaking", copy.status.speaking]] as const) {
            const { unmount } = render(<VoiceModePanel snapshot={{ ...base, state }} locale={locale} remainingSeconds={null} ringRef={createRef()} onTogglePause={vi.fn()} onEnd={vi.fn()} onRetry={vi.fn()} onUseText={vi.fn()} />);
            expect(screen.getByText(text)).toBeTruthy();
            expect(screen.getByRole("button", { name: copy.pause })).toBeTruthy();
            expect(screen.getByRole("button", { name: copy.end })).toBeTruthy();
            unmount();
        }
    });

    it("announces the status politely and shows the live partial transcript", () => {
        show({ state: "hearing", partial: "when is my next appointment" });
        expect(screen.getByText("Hearing you…").getAttribute("aria-live")).toBe("polite");
        expect(screen.getByText("when is my next appointment")).toBeTruthy();
    });

    it("keeps the end of a long transcript", () => {
        const text = `${"a".repeat(200)} the newest words`;
        expect(tailTranscript(text).endsWith("the newest words")).toBe(true);
        expect(tailTranscript(text).startsWith("…")).toBe(true);
    });

    it("pause and end buttons call back and show Resume while paused", () => {
        const handlers = show({ state: "paused", paused: true });
        fireEvent.click(screen.getByRole("button", { name: "Resume" }));
        fireEvent.click(screen.getByRole("button", { name: "End voice mode" }));
        expect(handlers.onTogglePause).toHaveBeenCalled();
        expect(handlers.onEnd).toHaveBeenCalled();
        expect(screen.getByText("Microphone paused")).toBeTruthy();
    });

    it("shows the time hint only when remaining time is given", () => {
        show({}, "en-US", 95);
        expect(screen.getByText("1:35 left in this voice session")).toBeTruthy();
    });

    it("shows an inline error with try again and use text actions", () => {
        const handlers = show({ state: "error", error: "permission_denied" }, "es-MX");
        expect(screen.getByRole("alert").textContent).toContain(getVoiceModeCopy("es-MX").errors.permission_denied);
        fireEvent.click(screen.getByRole("button", { name: "Intentar de nuevo" }));
        fireEvent.click(screen.getByRole("button", { name: "Usar texto" }));
        expect(handlers.onRetry).toHaveBeenCalled();
        expect(handlers.onUseText).toHaveBeenCalled();
    });

    it("keeps safety guidance visible as an alert", () => {
        show({ guidance: "Call 911 now." });
        expect(screen.getByRole("alert").textContent).toBe("Call 911 now.");
    });
});
