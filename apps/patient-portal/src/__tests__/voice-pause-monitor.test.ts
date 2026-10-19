import { afterEach, describe, expect, it, vi } from "vitest";
import { watchSpeechPause } from "@/services/voice-pause-monitor";

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("private spoken answer pause detection", () => {
    function audio(energy = 0) {
        let level = energy;
        const disconnect = vi.fn();
        const close = vi.fn().mockResolvedValue(undefined);
        class Context {
            createMediaStreamSource() { return { connect: vi.fn(), disconnect }; }
            createAnalyser() { return { fftSize: 1024, disconnect, getFloatTimeDomainData: (data: Float32Array) => data.fill(level) }; }
            resume = vi.fn().mockResolvedValue(undefined);
            close = close;
        }
        vi.stubGlobal("AudioContext", Context);
        return { close, disconnect, level: (value: number) => { level = value; } };
    }

    it("ends once after speech and a pause and releases local audio analysis", async () => {
        vi.useFakeTimers();
        const local = audio(0.1);
        const ended = vi.fn();
        const stop = watchSpeechPause({} as MediaStream, ended);
        await vi.advanceTimersByTimeAsync(500);
        expect(ended).not.toHaveBeenCalled();
        local.level(0);
        await vi.advanceTimersByTimeAsync(1900);
        expect(ended).toHaveBeenCalledTimes(1);
        expect(local.close).toHaveBeenCalledOnce();
        stop();
        await vi.advanceTimersByTimeAsync(10000);
        expect(ended).toHaveBeenCalledTimes(1);
    });

    it("bounds initial silence", async () => {
        vi.useFakeTimers();
        const local = audio();
        const ended = vi.fn();
        watchSpeechPause({} as MediaStream, ended);
        await vi.advanceTimersByTimeAsync(15000);
        expect(ended).toHaveBeenCalledOnce();
        expect(local.close).toHaveBeenCalledOnce();
    });

    it("manual cleanup cannot trigger an answer", async () => {
        vi.useFakeTimers();
        audio(0.1);
        const ended = vi.fn();
        const stop = watchSpeechPause({} as MediaStream, ended);
        stop();
        await vi.advanceTimersByTimeAsync(60000);
        expect(ended).not.toHaveBeenCalled();
    });
});
