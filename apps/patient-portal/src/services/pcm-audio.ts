/**
 * Browser audio for live voice mode (VOICE-001): microphone capture as 16-bit PCM and gapless
 * playback of streamed text-to-speech chunks.
 *
 * Capture: getUserMedia with echo cancellation, an AudioWorklet that forwards raw blocks (a
 * ScriptProcessor only when worklets are unavailable), and a downsampler to the backend's
 * sample rate. Every exit path (`close`) stops all tracks and closes the AudioContext.
 */

export type VoiceAudioErrorCode = "permission_denied" | "no_microphone" | "unsupported" | "failed";

export class VoiceAudioError extends Error {
    constructor(readonly code: VoiceAudioErrorCode) {
        super(code);
        this.name = "VoiceAudioError";
    }
}

/** What the controller needs from the browser; tests supply a fake. */
export interface AudioPort {
    /** Ask for the microphone and create the audio context. Throws VoiceAudioError. */
    open(): Promise<void>;
    /** Start delivering 16-bit mono PCM frames at `targetRate`. */
    beginCapture(targetRate: number, onFrame: (frame: ArrayBuffer) => void, onLevel: (level: number) => void): Promise<void>;
    setMuted(muted: boolean): void;
    playChunk(speechId: string, base64: string, sampleRate: number): void;
    /** Calls back once everything already queued for this speech has been heard. */
    finishSpeech(speechId: string, onDrained: () => void): void;
    stopPlayback(): void;
    isPlaying(): boolean;
    close(): void;
}

/** 40 ms at 16 kHz: inside the 20-100 ms range, small enough for responsive barge-in. */
export const FRAME_MS = 40;

/** Averaging downsampler from the context's rate to the wire rate, 16-bit little-endian. */
export class PcmDownsampler {
    private sum = 0;
    private count = 0;
    private phase = 0;
    private frame: Int16Array;
    private index = 0;
    private readonly frameSamples: number;

    constructor(private readonly targetRate: number, frameMs = FRAME_MS) {
        this.frameSamples = Math.max(1, Math.round((targetRate * frameMs) / 1000));
        this.frame = new Int16Array(this.frameSamples);
    }

    push(input: Float32Array, inputRate: number): Int16Array[] {
        const ratio = inputRate / this.targetRate;
        const frames: Int16Array[] = [];
        for (let i = 0; i < input.length; i += 1) {
            this.sum += input[i];
            this.count += 1;
            this.phase += 1;
            if (this.phase >= ratio) {
                this.phase -= ratio;
                const sample = Math.max(-1, Math.min(1, this.sum / this.count));
                this.frame[this.index] = sample < 0 ? Math.round(sample * 0x8000) : Math.round(sample * 0x7fff);
                this.index += 1;
                this.sum = 0;
                this.count = 0;
                if (this.index === this.frameSamples) {
                    frames.push(this.frame);
                    this.frame = new Int16Array(this.frameSamples);
                    this.index = 0;
                }
            }
        }
        return frames;
    }
}

export function rmsLevel(samples: Float32Array): number {
    if (samples.length === 0) return 0;
    let total = 0;
    for (let i = 0; i < samples.length; i += 1) total += samples[i] * samples[i];
    return Math.sqrt(total / samples.length);
}

/** Little-endian 16-bit PCM bytes to floats in [-1, 1). An odd trailing byte is returned as `rest`. */
export function decodePcm16(bytes: Uint8Array): { samples: Float32Array<ArrayBuffer>; rest: number | null } {
    const count = Math.floor(bytes.length / 2);
    const samples = new Float32Array(count);
    for (let i = 0; i < count; i += 1) {
        const value = (bytes[i * 2] | (bytes[i * 2 + 1] << 8)) << 16 >> 16;
        samples[i] = value / 0x8000;
    }
    return { samples, rest: bytes.length % 2 === 1 ? bytes[bytes.length - 1] : null };
}

function base64ToBytes(base64: string): Uint8Array {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return bytes;
}

const WORKLET_SOURCE = `
class MediagentPcmTap extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel && channel.length) this.port.postMessage(channel.slice(0));
    return true;
  }
}
registerProcessor("mediagent-pcm-tap", MediagentPcmTap);
`;

function audioContextConstructor(): typeof AudioContext | null {
    if (typeof window === "undefined") return null;
    const withWebkit = window as unknown as { webkitAudioContext?: typeof AudioContext };
    return window.AudioContext ?? withWebkit.webkitAudioContext ?? null;
}

export function mapMediaError(error: unknown): VoiceAudioError {
    const name = (error as { name?: string } | null)?.name ?? "";
    if (name === "NotAllowedError" || name === "SecurityError" || name === "PermissionDeniedError") {
        return new VoiceAudioError("permission_denied");
    }
    if (name === "NotFoundError" || name === "DevicesNotFoundError" || name === "OverconstrainedError") {
        return new VoiceAudioError("no_microphone");
    }
    return new VoiceAudioError("failed");
}

export function voiceAudioSupported(): boolean {
    return typeof navigator !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia) && audioContextConstructor() !== null;
}

export class BrowserAudioPort implements AudioPort {
    private stream: MediaStream | null = null;
    private context: AudioContext | null = null;
    private nodes: AudioNode[] = [];
    private workletUrl: string | null = null;
    private muted = false;
    private closed = false;

    // Playback.
    private currentSpeech: string | null = null;
    private nextTime = 0;
    private carry: number | null = null;
    private sources = new Set<AudioBufferSourceNode>();
    private drained: (() => void) | null = null;
    private finished = false;

