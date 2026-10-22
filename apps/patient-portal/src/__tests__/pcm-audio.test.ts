import { afterEach, describe, expect, it, vi } from "vitest";
import { BrowserAudioPort, PcmDownsampler, VoiceAudioError, decodePcm16, mapMediaError, rmsLevel } from "@/services/pcm-audio";

describe("PcmDownsampler", () => {
    it("turns 48 kHz float audio into 40 ms frames of 16 kHz 16-bit samples", () => {
        const sampler = new PcmDownsampler(16000);
        const frames = sampler.push(new Float32Array(48000 * 0.08).fill(0.5), 48000);
        expect(frames).toHaveLength(2);
        expect(frames[0]).toHaveLength(640);
        expect(frames[0][0]).toBe(Math.round(0.5 * 0x7fff));
    });

    it("clips instead of wrapping", () => {
        const frames = new PcmDownsampler(16000, 1).push(new Float32Array(16).fill(2), 16000);
        expect(frames[0][0]).toBe(0x7fff);
    });
});

describe("decodePcm16", () => {
    it("decodes little-endian samples and keeps an odd trailing byte", () => {
        const { samples, rest } = decodePcm16(new Uint8Array([0x00, 0x40, 0x00, 0x80, 0x07]));
        expect(Array.from(samples)).toEqual([0.5, -1]);
        expect(rest).toBe(7);
    });
    it("measures level", () => {
        expect(rmsLevel(new Float32Array([0.5, -0.5]))).toBeCloseTo(0.5);
        expect(rmsLevel(new Float32Array())).toBe(0);
    });
});

describe("mapMediaError", () => {
    it("separates a denied microphone from a missing one", () => {
        expect(mapMediaError({ name: "NotAllowedError" }).code).toBe("permission_denied");
        expect(mapMediaError({ name: "NotFoundError" }).code).toBe("no_microphone");
        expect(mapMediaError(new Error("x")).code).toBe("failed");
    });
});

function mockBrowser(getUserMedia: () => Promise<unknown>) {
    const track = { stop: vi.fn(), enabled: true };
    const stream = { getTracks: () => [track], getAudioTracks: () => [track] };
    const close = vi.fn(() => Promise.resolve());
    class FakeContext {
        state = "running"; sampleRate = 48000; currentTime = 0; destination = {}; audioWorklet = undefined;
        resume = vi.fn(); close = close;
        createMediaStreamSource() { return { connect: vi.fn(), disconnect: vi.fn() }; }
        createGain() { return { gain: { value: 1 }, connect: vi.fn(), disconnect: vi.fn() }; }
        createScriptProcessor() { return { connect: vi.fn(), disconnect: vi.fn(), onaudioprocess: null }; }
    }
    vi.stubGlobal("AudioContext", FakeContext);
    Object.defineProperty(window, "AudioContext", { value: FakeContext, configurable: true });
    Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia: vi.fn(async () => { const result = await getUserMedia(); return result ?? stream; }) }, configurable: true });
    return { track, close };
}

describe("BrowserAudioPort", () => {
    afterEach(() => { vi.unstubAllGlobals(); });

    it("requests echo cancellation and releases tracks and the context on close", async () => {
        const { track, close } = mockBrowser(async () => undefined);
        const port = new BrowserAudioPort();
        await port.open();
        const constraints = (navigator.mediaDevices.getUserMedia as unknown as { mock: { calls: unknown[][] } }).mock.calls[0][0];
        expect(constraints).toMatchObject({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
        await port.beginCapture(16000, () => undefined, () => undefined);
        port.close();
        port.close();
        expect(track.stop).toHaveBeenCalledTimes(1);
        expect(close).toHaveBeenCalledTimes(1);
    });

    it("maps a denied permission", async () => {
        mockBrowser(async () => { throw Object.assign(new Error("denied"), { name: "NotAllowedError" }); });
        await expect(new BrowserAudioPort().open()).rejects.toMatchObject({ code: "permission_denied" });
    });

    it("maps a missing device", async () => {
        mockBrowser(async () => { throw Object.assign(new Error("none"), { name: "NotFoundError" }); });
        await expect(new BrowserAudioPort().open()).rejects.toBeInstanceOf(VoiceAudioError);
    });
});
