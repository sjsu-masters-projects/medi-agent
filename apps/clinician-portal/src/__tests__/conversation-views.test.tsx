import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import MessagesPage from "@/app/(dashboard)/messages/page";

vi.mock("@/components/features/care-conversations", () => ({
  CareConversations: ({ conversationId }: { conversationId: string | null }) => <p>Human conversations {conversationId}</p>,
}));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams("conversation=exact-thread") }));
vi.mock("@/components/features/operational-alerts", () => ({
  OperationalAlerts: () => <p>Separate operational history</p>,
}));

describe("Messages views", () => {
  it("keeps Messages human-only and forwards the exact conversation", () => {
    render(<MessagesPage />);
    expect(screen.getByText("Human conversations exact-thread")).toBeInTheDocument();
    expect(screen.queryByText("Separate operational history")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Operational alerts" })).not.toBeInTheDocument();
  });
});
