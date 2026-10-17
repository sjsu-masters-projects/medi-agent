import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import MessagesPage from "@/app/(dashboard)/messages/page";

vi.mock("@/hooks/use-clinic-filter", async () => (await import("@/test/clinic-filter-mock")).clinicFilterModule);
vi.mock("@/components/features/care-conversations", () => ({
  CareConversations: ({ conversationId }: { conversationId: string | null }) => <p>Human conversations {conversationId}</p>,
}));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams("conversation=exact-thread") }));
vi.mock("@/components/features/operational-alerts", () => ({
  EarlierMessages: () => <p>Earlier messages archive</p>,
}));

describe("Messages views", () => {
  it("shows conversations first, keeps earlier one-way messages below, and forwards the exact conversation", () => {
    render(<MessagesPage />);
    expect(screen.getByText("Human conversations exact-thread")).toBeInTheDocument();
    expect(screen.getByText("Earlier messages archive")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Operational alerts" })).not.toBeInTheDocument();
  });
});
