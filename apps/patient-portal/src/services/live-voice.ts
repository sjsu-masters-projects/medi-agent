/**
 * Live voice mode controller (VOICE-001).
 *
 * Framework-free state machine: microphone PCM goes to the backend voice websocket, the
 * backend returns partial and final transcripts, each final utterance becomes an ordinary
 * chat message through `sendUtterance`, and the reply text is handed back through
 * `speakReply` to stream as audio. A finalized transcript is passed on the moment it
 * arrives, so nothing the patient said is lost to a later failure.
 *
 *   connecting -> listening -> hearing -> thinking -> speaking -> listening
 *                    ^ paused (mic muted) ^                 ^ barge-in returns to hearing
 */
import { VoiceAudioError, type AudioPort } from "@/services/pcm-audio";
import type { Locale as ChatLocale } from "@/types";

export type VoiceModeState = "connecting" | "listening" | "hearing" | "thinking" | "speaking" | "paused" | "ended" | "error";

export type VoiceModeErrorCode =
    | "permission_denied"
    | "no_microphone"
    | "unsupported"
    | "provider_unavailable"
    | "network"
    | "session_limit"
    | "idle_timeout"
    | "failed";

/** A short, non-fatal condition shown beside the panel; voice mode keeps running. */
export type VoiceModeNotice = "speech_unavailable" | "not_sent" | "reply_failed" | "interrupted_by_limit" | null;

export interface VoiceModeSnapshot {
    state: VoiceModeState;
    partial: string;
    error: VoiceModeErrorCode | null;
    notice: VoiceModeNotice;
    /** Deterministic safety guidance for the last utterance, shown as text and never lost. */
    guidance: string | null;
    paused: boolean;
    startedAt: number | null;
    maxSessionSeconds: number | null;
}

export interface SocketLike {
    readyState: number;
    onopen: ((event: unknown) => void) | null;
    onmessage: ((event: { data: unknown }) => void) | null;
    onclose: ((event: unknown) => void) | null;
    onerror: ((event: unknown) => void) | null;
    send(data: string | ArrayBufferLike | ArrayBufferView): void;
    close(code?: number, reason?: string): void;
}

export type UtteranceResult = "sent" | "handled" | "unavailable";

export interface ReplyToSpeak {
    text: string;
    language: ChatLocale;
    /** An emergency reply is spoken to the end; nothing the patient says cuts it off. */
    urgent: boolean;
}

export interface LiveVoiceOptions {
    language: ChatLocale;
    createSocket: () => SocketLike;
    audio: AudioPort;
    sendUtterance: (text: string, language: ChatLocale) => UtteranceResult;
    onChange: (snapshot: VoiceModeSnapshot) => void;
    onLevel?: (level: number) => void;
    /** Injected for tests. */
    now?: () => number;
}

const OPEN = 1;
/** Local speech detection while Nora talks: sustained level above the echo floor. */
const BARGE_IN_LEVEL = 0.1;
const BARGE_IN_FRAMES = 6;
const SESSION_START_TIMEOUT_MS = 10_000;
const SPEECH_START_TIMEOUT_MS = 12_000;
const THINKING_TIMEOUT_MS = 120_000;
const END_LINGER_MS = 1_500;
const DEFAULT_SAMPLE_RATE = 16_000;
const DEFAULT_TTS_RATE = 24_000;

let speechCounter = 0;

function speechId(): string {
    speechCounter += 1;
    return `sp${Date.now().toString(36)}${speechCounter}`;
}

export class LiveVoiceController {
    private snapshot: VoiceModeSnapshot = {
        state: "connecting", partial: "", error: null, notice: null, guidance: null,
        paused: false, startedAt: null, maxSessionSeconds: null,
    };
    private socket: SocketLike | null = null;
    private reconnected = false;
    private closing = false;
    private disposed = false;
    private sampleRate = DEFAULT_SAMPLE_RATE;
    private ttsSupported = true;
    private captureStarted = false;
    private awaitingReply = false;
    private speech: { id: string; interruptible: boolean; started: boolean; sampleRate: number } | null = null;
    private loudFrames = 0;
    private timers = new Set<ReturnType<typeof setTimeout>>();
    private startTimer: ReturnType<typeof setTimeout> | null = null;
    private speechTimer: ReturnType<typeof setTimeout> | null = null;
    private thinkingTimer: ReturnType<typeof setTimeout> | null = null;
    private readonly now: () => number;

    constructor(private readonly options: LiveVoiceOptions) {
        this.now = options.now ?? Date.now;
    }

    getSnapshot(): VoiceModeSnapshot {
        return this.snapshot;
    }

    /** Must be called from the tap that opens voice mode: the microphone prompt needs the gesture. */
    async start(): Promise<void> {
        this.update({ state: "connecting" });
        try {
            await this.options.audio.open();
        } catch (error) {
            this.fail(error instanceof VoiceAudioError ? error.code : "failed");
            return;
        }
        if (this.disposed) return;
        this.connect();
    }

