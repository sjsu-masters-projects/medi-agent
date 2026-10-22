import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LiveVoiceController, mayBeSpokenEarly, type DraftToSpeak, type SocketLike, type VoiceModeSnapshot } from "@/services/live-voice";
import type { AudioPort } from "@/services/pcm-audio";

class FakeSocket implements SocketLike {
    readyState = 1;
    onopen: SocketLike["onopen"] = null;
    onmessage: SocketLike["onmessage"] = null;
    onclose: SocketLike["onclose"] = null;
    onerror: SocketLike["onerror"] = null;
    sent: (string | ArrayBufferLike | ArrayBufferView)[] = [];
    send(data: string | ArrayBufferLike | ArrayBufferView) { this.sent.push(data); }
    close() { this.readyState = 3; }
    receive(event: Record<string, unknown>) { this.onmessage?.({ data: JSON.stringify(event) }); }
    json() { return this.sent.filter((item): item is string => typeof item === "string").map((item) => JSON.parse(item) as Record<string, unknown>); }
    ofType(type: string) { return this.json().filter((item) => item.type === type); }
    texts() { return this.ofType("tts_text").map((item) => item.text as string); }
}

class FakeAudio implements AudioPort {
    stops = 0;
    async open() { /* no-op */ }
    async beginCapture() { /* no-op */ }
    setMuted() { /* no-op */ }
    playChunk() { /* no-op */ }
    finishSpeech(_id: string, onDrained: () => void) { onDrained(); }
    stopPlayback() { this.stops += 1; }
    isPlaying() { return false; }
    close() { /* no-op */ }
}

async function setup() {
    const socket = new FakeSocket();
    const audio = new FakeAudio();
    const snapshots: VoiceModeSnapshot[] = [];
    const controller = new LiveVoiceController({
        language: "en-US", audio, createSocket: () => socket,
        sendUtterance: () => "sent", onChange: (s) => snapshots.push(s),
    });
    await controller.start();
    socket.receive({ type: "voice_ready", live_stt_supported: true, tts_stream_supported: true, sample_rate: 16000, max_session_seconds: 900 });
    socket.receive({ type: "voice_session_started", sample_rate: 16000 });
    await Promise.resolve();
    socket.receive({ type: "utterance_final", transcript: "when do I take metformin", language: "en-US" });
    return { controller, socket, audio, snapshots };
}

const draft = (text: string, extra: Partial<DraftToSpeak> = {}): DraftToSpeak =>
    ({ text, intent: "medication_question", urgency: "routine", generation: 1, ...extra });

const startedId = (socket: FakeSocket) => socket.ofType("tts_stream_start")[0].speech_id as string;
const reply = (text: string, urgent = false) => ({ text, language: "en-US" as const, urgent });

