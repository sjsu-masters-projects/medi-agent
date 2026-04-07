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
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-blue-100 text-sm text-blue-700">
                    AI
                </span>
            ) : null}
            <div className={`max-w-[80%] space-y-1 ${isUser ? "items-end text-right" : ""}`}>
                <div
                    className={`rounded-2xl px-4 py-3 text-sm leading-relaxed ${isUser ? "rounded-tr-sm bg-blue-600 text-white" : "rounded-tl-sm border border-gray-200 bg-gray-50 text-gray-800"}`}
                >
                    {content}
                </div>
                <p className="text-[10px] text-gray-400">{formatTimestamp(timestamp)}</p>
            </div>
        </div>
    );
}