    private connect(): void {
        const socket = this.options.createSocket();
        this.socket = socket;
        this.startTimer = this.later(() => {
            if (this.snapshot.state === "connecting") this.lostConnection("provider_unavailable");
        }, SESSION_START_TIMEOUT_MS);
        socket.onmessage = (event) => {
            if (this.socket === socket) this.handleMessage(event.data);
        };
        socket.onclose = () => {
            if (this.socket !== socket) return;
            this.socket = null;
            if (!this.closing && !this.disposed) this.lostConnection("network");
        };
        socket.onerror = () => undefined;
    }

    // -- server events ------------------------------------------------------------------

    private handleMessage(data: unknown): void {
        if (typeof data !== "string") return;
        let event: Record<string, unknown>;
        try {
            const parsed: unknown = JSON.parse(data);
            if (!parsed || typeof parsed !== "object") return;
            event = parsed as Record<string, unknown>;
        } catch {
            return;
        }
        switch (event.type) {
            case "voice_ready":
                this.onReady(event);
                return;
            case "voice_session_started":
                this.onStarted(event);
                return;
            case "speech_started":
                this.onSpeechStarted();
                return;
            case "transcript_partial":
                if (typeof event.transcript === "string" && !this.closing) {
                    this.update({ partial: event.transcript, state: this.hearingState() });
                }
                return;
            case "utterance_final":
                this.onUtterance(event);
                return;
            case "tts_start":
                this.onTtsStart(event);
                return;
            case "tts_audio":
                this.onTtsAudio(event);
                return;
            case "tts_end":
                this.onTtsEnd(event);
                return;
            case "tts_cancelled":
                if (this.isCurrent(event)) this.finishSpeaking();
                return;
            case "tts_error":
                if (this.isCurrent(event)) {
                    this.options.audio.stopPlayback();
                    this.speech = null;
                    this.clearSpeechTimer();
                    this.update({ notice: "speech_unavailable" });
                    this.settle();
                }
                return;
            case "voice_error":
                this.onVoiceError(event);
                return;
            case "voice_session_ended":
                this.onEnded(event);
                return;
            default:
        }
    }

    private onReady(event: Record<string, unknown>): void {
        if (event.live_stt_supported === false) {
            this.fail("provider_unavailable");
            return;
        }
        if (typeof event.sample_rate === "number") this.sampleRate = event.sample_rate;
        this.ttsSupported = event.tts_stream_supported !== false;
        const max = typeof event.max_session_seconds === "number" ? event.max_session_seconds : null;
        this.update({ maxSessionSeconds: max });
        this.send({ type: "voice_session_start", language: this.options.language });
    }

    private onStarted(event: Record<string, unknown>): void {
        this.clearStartTimer();
        if (typeof event.sample_rate === "number") this.sampleRate = event.sample_rate;
        if (!this.captureStarted) {
            this.captureStarted = true;
            this.options.audio
                .beginCapture(this.sampleRate, (frame) => this.sendFrame(frame), (level) => this.onLevel(level))
                .catch((error: unknown) => this.fail(error instanceof VoiceAudioError ? error.code : "failed"));
        }
        if (this.snapshot.paused) this.options.audio.setMuted(true);
        this.update({ state: this.snapshot.paused ? "paused" : "listening", startedAt: this.snapshot.startedAt ?? this.now() });
        this.reportState();
    }

    private onSpeechStarted(): void {
        if (this.closing || this.snapshot.paused) return;
        if (this.snapshot.state === "speaking") this.bargeIn();
        else if (this.snapshot.state === "listening" || this.snapshot.state === "thinking") this.update({ state: "hearing" });
    }

    private onUtterance(event: Record<string, unknown>): void {
        const text = typeof event.transcript === "string" ? event.transcript.trim() : "";
        if (!text) {
            this.update({ partial: "" });
            this.settle();
            return;
        }
        const language: ChatLocale = event.language === "es-MX" ? "es-MX" : event.language === "en-US" ? "en-US" : this.options.language;
        const guidance = typeof event.safety_guidance === "string" && event.safety_guidance ? event.safety_guidance : null;
        // The transcript is handed to the chat first, in every state, so closing never loses it.
        const result = this.options.sendUtterance(text, language);
        if (this.closing) return;
        if (result === "sent") {
            this.awaitingReply = true;
            this.update({ partial: "", guidance: guidance ?? this.snapshot.guidance, notice: null, state: "thinking" });
            this.reportState();
            this.thinkingTimer = this.later(() => this.noReply(), THINKING_TIMEOUT_MS);
        } else {
            this.update({ partial: "", guidance: guidance ?? this.snapshot.guidance, notice: result === "unavailable" ? "not_sent" : null });
            this.settle();
        }
    }

