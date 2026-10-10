import { describe, expect, it, vi } from "vitest";
import { careConversations } from "@/services/care-conversations";
import { api } from "@/services/api";
import { mergeConversationMessages } from "../../../../packages/shared/src/utils/care-conversations";
vi.mock("@/services/api", () => ({ api: { get: vi.fn().mockResolvedValue([]), post: vi.fn().mockResolvedValue({}) } }));
describe("conversation API contract", () => {
  it("merges pages using timestamp precision before UUID ordering, including fractional seconds", () => {
    const row = { conversation_id: "thread", sender_id: "sender", sender_role: "clinician", sender_name: "Synthetic sender", body: "Synthetic message" };
    const result = mergeConversationMessages(
      [{ ...row, id: "z", created_at: "2026-10-09T10:00:00Z" }, { ...row, id: "y", created_at: "2026-10-09T10:00:00.123456Z" }],
      [{ ...row, id: "b", created_at: "2026-10-09T10:00:00.000001Z" }, { ...row, id: "a", created_at: "2026-10-09T10:00:00.123457Z" }],
    );
    expect(result.map((message) => message.id)).toEqual(["z", "b", "y", "a"]);
  });
  it("uses authenticated routes, bounded cursor pages and exact write payloads without sender controls", async () => {
    await careConversations.recipients("token");
    await careConversations.list("token");
    await careConversations.open("token", "recipient");
    await careConversations.messages("token", "thread", "cursor");
    await careConversations.send("token", "thread", "  hello  ", "stable-uuid");
    await careConversations.read("token", "thread", "displayed-last-id");
    expect(api.get).toHaveBeenCalledWith("/api/v1/care-conversations/recipients", { token: "token", signal: undefined });
    expect(api.get).toHaveBeenCalledWith("/api/v1/care-conversations/", { token: "token", signal: undefined });
    expect(api.get).toHaveBeenCalledWith("/api/v1/care-conversations/thread/messages?limit=50&before=cursor", { token: "token", signal: undefined });
    expect(api.post).toHaveBeenCalledWith("/api/v1/care-conversations/", { recipient_id: "recipient" }, { token: "token" });
    expect(api.post).toHaveBeenCalledWith("/api/v1/care-conversations/thread/messages", { body: "hello", client_message_id: "stable-uuid" }, { token: "token" });
    expect(api.post).toHaveBeenCalledWith("/api/v1/care-conversations/thread/read", { last_message_id: "displayed-last-id" }, { token: "token" });
  });
});
