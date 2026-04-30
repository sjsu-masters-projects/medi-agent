import { normalizeLocale, type Locale } from "@/types";

export interface VoiceCapabilities {
    recording: boolean;
    recognition: boolean;
    synthesis: boolean;
}

export type VoiceStatus = "idle" | "listening" | "processing" | "playing" | "unsupported";

interface SpeechRecognitionAlternativeLike {
    transcript: string;
}

interface SpeechRecognitionResultLike {
    isFinal: boolean;
    0: SpeechRecognitionAlternativeLike;
}

interface SpeechRecognitionEventLike {
    resultIndex: number;
    results: ArrayLike<SpeechRecognitionResultLike>;
}

interface SpeechRecognitionErrorEventLike {
    error?: string;
}

interface BrowserSpeechRecognition {
    continuous: boolean;
    interimResults: boolean;
    lang: string;
    maxAlternatives: number;
    onend: (() => void) | null;
    onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
    onresult: ((event: SpeechRecognitionEventLike) => void) | null;
    onstart: (() => void) | null;
    abort: () => void;
    start: () => void;
    stop: () => void;
}

interface BrowserSpeechRecognitionConstructor {
    new (): BrowserSpeechRecognition;
}

declare global {
    interface Window {
        SpeechRecognition?: BrowserSpeechRecognitionConstructor;
        webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor;
    }
}

export interface SpeechRecognitionController {
    start: () => void;
    stop: () => void;
}

function getSpeechRecognitionConstructor():
    | BrowserSpeechRecognitionConstructor
    | null {
    if (typeof window === "undefined") {
        return null;
    }

    return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;
}

function getSpeechLocale(locale: Locale): string {
    return normalizeLocale(locale);
}

export function getVoiceCapabilities(): VoiceCapabilities {
    return {
        recording:
            typeof window !== "undefined"
            && typeof navigator !== "undefined"
            && Boolean(navigator.mediaDevices?.getUserMedia)
            && typeof window.MediaRecorder !== "undefined",
        recognition: getSpeechRecognitionConstructor() !== null,
        synthesis:
            typeof window !== "undefined"
            && typeof window.speechSynthesis !== "undefined",
    };
}

export function createSpeechRecognitionController(
    language: Locale,
    handlers: {
        onEnd: (finalTranscript: string) => void;
        onError: (message: string) => void;
        onStart: () => void;
        onTranscript: (state: {
            finalTranscript: string;
            interimTranscript: string;
        }) => void;
    },
): SpeechRecognitionController | null {
    const Recognition = getSpeechRecognitionConstructor();
    if (!Recognition) {
        return null;
    }

    const recognition = new Recognition();
    let finalTranscript = "";

    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = getSpeechLocale(language);
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
        handlers.onStart();
    };

    recognition.onresult = (event) => {
        let interimTranscript = "";

        for (let index = event.resultIndex; index < event.results.length; index += 1) {
            const result = event.results[index];
            const transcript = result[0]?.transcript ?? "";
            if (result.isFinal) {
                finalTranscript += transcript;
            } else {
                interimTranscript += transcript;
            }
        }

        handlers.onTranscript({
            finalTranscript: finalTranscript.trim(),
            interimTranscript: interimTranscript.trim(),
        });
    };

    recognition.onerror = (event) => {
        handlers.onError(event.error ?? "Voice transcription failed.");
    };

    recognition.onend = () => {
        handlers.onEnd(finalTranscript.trim());
    };

    return {
        start: () => {
            recognition.start();
        },
        stop: () => {
            recognition.stop();
        },
    };
}

export function playAssistantVoiceResponse({
    audioUrl,
    language,
    onEnd,
    onStart,
    text,
}: {
    audioUrl?: string;
    language: Locale;
    onEnd?: () => void;
    onStart?: () => void;
    text: string;
}): (() => void) | null {
    if (typeof window === "undefined") {
        return null;
    }

    if (audioUrl) {
        const audio = new Audio(audioUrl);
        audio.onended = () => {
            onEnd?.();
        };
        audio.onerror = () => {
            onEnd?.();
        };
        onStart?.();
        void audio.play().catch(() => {
            onEnd?.();
        });
        return () => {
            audio.pause();
            audio.currentTime = 0;
            onEnd?.();
        };
    }

    if (!window.speechSynthesis) {
        return null;
    }

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = getSpeechLocale(language);
    utterance.onend = () => {
        onEnd?.();
    };
    utterance.onerror = () => {
        onEnd?.();
    };

    window.speechSynthesis.cancel();
    onStart?.();
    window.speechSynthesis.speak(utterance);

    return () => {
        window.speechSynthesis.cancel();
        onEnd?.();
    };
}

export function stopAssistantVoicePlayback(): void {
    if (typeof window === "undefined") {
        return;
    }

    window.speechSynthesis?.cancel();
}
