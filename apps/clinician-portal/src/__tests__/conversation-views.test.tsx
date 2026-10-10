import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import MessagesPage from "@/app/(dashboard)/messages/page";

vi.mock("@/components/features/care-conversations", () => ({
  CareConversations: ({ visible }: { visible: boolean }) => <p>Human conversations {visible ? "active" : "paused"}</p>,
}));
vi.mock("@/components/features/operational-alerts", () => ({
  OperationalAlerts: () => <p>Separate operational history</p>,
}));

describe("Messages views", () => {
  it("opens the conversation inbox by default and pauses it in operational alerts", () => {
    render(<MessagesPage />);
    expect(screen.getByText("Human conversations active")).toBeInTheDocument();
    expect(screen.queryByText("Separate operational history")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Operational alerts" }));
    expect(screen.getByText("Separate operational history")).toBeInTheDocument();
    expect(screen.getByText("Human conversations paused")).not.toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Conversations" }));
    expect(screen.getByText("Human conversations active")).toBeVisible();
  });
});
