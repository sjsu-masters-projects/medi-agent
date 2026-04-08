"use client";

import { useEffect, useRef, useState } from "react";
import { ChatBubble } from "@/components/features";
import { Button, Input } from "@/components/ui";
import { ChatRole, type ChatMessage } from "@/types";

const welcomeMessage: ChatMessage = {
    content: "Hi Sarah. I can help explain results, track symptoms, and prepare questions for your doctor.",
    createdAt: new Date().toISOString(),
    id: "welcome-message",
    language: "en",
    patientId: "demo-patient",
    role: ChatRole.ASSISTANT,
};

export default function ChatPage() {
    const [input, setInput] = useState("");
    const [isTyping, setIsTyping] = useState(false);
    const [messages, setMessages] = useState<ChatMessage[]>([welcomeMessage]);
    const bottomRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [isTyping, messages]);

    function handleSend(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const content = input.trim();
        if (!content) {
            return;
        }

        const userMessage: ChatMessage = {
            content,
            createdAt: new Date().toISOString(),
            id: `${Date.now()}`,
            language: "en",
            patientId: "demo-patient",
            role: ChatRole.USER,
        };

        setMessages((current) => [...current, userMessage]);
        setInput("");
        setIsTyping(true);

        window.setTimeout(() => {
            setMessages((current) => [
                ...current,
                {
                    content: "I noted that for your care team. If symptoms worsen or new dizziness appears, report it immediately.",
                    createdAt: new Date().toISOString(),
                    id: `${Date.now()}-reply`,
                    language: "en",
                    patientId: "demo-patient",
                    role: ChatRole.ASSISTANT,
                },
            ]);
            setIsTyping(false);
        }, 700);
    }

    return (
        <div className="flex min-h-full flex-col bg-slate-950 text-white">
            <div className="border-b border-slate-800 bg-slate-950 px-5 pt-10 pb-4">
                <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-full border border-slate-700 bg-slate-900 text-sm text-sky-200">
                            ✦
                        </div>
                        <div>
                            <h1 className="text-2xl font-bold text-white">Care Companion</h1>
                            <p className="mt-1 inline-flex items-center gap-2 text-sm text-slate-300">
                                <span className="h-2 w-2 rounded-full bg-green-500" />
                                Online
                            </p>
                        </div>
                    </div>
                    <button
                        className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-200"
                        type="button"
                    >
                        EN / ES
                    </button>
                </div>
            </div>

            <div className="flex-1 space-y-4 px-5 py-5">
                <div className="mx-auto w-fit rounded-full bg-slate-800 px-3 py-1 text-[11px] text-slate-400">
                    Today, {new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}
                </div>

                <div className="space-y-4">
                    {messages.map((message) => (
                        <ChatBubble
                            content={message.content}
                            key={message.id}
                            role={message.role === ChatRole.USER ? "user" : "assistant"}
                            timestamp={message.createdAt}
                        />
                    ))}
                    {isTyping ? (
                        <div className="rounded-2xl border border-slate-700 bg-slate-800 px-4 py-3 text-sm text-slate-300">
                            Care Companion is typing...
                        </div>
                    ) : null}
                    <div className="rounded-2xl border border-sky-900 bg-sky-950/70 px-4 py-3 text-sm text-sky-100 shadow-sm">
                        Transferring context to Pharmacovigilance Agent via A2A
                    </div>
                    <div ref={bottomRef} />
                </div>
            </div>

            <form className="sticky bottom-0 space-y-3 border-t border-slate-800 bg-slate-950/95 px-5 py-4 backdrop-blur" onSubmit={handleSend}>
                <Button className="mx-auto block rounded-full px-5 py-2 text-sm font-semibold" variant="secondary">
                    Start Voice-to-Voice Mode
                </Button>
                <div className="flex items-center gap-3">
                    <button
                        className="flex h-12 w-12 items-center justify-center rounded-full border border-slate-700 bg-slate-900 text-slate-300"
                        type="button"
                    >
                        🎙
                    </button>
                    <div className="flex-1">
                        <Input
                            className="border-slate-700 bg-slate-900 text-white placeholder:text-slate-500 focus:border-sky-500 focus:ring-sky-500"
                            onChange={(event) => setInput(event.target.value)}
                            placeholder="Type or speak a message..."
                            value={input}
                        />
                    </div>
                    <button
                        className="flex h-12 w-12 items-center justify-center rounded-full bg-sky-700 text-white disabled:cursor-not-allowed disabled:opacity-50"
                        disabled={!input.trim()}
                        type="submit"
                    >
                        ↑
                    </button>
                </div>
            </form>
        </div>
    );
}
