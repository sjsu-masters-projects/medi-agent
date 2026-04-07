"use client";

import { useEffect, useRef, useState } from "react";
import { ChatBubble } from "@/components/features";
import { PageHeader } from "@/components/layouts";
import { Button, Card, Input } from "@/components/ui";
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
        <div className="flex min-h-full flex-col bg-gray-50">
            <PageHeader subtitle="Secure messaging with your AI care companion." title="Care Companion" />
            <div className="flex-1 space-y-4 px-5 pb-4">
                <Card className="flex items-center justify-between">
                    <div>
                        <p className="text-sm font-semibold text-gray-900">Companion status</p>
                        <p className="text-sm text-gray-500">Ready to help with medications, symptoms, and follow-up questions.</p>
                    </div>
                    <span className="inline-flex items-center gap-2 rounded-full bg-green-100 px-3 py-1 text-xs font-medium text-green-800">
                        <span className="h-2 w-2 rounded-full bg-green-500" />
                        Online
                    </span>
                </Card>

                <div className="space-y-4 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                    {messages.map((message) => (
                        <ChatBubble
                            content={message.content}
                            key={message.id}
                            role={message.role === ChatRole.USER ? "user" : "assistant"}
                            timestamp={message.createdAt}
                        />
                    ))}
                    {isTyping ? (
                        <div className="rounded-2xl rounded-tl-sm border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-500">
                            Care Companion is typing...
                        </div>
                    ) : null}
                    <div ref={bottomRef} />
                </div>
            </div>

            <form className="sticky bottom-0 space-y-3 border-t border-gray-200 bg-white px-5 py-4" onSubmit={handleSend}>
                <Input
                    onChange={(event) => setInput(event.target.value)}
                    placeholder="Type your question..."
                    value={input}
                />
                <div className="flex items-center justify-between gap-3">
                    <Button variant="secondary">Start voice</Button>
                    <Button disabled={!input.trim()} type="submit">
                        Send
                    </Button>
                </div>
            </form>
        </div>
    );
}
