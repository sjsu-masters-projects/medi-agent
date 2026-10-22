"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { LiveVoiceController, type SocketLike, type UtteranceResult, type VoiceModeSnapshot } from "@/services/live-voice";
import { BrowserAudioPort, type AudioPort } from "@/services/pcm-audio";
import { buildVoiceWebSocketUrl } from "@/services/voice-api";
import { socketAuthProtocols } from "@/services/ws-auth";
import type { Locale as ChatLocale } from "@/types";

/** Voice mode ends when the tab has been hidden this long; a short switch away is fine. */
export const HIDDEN_END_MS = 60_000;
/** The remaining-time hint appears only this close to the session limit. */
export const REMAINING_HINT_SECONDS = 120;

export interface VoiceReply {
    seq: number;
    text: string;
    language: ChatLocale;
    urgent: boolean;
}

interface Options {
    patientId: string | null;
    accessToken: string | null;
    /** Voice mode belongs to one conversation: when this changes it ends. */
    scope: string;
    locale: ChatLocale;
    sendUtterance: (text: string, language: ChatLocale) => UtteranceResult;
    reply: VoiceReply | null;
    /** Set when a chat turn fails, so voice mode stops waiting for a reply. */
    chatError: string | null;
    /** Test seam. */
    createAudio?: () => AudioPort;
    createSocket?: (url: string, protocols: string[]) => SocketLike;
}

export function useVoiceMode(options: Options) {
    const [held, setHeld] = useState<{ snapshot: VoiceModeSnapshot | null; scope: string }>({ snapshot: null, scope: options.scope });
    const setSnapshot = useCallback((snapshot: VoiceModeSnapshot | null) => setHeld({ snapshot, scope: latest.current.scope }), []);
    // A snapshot from another conversation, or after sign-out, is not shown.
    const snapshot = options.accessToken && held.scope === options.scope ? held.snapshot : null;
    const [remainingSeconds, setRemainingSeconds] = useState<number | null>(null);
    const controllerRef = useRef<LiveVoiceController | null>(null);
    const ringRef = useRef<HTMLDivElement | null>(null);
    const latest = useRef<Options>({ ...options });
    useLayoutEffect(() => { Object.assign(latest.current, options); });
    const seenReply = useRef(options.reply?.seq ?? 0);

    const dispose = useCallback(() => {
        controllerRef.current?.dispose();
        controllerRef.current = null;
    }, []);

    const start = useCallback(() => {
        const { patientId, accessToken, locale } = latest.current;
        if (!patientId || !accessToken) return;
        dispose();
        const controller = new LiveVoiceController({
            language: locale,
            audio: (latest.current.createAudio ?? (() => new BrowserAudioPort()))(),
            createSocket: () => {
                const url = buildVoiceWebSocketUrl(patientId);
                const protocols = socketAuthProtocols(accessToken);
                return (latest.current.createSocket?.(url, protocols) ?? new WebSocket(url, protocols)) as SocketLike;
            },
            sendUtterance: (text, language) => latest.current.sendUtterance(text, language),
            onLevel: (level) => ringRef.current?.style.setProperty("--voice-level", String(Math.min(1, level * 4))),
            onChange: (next) => {
                if (controllerRef.current !== controller) return;
                // "ended" is the patient's own exit: the panel simply goes away.
                setSnapshot(next.state === "ended" ? null : next);
            },
        });
        controllerRef.current = controller;
        seenReply.current = latest.current.reply?.seq ?? 0;
        setSnapshot(controller.getSnapshot());
        void controller.start();
    }, [dispose, setSnapshot]);

    const end = useCallback(() => {
        const controller = controllerRef.current;
        controllerRef.current = null;
        setSnapshot(null);
        setRemainingSeconds(null);
        controller?.end();
    }, [setSnapshot]);

    const togglePause = useCallback(() => {
        const controller = controllerRef.current;
        if (controller) controller.setPaused(!controller.getSnapshot().paused);
    }, []);

    // Nora's reply is spoken once, when it arrives while voice mode is waiting for it.
    useEffect(() => {
        const reply = options.reply;
        if (!reply || reply.seq === seenReply.current) return;
        seenReply.current = reply.seq;
        controllerRef.current?.speakReply({ text: reply.text, language: reply.language, urgent: reply.urgent });
    }, [options.reply]);

    useEffect(() => {
        if (options.chatError) controllerRef.current?.noReply();
    }, [options.chatError]);

    // Sign-out and unmount: release the microphone and the sockets.
    useEffect(() => {
        if (!options.accessToken || held.scope !== options.scope) dispose();
    }, [options.accessToken, options.scope, held.scope, dispose]);
    useEffect(() => dispose, [dispose]);

    const active = snapshot !== null;
    useEffect(() => {
        if (!active) return;
        let timer: number | undefined;
        const onVisibility = () => {
            window.clearTimeout(timer);
            if (document.visibilityState === "hidden") timer = window.setTimeout(end, HIDDEN_END_MS);
        };
        document.addEventListener("visibilitychange", onVisibility);
        window.addEventListener("pagehide", dispose);
        return () => {
            window.clearTimeout(timer);
            document.removeEventListener("visibilitychange", onVisibility);
            window.removeEventListener("pagehide", dispose);
        };
    }, [active, end, dispose]);

    const startedAt = snapshot?.startedAt ?? null;
    const maxSeconds = snapshot?.maxSessionSeconds ?? null;
    useEffect(() => {
        if (startedAt === null || maxSeconds === null) return;
        const tick = () => {
            const left = Math.max(0, Math.ceil(maxSeconds - (Date.now() - startedAt) / 1000));
            setRemainingSeconds(left <= REMAINING_HINT_SECONDS ? left : null);
        };
        tick();
        const timer = window.setInterval(tick, 1000);
        return () => window.clearInterval(timer);
    }, [startedAt, maxSeconds]);

    return { active, snapshot, remainingSeconds, ringRef, start, end, togglePause };
}