    private onVoiceError(event: Record<string, unknown>): void {
        const code = typeof event.code === "string" ? event.code : "";
        if (code === "voice_live_unavailable" || code === "voice_live_busy") this.fail("provider_unavailable");
        // Oversized frames, duplicate starts and validation errors are not the patient's to fix.
    }

    private onEnded(event: Record<string, unknown>): void {
        const reason = typeof event.reason === "string" ? event.reason : "";
        if (this.closing || reason === "client") {
            this.finishEnd();
            return;
        }
        if (reason === "max_session") this.fail("session_limit");
        else if (reason === "idle_timeout") this.fail("idle_timeout");
        else this.lostConnection("provider_unavailable");
    }

    // -- speech ---------------------------------------------------------------------------

    private isCurrent(event: Record<string, unknown>): boolean {
        return this.speech !== null && event.speech_id === this.speech.id;
    }

    private onTtsStart(event: Record<string, unknown>): void {
        if (!this.isCurrent(event) || !this.speech) return;
        this.speech.started = true;
        if (typeof event.sample_rate === "number") this.speech.sampleRate = event.sample_rate;
        this.clearSpeechTimer();
        this.loudFrames = 0;
        this.update({ state: "speaking", partial: "" });
        this.reportState();
    }

    private onTtsAudio(event: Record<string, unknown>): void {
        if (!this.isCurrent(event) || typeof event.audio_base64 !== "string") return;
        this.options.audio.playChunk(this.speech!.id, event.audio_base64, this.speech!.sampleRate);
    }

    private onTtsEnd(event: Record<string, unknown>): void {
        if (!this.isCurrent(event) || !this.speech) return;
        const id = this.speech.id;
        this.options.audio.finishSpeech(id, () => {
            if (this.speech?.id === id) this.finishSpeaking();
        });
    }

    private finishSpeaking(): void {
        this.options.audio.stopPlayback();
        this.speech = null;
        this.clearSpeechTimer();
        this.settle();
    }

    /** Ask for Nora's reply to be spoken. False when it cannot be, so the reply stays text. */
    speakReply(reply: ReplyToSpeak): boolean {
        if (!this.awaitingReply || this.closing || this.disposed) return false;
        this.awaitingReply = false;
        this.clearThinkingTimer();
        if (this.snapshot.state !== "thinking" || !this.ttsSupported || !this.socketOpen()) {
            this.update({ notice: this.snapshot.state === "thinking" ? "speech_unavailable" : this.snapshot.notice });
            this.settle();
            return false;
        }
        const id = speechId();
        this.speech = { id, interruptible: !reply.urgent, started: false, sampleRate: DEFAULT_TTS_RATE };
        this.send({ type: "tts_stream_start", speech_id: id, language: reply.language, interruptible: !reply.urgent });
        this.send({ type: "tts_text", speech_id: id, text: reply.text });
        this.send({ type: "tts_end", speech_id: id });
        this.speechTimer = this.later(() => {
            if (this.speech?.id === id && !this.speech.started) {
                this.speech = null;
                this.update({ notice: "speech_unavailable" });
                this.settle();
            }
        }, SPEECH_START_TIMEOUT_MS);
        return true;
    }

    /** The turn ended without a reply (error, timeout): back to listening, the chat shows why. */
    noReply(): void {
        if (!this.awaitingReply) return;
        this.awaitingReply = false;
        this.clearThinkingTimer();
        this.update({ notice: "reply_failed" });
        this.settle();
    }

    isAwaitingReply(): boolean {
        return this.awaitingReply;
    }

    private bargeIn(): void {
        const speech = this.speech;
        if (!speech || !speech.interruptible) return;
        this.options.audio.stopPlayback();
        this.speech = null;
        this.clearSpeechTimer();
        this.send({ type: "tts_cancel", speech_id: speech.id });
        this.loudFrames = 0;
        this.update({ state: this.hearingState() });
        this.reportState();
    }

    private onLevel(level: number): void {
        this.options.onLevel?.(this.snapshot.paused ? 0 : level);
        if (this.snapshot.state !== "speaking" || !this.speech?.interruptible) {
            this.loudFrames = 0;
            return;
        }
        this.loudFrames = level >= BARGE_IN_LEVEL ? this.loudFrames + 1 : 0;
        if (this.loudFrames >= BARGE_IN_FRAMES) this.bargeIn();
    }

    // -- controls -------------------------------------------------------------------------

    setPaused(paused: boolean): void {
        if (this.closing || this.disposed || this.snapshot.state === "error") return;
        this.options.audio.setMuted(paused);
        this.update({ paused, partial: "" });
        if (this.snapshot.state === "listening" || this.snapshot.state === "hearing" || this.snapshot.state === "paused") {
            this.update({ state: paused ? "paused" : "listening" });
        }
        this.reportState();
    }

