"use client";

import { useEffect, useRef, useState } from "react";
import { HiArrowUp, HiMicrophone, HiSparkles } from "react-icons/hi2";
import { useDispatch, useSelector } from "react-redux";
import { ChatBubble } from "@/components/features";
import { Button, Input } from "@/components/ui";
import {
    buildChatWebSocketUrl,
    fetchChatHistory,
    isChatSocketEvent,
    mapChatMessageFromApi,
} from "@/services/chat-api";
import {
    addMessage,
    clearChatState,
    setChatError,
    setConnectionStatus,
    setLoading,
    setMessages,
    setTyping,
} from "@/store/slices/chat-slice";
import type { AppDispatch, RootState } from "@/store/store";
import { ChatRole, type ChatMessage } from "@/types";

function buildWelcomeMessage(patientId: string): ChatMessage {
    return {
        content: "Hi. I can help explain results, track symptoms, and prepare questions for your doctor.",
        createdAt: new Date().toISOString(),
        id: "welcome-message",
        language: "en",
        patientId,
        role: ChatRole.ASSISTANT,
    };
}

function getConnectionLabel(status: RootState["chat"]["connectionStatus"]): string {
    if (status === "connected") {
        return "Online";
    }
    if (status === "connecting") {
        return "Connecting";
    }
    if (status === "error") {
        return "Connection issue";
    }
    return "Offline";
}

export default function ChatPage() {
    const dispatch = useDispatch<AppDispatch>();
    const { accessToken, user } = useSelector((state: RootState) => state.auth);
    const { connectionStatus, error, isTyping, loading, messages } = useSelector(
        (state: RootState) => state.chat,
    );

    const [input, setInput] = useState("");
    const bottomRef = useRef<HTMLDivElement | null>(null);
    const socketRef = useRef<WebSocket | null>(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [isTyping, messages]);

    useEffect(() => {
        if (!accessToken || !user) {
            return;
        }

        let isMounted = true;
        dispatch(clearChatState());
        dispatch(setLoading(true));

        fetchChatHistory(user.id, accessToken)
            .then((history) => {
                if (!isMounted) {
                    return;
                }
                dispatch(
                    setMessages(
                        history.length > 0 ? history : [buildWelcomeMessage(user.id)],
                    ),
                );
            })
            .catch(() => {
                if (!isMounted) {
                    return;
                }
                dispatch(setMessages([buildWelcomeMessage(user.id)]));
                dispatch(setChatError("Unable to load chat history. Live chat is still available."));
            })
            .finally(() => {
                if (isMounted) {
                    dispatch(setLoading(false));
                }
            });

        dispatch(setConnectionStatus("connecting"));
        dispatch(setChatError(null));

        const socket = new WebSocket(buildChatWebSocketUrl(user.id, accessToken));
        socketRef.current = socket;

        socket.onopen = () => {
            if (!isMounted) {
                return;
            }
            dispatch(setConnectionStatus("connected"));
            dispatch(setChatError(null));
        };

        socket.onmessage = (event) => {
            let payload: unknown;

            try {
                payload = JSON.parse(event.data as string);
            } catch {
                return;
            }

            if (!isChatSocketEvent(payload)) {
                return;
            }

            switch (payload.type) {
                case "chat_history": {
                    const incomingHistory = payload.messages.map(mapChatMessageFromApi);
                    dispatch(
                        setMessages(
                            incomingHistory.length > 0
                                ? incomingHistory
                                : [buildWelcomeMessage(user.id)],
                        ),
                    );
                    return;
                }
                case "user_message_saved":
                    dispatch(addMessage(mapChatMessageFromApi(payload.message)));
                    return;
                case "assistant_start":
                case "assistant_chunk":
                    dispatch(setTyping(true));
                    return;
                case "assistant_complete":
                    dispatch(setTyping(false));
                    dispatch(addMessage(mapChatMessageFromApi(payload.message)));
                    if (payload.escalation_required) {
                        dispatch(
                            setChatError(
                                "Urgent symptoms detected. Contact your care team today.",
                            ),
                        );
                    }
                    return;
                case "escalation_recommended":
                    dispatch(setChatError(payload.message));
                    return;
                case "error":
                    dispatch(setTyping(false));
                    dispatch(setChatError(payload.message || "Chat request failed."));
                    return;
                default:
                    return;
            }
        };

        socket.onerror = () => {
            if (!isMounted) {
                return;
            }
            dispatch(setConnectionStatus("error"));
            dispatch(setTyping(false));
            dispatch(setChatError("Live chat connection encountered an issue."));
        };

        socket.onclose = () => {
            if (!isMounted) {
                return;
            }
            dispatch(setConnectionStatus("disconnected"));
            dispatch(setTyping(false));
        };

        return () => {
            isMounted = false;
            socketRef.current = null;
            socket.close();
        };
    }, [accessToken, dispatch, user]);

    function handleSend(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const content = input.trim();
        if (!content) {
            return;
        }

        if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
            dispatch(setChatError("Chat is reconnecting. Try sending in a moment."));
            return;
        }

        socketRef.current.send(
            JSON.stringify({
                type: "user_message",
                content,
                language: "en",
            }),
        );
        dispatch(setChatError(null));
        setInput("");
    }

    return (
        <div className="flex min-h-full flex-col bg-slate-950 text-white">
            <div className="border-b border-slate-800 bg-slate-950 px-5 pt-10 pb-4">
                <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-full border border-slate-700 bg-slate-900 text-sm text-sky-200">
                            <HiSparkles className="h-5 w-5" />
                        </div>
                        <div>
                            <h1 className="text-2xl font-bold text-white">Care Companion</h1>
                            <p className="mt-1 inline-flex items-center gap-2 text-sm text-slate-300">
                                <span
                                    className={`h-2 w-2 rounded-full ${
                                        connectionStatus === "connected"
                                            ? "bg-green-500"
                                            : connectionStatus === "connecting"
                                              ? "bg-amber-400"
                                              : "bg-rose-500"
                                    }`}
                                />
                                {getConnectionLabel(connectionStatus)}
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

                {error ? (
                    <div className="rounded-2xl border border-rose-800 bg-rose-950/40 px-4 py-3 text-sm text-rose-200">
                        {error}
                    </div>
                ) : null}

                <div className="space-y-4">
                    {loading && messages.length === 0 ? (
                        <div className="rounded-2xl border border-slate-700 bg-slate-900 px-4 py-3 text-sm text-slate-300">
                            Loading conversation...
                        </div>
                    ) : null}

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
                        <HiMicrophone className="h-5 w-5" />
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
                        <HiArrowUp className="h-5 w-5" />
                    </button>
                </div>
            </form>
        </div>
    );
}
