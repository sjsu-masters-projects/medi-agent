import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LiveVoiceController, type SocketLike, type UtteranceResult, type VoiceModeSnapshot } from "@/services/live-voice";
import { VoiceAudioError, type AudioPort } from "@/services/pcm-audio";

class FakeSocket implements SocketLike {
    readyState = 1;
    onopen: SocketLike["onopen"] = null;
    onmessage: SocketLike["onmessage"] = null;
    onclose: SocketLike["onclose"] = null;
    onerror: SocketLike["onerror"] = null;
    sent: (string | ArrayBufferLike | ArrayBufferView)[] = [];
    closed = false;
    send(data: string | ArrayBufferLike | ArrayBufferView) { this.sent.push(data); }
    close() { this.closed = true; this.readyState = 3; }
    receive(event: Record<string, unknown>) { this.onmessage?.({ data: JSON.stringify(event) }); }
    drop() { this.readyState = 3; this.onclose?.({}); }
    json() { return this.sent.filter((item): item is string => typeof item === "string").map((item) => JSON.parse(item) as Record<string, unknown>); }
    types() { return this.json().map((item) => item.type); }
}

class FakeAudio implements AudioPort {
    openError: VoiceAudioError | null = null;
    opened = false;
    closed = false;
    muted = false;
    played: { id: string; rate: number }[] = [];
    stops = 0;
    drain: (() => void) | null = null;
    onFrame: ((frame: ArrayBuffer) => void) | null = null;
    onLevel: ((level: number) => void) | null = null;
    async open() { if (this.openError) throw this.openError; this.opened = true; }
    async beginCapture(_rate: number, onFrame: (frame: ArrayBuffer) => void, onLevel: (level: number) => void) { this.onFrame = onFrame; this.onLevel = onLevel; }
    setMuted(muted: boolean) { this.muted = muted; }
    playChunk(id: string, _base64: string, rate: number) { this.played.push({ id, rate }); }
    finishSpeech(_id: string, onDrained: () => void) { this.drain = onDrained; }
    stopPlayback() { this.stops += 1; }
    isPlaying() { return this.played.length > 0; }
    close() { this.closed = true; }
}

const READY = { type: "voice_ready", live_stt_supported: true, tts_stream_supported: true, sample_rate: 16000, max_session_seconds: 900 };

async function setup(options: { send?: (text: string) => UtteranceResult } = {}) {
    const socket = new FakeSocket();
    const audio = new FakeAudio();
    const snapshots: VoiceModeSnapshot[] = [];
    const sent: { text: string; language: string }[] = [];
    const controller = new LiveVoiceController({
        language: "en-US", audio, createSocket: () => socket,
        sendUtterance: (text, language) => { sent.push({ text, language }); return options.send?.(text) ?? "sent"; },
        onChange: (snapshot) => snapshots.push(snapshot),
    });
    await controller.start();
    socket.receive(READY);
    socket.receive({ type: "voice_session_started", sample_rate: 16000 });
    await Promise.resolve();
    return { controller, socket, audio, snapshots, sent };
}

async function toSpeaking(ctx: Awaited<ReturnType<typeof setup>>, urgent = false) {
    ctx.socket.receive({ type: "utterance_final", transcript: "when is my next visit", language: "en-US" });
    expect(ctx.controller.speakReply({ text: "Tomorrow at 9.", language: "en-US", urgent })).toBe(true);
    const start = ctx.socket.json().find((item) => item.type === "tts_stream_start")!;
    ctx.socket.receive({ type: "tts_start", speech_id: start.speech_id, sample_rate: 24000 });
    ctx.socket.receive({ type: "tts_audio", speech_id: start.speech_id, seq: 1, audio_base64: "AAAA" });
    return start.speech_id as string;
}

