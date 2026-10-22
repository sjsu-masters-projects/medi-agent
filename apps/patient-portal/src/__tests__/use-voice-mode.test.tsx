import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useVoiceMode, type VoiceReply } from "@/hooks/use-voice-mode";
import type { SocketLike } from "@/services/live-voice";
import type { AudioPort } from "@/services/pcm-audio";

function fakes() {
    const socket: SocketLike & { sent: unknown[]; closed: boolean } = {
        readyState: 1, onopen: null, onmessage: null, onclose: null, onerror: null, sent: [], closed: false,
        send(data) { this.sent.push(data); },
        close() { this.closed = true; },
    };
    const audio = {
        open: vi.fn(async () => undefined), beginCapture: vi.fn(async () => undefined), setMuted: vi.fn(), playChunk: vi.fn(),
        finishSpeech: vi.fn(), stopPlayback: vi.fn(), isPlaying: () => false, close: vi.fn(),
    } satisfies AudioPort;
    return { socket, audio };
}
const receive = (socket: SocketLike, event: Record<string, unknown>) => act(async () => { socket.onmessage?.({ data: JSON.stringify(event) }); await Promise.resolve(); });

function mount(reply: VoiceReply | null = null, sendUtterance = vi.fn(() => "sent" as const)) {
    const { socket, audio } = fakes();
    const hook = renderHook((props: { reply: VoiceReply | null; token: string | null }) => useVoiceMode({
        patientId: "p1", accessToken: props.token, scope: "s1", locale: "en-US", sendUtterance, reply: props.reply, chatError: null,
        createAudio: () => audio, createSocket: () => socket,
    }), { initialProps: { reply, token: "t" as string | null } });
    return { hook, socket, audio, sendUtterance };
}

describe("useVoiceMode", () => {
    afterEach(() => vi.useRealTimers());

    it("starts, sends the finalized utterance as a chat message and speaks the reply once", async () => {
        const { hook, socket, sendUtterance } = mount();
        await act(async () => { hook.result.current.start(); await Promise.resolve(); });
        await receive(socket, { type: "voice_ready", live_stt_supported: true, tts_stream_supported: true, sample_rate: 16000, max_session_seconds: 900 });
        await receive(socket, { type: "voice_session_started" });
        expect(hook.result.current.snapshot?.state).toBe("listening");
        await receive(socket, { type: "utterance_final", transcript: "hello", language: "en-US" });
        expect(sendUtterance).toHaveBeenCalledWith("hello", "en-US");
        expect(hook.result.current.snapshot?.state).toBe("thinking");
        hook.rerender({ reply: { seq: 1, text: "Hi there.", language: "en-US", urgent: false }, token: "t" });
        const texts = socket.sent.filter((item): item is string => typeof item === "string").map((item) => JSON.parse(item) as { type: string });
        expect(texts.filter((item) => item.type === "tts_stream_start")).toHaveLength(1);
        hook.rerender({ reply: { seq: 1, text: "Hi there.", language: "en-US", urgent: false }, token: "t" });
        expect(socket.sent.filter((item) => typeof item === "string" && item.includes("tts_stream_start"))).toHaveLength(1);
    });

    it("ending closes the audio and the panel goes away", async () => {
        const { hook, audio } = mount();
        await act(async () => { hook.result.current.start(); await Promise.resolve(); });
        act(() => hook.result.current.end());
        expect(audio.close).toHaveBeenCalled();
        expect(hook.result.current.active).toBe(false);
    });

    it("unmount releases the microphone", async () => {
        const { hook, audio, socket } = mount();
        await act(async () => { hook.result.current.start(); await Promise.resolve(); });
        hook.unmount();
        expect(audio.close).toHaveBeenCalled();
        expect(socket.closed).toBe(true);
    });

    it("signing out ends voice mode", async () => {
        const { hook, audio } = mount();
        await act(async () => { hook.result.current.start(); await Promise.resolve(); });
        hook.rerender({ reply: null, token: null });
        expect(audio.close).toHaveBeenCalled();
        expect(hook.result.current.active).toBe(false);
    });

    it("ends when the tab stays hidden", async () => {
        vi.useFakeTimers();
        const { hook, audio } = mount();
        await act(async () => { hook.result.current.start(); await Promise.resolve(); });
        vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
        act(() => { document.dispatchEvent(new Event("visibilitychange")); });
        act(() => { vi.advanceTimersByTime(61_000); });
        expect(audio.close).toHaveBeenCalled();
        expect(hook.result.current.active).toBe(false);
    });
});
