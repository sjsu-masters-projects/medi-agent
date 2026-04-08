interface ChatBubbleProps {
    role: "user" | "assistant";
    content: string;
    timestamp: Date | string;
}

function formatTimestamp(timestamp: Date | string) {
    const value = timestamp instanceof Date ? timestamp : new Date(timestamp);
    return value.toLocaleTimeString("en-US", {
        hour: "numeric",
        minute: "2-digit",
    });
}

export function ChatBubble({ content, role, timestamp }: ChatBubbleProps) {
    const isUser = role === "user";

    return (
        <div className={`flex items-start gap-3 ${isUser ? "justify-end" : ""}`}>
            {!isUser ? (
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-800 text-xs font-semibold text-sky-200 shadow-sm">
                    AI
                </span>
            ) : null}
            <div className={`max-w-[80%] space-y-1 ${isUser ? "items-end text-right" : ""}`}>
                <div
                    className={`rounded-3xl px-4 py-3 text-sm leading-relaxed shadow-sm ${isUser ? "rounded-tr-sm bg-sky-700 text-white" : "rounded-tl-sm border border-slate-700 bg-slate-800 text-slate-100"}`}
                >
                    {content}
                </div>
                <p className="text-[10px] text-slate-500">{formatTimestamp(timestamp)}</p>
            </div>
        </div>
    );
}