describe("LiveVoiceController", () => {
    beforeEach(() => { vi.useFakeTimers(); });
    afterEach(() => { vi.useRealTimers(); });

    it("runs listening -> hearing -> thinking -> speaking -> listening", async () => {
        const ctx = await setup();
        const { controller, socket, audio, sent } = ctx;
        expect(controller.getSnapshot().state).toBe("listening");
        expect(socket.json()[0]).toEqual({ type: "voice_session_start", language: "en-US" });

        socket.receive({ type: "speech_started" });
        expect(controller.getSnapshot().state).toBe("hearing");
        socket.receive({ type: "transcript_partial", transcript: "when is my" });
        expect(controller.getSnapshot().partial).toBe("when is my");

        socket.receive({ type: "utterance_final", transcript: "when is my next visit", language: "en-US" });
        expect(sent).toEqual([{ text: "when is my next visit", language: "en-US" }]);
        expect(controller.getSnapshot()).toMatchObject({ state: "thinking", partial: "" });

        const id = await toSpeakingFrom(ctx);
        expect(controller.getSnapshot().state).toBe("speaking");
        expect(audio.played).toEqual([{ id, rate: 24000 }]);

        socket.receive({ type: "tts_end", speech_id: id });
        audio.drain?.();
        expect(controller.getSnapshot().state).toBe("listening");
        expect(socket.types()).toContain("voice_state");
    });

    async function toSpeakingFrom(ctx: Awaited<ReturnType<typeof setup>>) {
        expect(ctx.controller.speakReply({ text: "Tomorrow at 9 AM.", language: "en-US", urgent: false })).toBe(true);
        const start = ctx.socket.json().find((item) => item.type === "tts_stream_start")!;
        ctx.socket.receive({ type: "tts_start", speech_id: start.speech_id, sample_rate: 24000 });
        ctx.socket.receive({ type: "tts_audio", speech_id: start.speech_id, seq: 1, audio_base64: "AAAA" });
        return start.speech_id as string;
    }

    it("barge-in from the server stops playback and sends the cancel", async () => {
        const ctx = await setup();
        const id = await toSpeaking(ctx);
        const before = ctx.audio.stops;
        ctx.socket.receive({ type: "speech_started" });
        expect(ctx.audio.stops).toBeGreaterThan(before);
        expect(ctx.socket.json()).toContainEqual({ type: "tts_cancel", speech_id: id });
        expect(ctx.controller.getSnapshot().state).toBe("hearing");
    });

    it("barge-in by local level detection stops playback and sends the cancel", async () => {
        const ctx = await setup();
        const id = await toSpeaking(ctx);
        for (let i = 0; i < 6; i += 1) ctx.audio.onLevel?.(0.3);
        expect(ctx.socket.json()).toContainEqual({ type: "tts_cancel", speech_id: id });
        expect(ctx.controller.getSnapshot().state).toBe("hearing");
    });

    it("never interrupts an urgent reply", async () => {
        const ctx = await setup();
        const id = await toSpeaking(ctx, true);
        ctx.socket.receive({ type: "speech_started" });
        for (let i = 0; i < 10; i += 1) ctx.audio.onLevel?.(0.5);
        expect(ctx.socket.json()).not.toContainEqual({ type: "tts_cancel", speech_id: id });
        expect(ctx.controller.getSnapshot().state).toBe("speaking");
    });

    it("falls back to text with a notice when speech fails", async () => {
        const ctx = await setup();
        ctx.socket.receive({ type: "utterance_final", transcript: "hello", language: "en-US" });
        ctx.controller.speakReply({ text: "Hi.", language: "en-US", urgent: false });
        const start = ctx.socket.json().find((item) => item.type === "tts_stream_start")!;
        ctx.socket.receive({ type: "tts_error", speech_id: start.speech_id, reason: "connect" });
        expect(ctx.controller.getSnapshot()).toMatchObject({ state: "listening", notice: "speech_unavailable" });
    });

    it("returns to listening when the speech never starts", async () => {
        const ctx = await setup();
        ctx.socket.receive({ type: "utterance_final", transcript: "hello", language: "en-US" });
        ctx.controller.speakReply({ text: "Hi.", language: "en-US", urgent: false });
        vi.advanceTimersByTime(13_000);
        expect(ctx.controller.getSnapshot()).toMatchObject({ state: "listening", notice: "speech_unavailable" });
    });

    it("keeps the words in the composer path when the chat cannot take them", async () => {
        const ctx = await setup({ send: () => "unavailable" });
        ctx.socket.receive({ type: "utterance_final", transcript: "I feel dizzy", language: "en-US" });
        expect(ctx.sent).toHaveLength(1);
        expect(ctx.controller.getSnapshot()).toMatchObject({ state: "listening", notice: "not_sent" });
    });

    it("shows deterministic safety guidance from the utterance", async () => {
        const ctx = await setup();
        ctx.socket.receive({ type: "utterance_final", transcript: "chest pain", language: "en-US", safety_guidance: "Call 911 now." });
        expect(ctx.controller.getSnapshot().guidance).toBe("Call 911 now.");
    });

    it("reports a denied microphone and releases everything", async () => {
        const audio = new FakeAudio();
        audio.openError = new VoiceAudioError("permission_denied");
        const controller = new LiveVoiceController({ language: "es-MX", audio, createSocket: () => new FakeSocket(), sendUtterance: () => "sent", onChange: () => undefined });
        await controller.start();
        expect(controller.getSnapshot()).toMatchObject({ state: "error", error: "permission_denied" });
        expect(audio.closed).toBe(true);
    });

    it("fails clearly when the provider is unavailable", async () => {
        const socket = new FakeSocket();
        const audio = new FakeAudio();
        const controller = new LiveVoiceController({ language: "en-US", audio, createSocket: () => socket, sendUtterance: () => "sent", onChange: () => undefined });
        await controller.start();
        socket.receive({ type: "voice_ready", live_stt_supported: false });
        expect(controller.getSnapshot()).toMatchObject({ state: "error", error: "provider_unavailable" });
        expect(audio.closed).toBe(true);
    });

    it("surfaces the session limit and idle timeout", async () => {
        const limit = await setup();
        limit.socket.receive({ type: "voice_session_ended", reason: "max_session" });
        expect(limit.controller.getSnapshot()).toMatchObject({ state: "error", error: "session_limit" });
        expect(limit.audio.closed).toBe(true);
        const idle = await setup();
        idle.socket.receive({ type: "voice_session_ended", reason: "idle_timeout" });
        expect(idle.controller.getSnapshot()).toMatchObject({ state: "error", error: "idle_timeout" });
    });

    it("reconnects once after a network drop, then exits cleanly", async () => {
        const sockets = [new FakeSocket(), new FakeSocket()];
        const audio = new FakeAudio();
        let next = 0;
        const controller = new LiveVoiceController({ language: "en-US", audio, createSocket: () => sockets[next++] ?? new FakeSocket(), sendUtterance: () => "sent", onChange: () => undefined });
        await controller.start();
        sockets[0].receive(READY);
        sockets[0].receive({ type: "voice_session_started" });
        sockets[0].drop();
        expect(controller.getSnapshot().state).toBe("connecting");
        sockets[1].receive(READY);
        expect(sockets[1].types()).toContain("voice_session_start");
        sockets[1].receive({ type: "voice_session_started" });
        expect(controller.getSnapshot().state).toBe("listening");
        sockets[1].drop();
        expect(controller.getSnapshot()).toMatchObject({ state: "error", error: "network" });
        expect(audio.closed).toBe(true);
    });

    it("pausing mutes the microphone and stops sending frames", async () => {
        const ctx = await setup();
        ctx.controller.setPaused(true);
        expect(ctx.audio.muted).toBe(true);
        expect(ctx.controller.getSnapshot().state).toBe("paused");
        const framesBefore = ctx.socket.sent.filter((item) => typeof item !== "string").length;
        ctx.audio.onFrame?.(new ArrayBuffer(1280));
        expect(ctx.socket.sent.filter((item) => typeof item !== "string").length).toBe(framesBefore);
        ctx.controller.setPaused(false);
        ctx.audio.onFrame?.(new ArrayBuffer(1280));
        expect(ctx.socket.sent.filter((item) => typeof item !== "string").length).toBe(framesBefore + 1);
        expect(ctx.controller.getSnapshot().state).toBe("listening");
    });

    it("ending stops the microphone at once but still delivers a late final transcript", async () => {
        const ctx = await setup();
        ctx.controller.end();
        expect(ctx.audio.closed).toBe(true);
        expect(ctx.socket.types()).toContain("voice_session_stop");
        ctx.socket.receive({ type: "utterance_final", transcript: "last words", language: "en-US" });
        expect(ctx.sent).toEqual([{ text: "last words", language: "en-US" }]);
        ctx.socket.receive({ type: "voice_session_ended", reason: "client" });
        expect(ctx.socket.closed).toBe(true);
    });

    it("dispose closes audio and the socket and is idempotent", async () => {
        const ctx = await setup();
        ctx.controller.dispose();
        ctx.controller.dispose();
        expect(ctx.audio.closed).toBe(true);
        expect(ctx.socket.closed).toBe(true);
    });

    it("stops waiting when the turn fails", async () => {
        const ctx = await setup();
        ctx.socket.receive({ type: "utterance_final", transcript: "hello", language: "en-US" });
        ctx.controller.noReply();
        expect(ctx.controller.getSnapshot()).toMatchObject({ state: "listening", notice: "reply_failed" });
        expect(ctx.controller.speakReply({ text: "late", language: "en-US", urgent: false })).toBe(false);
    });
});