    /**
     * End voice mode. The microphone and playback stop at once; the socket lingers briefly so
     * speech the provider had finished but not yet reported still reaches the chat.
     */
    end(): void {
        if (this.closing || this.disposed) return;
        this.closing = true;
        this.releaseAudio();
        this.speech = null;
        this.awaitingReply = false;
        this.clearTimers();
        this.update({ state: "ended", partial: "" });
        if (this.socketOpen()) {
            this.send({ type: "voice_session_stop" });
            this.later(() => this.finishEnd(), END_LINGER_MS);
        } else {
            this.finishEnd();
        }
    }

    /** Hard stop for unmount, sign-out and every other exit path. Idempotent. */
    dispose(): void {
        if (this.disposed) return;
        this.disposed = true;
        this.closing = true;
        this.releaseAudio();
        this.clearTimers();
        this.closeSocket();
        if (this.snapshot.state !== "error") this.snapshot = { ...this.snapshot, state: "ended" };
    }

    private finishEnd(): void {
        this.clearTimers();
        this.closeSocket();
        this.disposed = true;
    }

    private releaseAudio(): void {
        this.options.audio.stopPlayback();
        this.options.audio.close();
        this.options.onLevel?.(0);
    }

    // -- failure and reconnect ------------------------------------------------------------

    private lostConnection(code: VoiceModeErrorCode): void {
        if (this.closing || this.disposed) return;
        if (!this.reconnected && code === "network") {
            // One quiet reconnect; the microphone stays open and nothing finalized is lost.
            this.reconnected = true;
            this.options.audio.stopPlayback();
            this.speech = null;
            this.closeSocket();
            this.update({ state: "connecting", partial: "" });
            this.connect();
            return;
        }
        this.fail(code);
    }

    private fail(code: VoiceModeErrorCode): void {
        if (this.disposed && this.snapshot.state === "error") return;
        this.closing = true;
        this.disposed = true;
        this.awaitingReply = false;
        this.speech = null;
        this.clearTimers();
        this.releaseAudio();
        if (this.socketOpen()) this.send({ type: "voice_session_stop" });
        this.closeSocket();
        this.update({ state: "error", error: code, partial: "" });
    }

    // -- internals ------------------------------------------------------------------------

    private hearingState(): VoiceModeState {
        return this.snapshot.paused ? "paused" : "hearing";
    }

    /** Back to the resting state: listening, or paused when the mic is muted. */
    private settle(): void {
        if (this.closing || this.snapshot.state === "error") return;
        this.update({ state: this.snapshot.paused ? "paused" : "listening" });
        this.reportState();
    }

    private reportState(): void {
        const state = this.snapshot.state;
        const mapped = state === "hearing" ? "listening" : state;
        if (mapped === "listening" || mapped === "thinking" || mapped === "speaking" || mapped === "paused") {
            this.send({ type: "voice_state", state: mapped });
        }
    }

    private sendFrame(frame: ArrayBuffer): void {
        if (this.socketOpen() && !this.closing && !this.snapshot.paused) this.socket!.send(frame);
    }

    private send(payload: Record<string, unknown>): void {
        if (this.socketOpen()) this.socket!.send(JSON.stringify(payload));
    }

    private socketOpen(): boolean {
        return this.socket !== null && this.socket.readyState === OPEN;
    }

    private closeSocket(): void {
        const socket = this.socket;
        this.socket = null;
        if (socket) {
            socket.onmessage = null;
            socket.onclose = null;
            try { socket.close(1000, "voice mode ended"); } catch { /* already closed */ }
        }
    }

    private update(patch: Partial<VoiceModeSnapshot>): void {
        const next = { ...this.snapshot, ...patch };
        const changed = (Object.keys(next) as (keyof VoiceModeSnapshot)[]).some((key) => next[key] !== this.snapshot[key]);
        if (!changed) return;
        this.snapshot = next;
        this.options.onChange(next);
    }

    private later(callback: () => void, ms: number): ReturnType<typeof setTimeout> {
        const timer = setTimeout(() => {
            this.timers.delete(timer);
            callback();
        }, ms);
        this.timers.add(timer);
        return timer;
    }

    private clearTimer(timer: ReturnType<typeof setTimeout> | null): void {
        if (timer) {
            clearTimeout(timer);
            this.timers.delete(timer);
        }
    }

    private clearStartTimer(): void { this.clearTimer(this.startTimer); this.startTimer = null; }
    private clearSpeechTimer(): void { this.clearTimer(this.speechTimer); this.speechTimer = null; }
    private clearThinkingTimer(): void { this.clearTimer(this.thinkingTimer); this.thinkingTimer = null; }

    private clearTimers(): void {
        for (const timer of this.timers) clearTimeout(timer);
        this.timers.clear();
    }
}
