import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ConversationActivityReview } from "@/components/features/conversation-activity";
import { careConversations } from "@/services/care-conversations";

const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/services/care-conversations", () => ({ careConversations: { reviewActivity: vi.fn() } }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });
const activity = { item_id: "source", plan_id: "approved", title: "Source title", frequency: "daily", current: true };

it("does nothing until an explicit review click and opens the returned exact draft item", async () => {
  vi.mocked(careConversations.reviewActivity).mockResolvedValue({ patient_id: "patient", plan_id: "draft", item_id: "target" });
  render(<ConversationActivityReview activity={activity} token="synthetic" conversationId="private" messageId="message" />);
  expect(careConversations.reviewActivity).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Review activity in draft" }));
  await waitFor(() => expect(push).toHaveBeenCalledWith("/patients/patient?tab=care-plan#care-plan-item-target"));
  expect(careConversations.reviewActivity).toHaveBeenCalledExactlyOnceWith("synthetic", "private", "message");
});

it("disables review for a superseded activity", () => {
  render(<ConversationActivityReview activity={{ ...activity, current: false }} token="synthetic" conversationId="private" messageId="message" />);
  expect(screen.getByRole("button", { name: "Review activity in draft" })).toBeDisabled();
  expect(careConversations.reviewActivity).not.toHaveBeenCalled();
});

it("keeps the message and approval boundary visible on failure", async () => {
  vi.mocked(careConversations.reviewActivity).mockRejectedValue(new Error("private database detail"));
  render(<ConversationActivityReview activity={activity} token="synthetic" conversationId="private" messageId="message" />);
  fireEvent.click(screen.getByRole("button", { name: "Review activity in draft" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not open");
  expect(screen.getByText(/A reply does not change/)).toBeVisible();
  expect(push).not.toHaveBeenCalled();
  expect(screen.queryByText(/private database detail/)).not.toBeInTheDocument();
});
