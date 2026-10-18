import { fireEvent, render, screen } from "@testing-library/react";
import { Provider } from "react-redux";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NoraConversations } from "@/components/features/nora-conversations";
import { store } from "@/store/store";
import { hydrateSession } from "@/store/slices/auth-slice";

const { fetchChatConversations } = vi.hoisted(() => ({ fetchChatConversations: vi.fn() }));
vi.mock("@/services/chat-api", async (importOriginal) => ({
    ...(await importOriginal<typeof import("@/services/chat-api")>()),
    fetchChatConversations,
}));

const rows = [
    { sessionId: "day-2026-10-01", title: "Explain my recent results", updatedAt: "2026-10-01T15:00:00Z", needsAttention: true, replyInProgress: false },
    { sessionId: "day-2026-09-30", title: "Metformin", updatedAt: "2026-09-30T15:00:00Z", needsAttention: true, replyInProgress: true },
    { sessionId: "day-2026-09-29", title: "Finished", updatedAt: "2026-09-29T15:00:00Z", needsAttention: false, replyInProgress: false },
];

describe("NoraConversations unfinished replies", () => {
    beforeEach(() => {
        store.dispatch(hydrateSession({
            accessToken: "t", expiresAt: 9999999999, refreshToken: "r",
            user: { email: "p@example.com", id: "patient-1", role: "patient" },
        }));
        fetchChatConversations.mockResolvedValue(rows);
    });

    it.each([
        ["en-US", "Reply unfinished", "Nora is replying…"],
        ["es-MX", "Respuesta incompleta", "Nora está respondiendo…"],
    ])("shows the chip in %s and opens the conversation", async (locale, unfinished, replying) => {
        const onOpen = vi.fn();
        render(<Provider store={store}><NoraConversations locale={locale} activeSessionId="x" onOpen={onOpen} /></Provider>);
        const first = await screen.findByRole("button", { name: new RegExp(`Explain my recent results.*${unfinished}`) });
        expect(screen.getAllByText(unfinished)).toHaveLength(1);
        expect(screen.getAllByText(replying)).toHaveLength(1);
        fireEvent.click(first);
        expect(onOpen).toHaveBeenCalledWith("day-2026-10-01");
    });
});
