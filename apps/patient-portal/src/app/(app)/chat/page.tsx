"use client";

import { useState, useRef, useEffect } from "react";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

const WELCOME_MSG: Message = {
  id: "0",
  role: "assistant",
  content: "Hi Sarah! I'm your Care Companion. I can help you understand your medications, track symptoms, or answer health questions. How can I help you today?",
  timestamp: new Date(),
};

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([WELCOME_MSG]);
  const [input, setInput] = useState("");
  const [language, setLanguage] = useState<"EN" | "ES">("EN");
  const [isTyping, setIsTyping] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: text,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsTyping(true);

    // Simulate AI response (TODO: connect to WebSocket /ws/chat/{patient_id})
    setTimeout(() => {
      setIsTyping(false);
      const reply: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: "I understand. Let me look into that for you. Based on your current medications and health records, I have some information that might help.",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, reply]);
    }, 1500);
  }

  function formatTime(date: Date) {
    return date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
  }

  return (
    <div className="flex flex-col h-screen bg-white">
      {/* Header */}
      <div
        className="flex items-center justify-between px-5 pt-12 pb-4 border-b"
        style={{ borderColor: "#f1f5f9" }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-full flex items-center justify-center text-white text-lg"
            style={{ background: "var(--primary-light)" }}
          >
            🤖
          </div>
          <div>
            <p className="font-semibold text-sm" style={{ color: "var(--text-primary)" }}>Care Companion</p>
            <div className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-full" style={{ background: "var(--success)" }} />
              <span className="text-xs" style={{ color: "var(--success)" }}>Online</span>
            </div>
          </div>
        </div>

        {/* Language toggle */}
        <button
          onClick={() => setLanguage((l) => (l === "EN" ? "ES" : "EN"))}
          className="flex items-center gap-1 rounded-full px-3 py-1.5 text-xs font-medium border"
          style={{ borderColor: "#e2e8f0", color: "var(--text-secondary)" }}
        >
          {language} / {language === "EN" ? "ES" : "EN"} ▾
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-3">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex gap-2 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}
          >
            {msg.role === "assistant" && (
              <div
                className="w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center text-sm mt-1"
                style={{ background: "var(--primary-light)" }}
              >
                🤖
              </div>
            )}
            <div className={`flex flex-col gap-1 max-w-[75%] ${msg.role === "user" ? "items-end" : "items-start"}`}>
              <div
                className="rounded-2xl px-4 py-3 text-sm leading-relaxed"
                style={
                  msg.role === "user"
                    ? { background: "var(--primary)", color: "white", borderBottomRightRadius: "4px" }
                    : { background: "#f1f5f9", color: "var(--text-primary)", borderBottomLeftRadius: "4px" }
                }
              >
                {msg.content}
              </div>
              <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                {formatTime(msg.timestamp)}
              </span>
            </div>
          </div>
        ))}

        {isTyping && (
          <div className="flex gap-2 items-center">
            <div
              className="w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center text-sm"
              style={{ background: "var(--primary-light)" }}
            >
              🤖
            </div>
            <div className="rounded-2xl px-4 py-3 flex gap-1" style={{ background: "#f1f5f9", borderBottomLeftRadius: "4px" }}>
              <span className="w-2 h-2 rounded-full animate-bounce" style={{ background: "var(--text-muted)", animationDelay: "0ms" }} />
              <span className="w-2 h-2 rounded-full animate-bounce" style={{ background: "var(--text-muted)", animationDelay: "150ms" }} />
              <span className="w-2 h-2 rounded-full animate-bounce" style={{ background: "var(--text-muted)", animationDelay: "300ms" }} />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Voice button */}
      <div className="px-4 pb-2 flex justify-end">
        <button
          className="flex items-center gap-2 rounded-full px-4 py-2 text-xs font-semibold text-white"
          style={{ background: "#0f172a" }}
        >
          🎧 Start Voice
        </button>
      </div>

      {/* Input bar */}
      <form
        onSubmit={handleSend}
        className="px-4 pb-24 flex items-center gap-2"
      >
        <button
          type="button"
          className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0"
          style={{ background: "#f1f5f9", color: "var(--text-muted)" }}
        >
          📎
        </button>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type or speak..."
          className="flex-1 rounded-full px-4 py-2.5 text-sm outline-none"
          style={{ background: "#f1f5f9", color: "var(--text-primary)" }}
        />
        <button
          type="submit"
          disabled={!input.trim()}
          className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 text-white disabled:opacity-40"
          style={{ background: "var(--primary)" }}
        >
          ↑
        </button>
      </form>
    </div>
  );
}