describe("speaking from a draft", () => {
    beforeEach(() => { vi.useFakeTimers(); });
    afterEach(() => { vi.useRealTimers(); });

    it("only routine, directly answered drafts may be spoken early", () => {
        expect(mayBeSpokenEarly({ intent: "medication_question", urgency: "routine" })).toBe(true);
        expect(mayBeSpokenEarly({ intent: "symptom", urgency: "routine" })).toBe(false);
        expect(mayBeSpokenEarly({ intent: "medication_question", urgency: "urgent" })).toBe(false);
        expect(mayBeSpokenEarly({ intent: "symptom", urgency: "emergency" })).toBe(false);
    });

    it("starts the speech stream with the first text and sends only what is new", async () => {
        const { controller, socket } = await setup();
        controller.speakDraft(draft("Take it with food. "));
        controller.speakDraft(draft("Take it with food. Ask us if that changes."));
        controller.speakDraft(draft("Take it with food. Ask us if that changes."));
        expect(socket.ofType("tts_stream_start")).toHaveLength(1);
        expect(socket.texts()).toEqual(["Take it with food. ", "Ask us if that changes."]);
        expect(socket.ofType("tts_end")).toHaveLength(0);
    });

    it("finishes the same stream when the saved reply continues the draft", async () => {
        const { controller, socket, audio } = await setup();
        controller.speakDraft(draft("Take it with food."));
        const id = startedId(socket);
        socket.receive({ type: "tts_start", speech_id: id, sample_rate: 24000 });
        expect(controller.getSnapshot().state).toBe("speaking");
        expect(controller.speakReply(reply("Take it with food. Ask us if that changes.\n\nSource: MedlinePlus: Metformin (checked Oct 1, 2026)"))).toBe(true);
        expect(socket.ofType("tts_stream_start")).toHaveLength(1);
        expect(socket.texts().join("")).toContain("Ask us if that changes.");
        expect(socket.ofType("tts_end")).toHaveLength(1);
        expect(audio.stops).toBe(0);
    });

    it("stops the audio and speaks the saved reply when it differs from what was said", async () => {
        const { controller, socket, audio } = await setup();
        controller.speakDraft(draft("Take it with food."));
        const first = startedId(socket);
        socket.receive({ type: "tts_start", speech_id: first, sample_rate: 24000 });
        controller.speakReply(reply("Please contact your care team before taking it."));
        expect(audio.stops).toBeGreaterThan(0);
        expect(socket.ofType("tts_cancel").map((m) => m.speech_id)).toContain(first);
        const starts = socket.ofType("tts_stream_start");
        expect(starts).toHaveLength(2);
        const second = starts[1].speech_id as string;
        expect(second).not.toBe(first);
        const full = socket.json().filter((m) => m.type === "tts_text" && m.speech_id === second);
        expect(full.map((m) => m.text)).toEqual(["Please contact your care team before taking it."]);
        expect(socket.json().some((m) => m.type === "tts_end" && m.speech_id === second)).toBe(true);
    });

    it("withdraws speech when the draft is withdrawn and restarted", async () => {
        const { controller, socket, audio } = await setup();
        controller.speakDraft(draft("Half an answer. "));
        socket.receive({ type: "tts_start", speech_id: startedId(socket), sample_rate: 24000 });
        controller.speakDraft(draft("", { generation: 2 }));
        controller.speakDraft(draft("Something else.", { generation: 2 }));
        expect(audio.stops).toBeGreaterThan(0);
        expect(socket.ofType("tts_cancel")).toHaveLength(1);
        expect(socket.ofType("tts_stream_start")).toHaveLength(1); // nothing more from drafts this turn
        controller.speakReply(reply("Something else."));
        expect(socket.ofType("tts_stream_start")).toHaveLength(2);
        expect(controller.getSnapshot().state).not.toBe("error");
    });

    it("a draft that stops being an extension is never spoken from again", async () => {
        const { controller, socket } = await setup();
        controller.speakDraft(draft("Take it with food. "));
        controller.speakDraft(draft("Do not take it. "));
        expect(socket.ofType("tts_cancel")).toHaveLength(1);
        controller.speakDraft(draft("Do not take it. Call us."));
        expect(socket.texts()).toEqual(["Take it with food. "]);
    });

    it.each([
        ["urgent", { urgency: "urgent" }],
        ["emergency", { urgency: "emergency" }],
        ["guided symptom flow", { intent: "symptom" }],
    ])("does not speak a %s draft; the saved reply is spoken once, whole", async (_name, extra) => {
        const { controller, socket } = await setup();
        controller.speakDraft(draft("Call 911 now. ", extra));
        controller.speakDraft(draft("Call 911 now. Stay on the line.", extra));
        expect(socket.ofType("tts_stream_start")).toHaveLength(0);
        controller.speakReply(reply("Call 911 now. Stay on the line.", true));
        const start = socket.ofType("tts_stream_start");
        expect(start).toHaveLength(1);
        expect(start[0].interruptible).toBe(false);
    });

    it("an urgent saved reply replaces early speech and cannot be interrupted", async () => {
        const { controller, socket, audio } = await setup();
        controller.speakDraft(draft("It is fine. "));
        socket.receive({ type: "tts_start", speech_id: startedId(socket), sample_rate: 24000 });
        controller.speakReply(reply("Call 911 now.", true));
        expect(audio.stops).toBeGreaterThan(0);
        const starts = socket.ofType("tts_stream_start");
        expect(starts[1].interruptible).toBe(false);
    });

    it("a patient who talks over the early speech is not talked over by the saved reply", async () => {
        const { controller, socket } = await setup();
        controller.speakDraft(draft("Take it with food. "));
        const id = startedId(socket);
        socket.receive({ type: "tts_start", speech_id: id, sample_rate: 24000 });
        socket.receive({ type: "speech_started" });
        expect(socket.ofType("tts_cancel")).toHaveLength(1);
        controller.speakDraft(draft("Take it with food. More."));
        expect(controller.speakReply(reply("Take it with food. More."))).toBe(false);
        expect(socket.ofType("tts_stream_start")).toHaveLength(1);
    });

    it("a provider error during early speech falls back to speaking the saved reply", async () => {
        const { controller, socket } = await setup();
        controller.speakDraft(draft("Take it with food. "));
        const id = startedId(socket);
        socket.receive({ type: "tts_start", speech_id: id, sample_rate: 24000 });
        socket.receive({ type: "tts_error", speech_id: id, reason: "provider_error" });
        expect(controller.getSnapshot().state).toBe("thinking");
        expect(controller.speakReply(reply("Take it with food."))).toBe(true);
        expect(socket.ofType("tts_stream_start")).toHaveLength(2);
    });

    it("a failed turn stops early speech and reports it", async () => {
        const { controller, socket, audio } = await setup();
        controller.speakDraft(draft("Take it with food. "));
        socket.receive({ type: "tts_start", speech_id: startedId(socket), sample_rate: 24000 });
        controller.noReply();
        expect(audio.stops).toBeGreaterThan(0);
        expect(controller.getSnapshot()).toMatchObject({ state: "listening", notice: "reply_failed" });
    });

    it("ignores drafts when no reply is awaited (for example after a reload)", async () => {
        const { controller, socket } = await setup();
        controller.noReply();
        controller.speakDraft(draft("Late text. "));
        expect(socket.ofType("tts_stream_start")).toHaveLength(0);
    });

    it("gives up on a reply that never becomes final", async () => {
        const { controller, socket } = await setup();
        controller.speakDraft(draft("Take it with food. "));
        socket.receive({ type: "tts_start", speech_id: startedId(socket), sample_rate: 24000 });
        vi.advanceTimersByTime(121_000);
        expect(controller.getSnapshot().notice).toBe("reply_failed");
    });
});