    async open(): Promise<void> {
        const Context = audioContextConstructor();
        if (!navigator.mediaDevices?.getUserMedia || !Context) throw new VoiceAudioError("unsupported");
        let stream: MediaStream;
        try {
            stream = await navigator.mediaDevices.getUserMedia({
                audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
            });
        } catch (error) {
            throw mapMediaError(error);
        }
        if (this.closed) {
            stream.getTracks().forEach((track) => track.stop());
            throw new VoiceAudioError("failed");
        }
        this.stream = stream;
        try {
            this.context = new Context({ latencyHint: "interactive" });
            if (this.context.state === "suspended") await this.context.resume();
        } catch {
            this.close();
            throw new VoiceAudioError("failed");
        }
    }

    async beginCapture(targetRate: number, onFrame: (frame: ArrayBuffer) => void, onLevel: (level: number) => void): Promise<void> {
        const context = this.context;
        const stream = this.stream;
        if (!context || !stream || this.closed) throw new VoiceAudioError("failed");
        const downsampler = new PcmDownsampler(targetRate);
        const handle = (block: Float32Array) => {
            if (this.closed) return;
            if (this.muted) {
                onLevel(0);
                return;
            }
            onLevel(rmsLevel(block));
            for (const frame of downsampler.push(block, context.sampleRate)) {
                onFrame(frame.buffer as ArrayBuffer);
            }
        };
        const source = context.createMediaStreamSource(stream);
        this.nodes.push(source);
        const sink = context.createGain();
        sink.gain.value = 0;
        sink.connect(context.destination);
        this.nodes.push(sink);

        let tapped = false;
        if (context.audioWorklet && typeof AudioWorkletNode !== "undefined") {
            try {
                this.workletUrl = URL.createObjectURL(new Blob([WORKLET_SOURCE], { type: "application/javascript" }));
                await context.audioWorklet.addModule(this.workletUrl);
                const tap = new AudioWorkletNode(context, "mediagent-pcm-tap", { numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1 });
                tap.port.onmessage = (event: MessageEvent<Float32Array>) => handle(event.data);
                source.connect(tap);
                tap.connect(sink);
                this.nodes.push(tap);
                tapped = true;
            } catch {
                tapped = false;
            }
        }
        if (!tapped) {
            // Only where AudioWorklet is missing. ScriptProcessor is deprecated but universal.
            const processor = context.createScriptProcessor(2048, 1, 1);
            processor.onaudioprocess = (event) => handle(new Float32Array(event.inputBuffer.getChannelData(0)));
            source.connect(processor);
            processor.connect(sink);
            this.nodes.push(processor);
        }
    }

    setMuted(muted: boolean): void {
        this.muted = muted;
        this.stream?.getAudioTracks().forEach((track) => { track.enabled = !muted; });
    }

    playChunk(speechId: string, base64: string, sampleRate: number): void {
        const context = this.context;
        if (!context || this.closed) return;
        if (speechId !== this.currentSpeech) {
            this.stopPlayback();
            this.currentSpeech = speechId;
            this.finished = false;
        }
        let bytes = base64ToBytes(base64);
        if (this.carry !== null) {
            const joined = new Uint8Array(bytes.length + 1);
            joined[0] = this.carry;
            joined.set(bytes, 1);
            bytes = joined;
            this.carry = null;
        }
        const { samples, rest } = decodePcm16(bytes);
        this.carry = rest;
        if (samples.length === 0) return;
        const buffer = context.createBuffer(1, samples.length, sampleRate);
        buffer.copyToChannel(samples, 0);
        const node = context.createBufferSource();
        node.buffer = buffer;
        node.connect(context.destination);
        // A small lead absorbs network jitter on the first chunk; later chunks queue back to back.
        const startAt = Math.max(context.currentTime + 0.04, this.nextTime);
        node.start(startAt);
        this.nextTime = startAt + buffer.duration;
        this.sources.add(node);
        node.onended = () => {
            this.sources.delete(node);
            node.disconnect();
            this.settle();
        };
    }

    finishSpeech(speechId: string, onDrained: () => void): void {
        if (speechId !== this.currentSpeech) {
            onDrained();
            return;
        }
        this.finished = true;
        this.drained = onDrained;
        this.settle();
    }

    private settle(): void {
        if (this.finished && this.sources.size === 0 && this.drained) {
            const done = this.drained;
            this.drained = null;
            this.currentSpeech = null;
            this.finished = false;
            this.nextTime = 0;
            done();
        }
    }

    stopPlayback(): void {
        for (const node of this.sources) {
            node.onended = null;
            try { node.stop(); } catch { /* already stopped */ }
            node.disconnect();
        }
        this.sources.clear();
        this.drained = null;
        this.currentSpeech = null;
        this.finished = false;
        this.carry = null;
        this.nextTime = 0;
    }

    isPlaying(): boolean {
        return this.sources.size > 0;
    }

    close(): void {
        this.closed = true;
        this.stopPlayback();
        for (const node of this.nodes) {
            try { node.disconnect(); } catch { /* already disconnected */ }
        }
        this.nodes = [];
        this.stream?.getTracks().forEach((track) => track.stop());
        this.stream = null;
        const context = this.context;
        this.context = null;
        if (context && context.state !== "closed") void context.close().catch(() => undefined);
        if (this.workletUrl) {
            URL.revokeObjectURL(this.workletUrl);
            this.workletUrl = null;
        }
    }
}
