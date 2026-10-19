import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ConversationActivityReview } from "@/components/features/conversation-activity";
import { careConversations } from "@/services/care-conversations";

const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/services/care-conversations", () => ({ careConversations: { reviewActivity: vi.fn() } }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });
const activity = { item_id: "source", plan_id: "approved", title: "Source title", frequency: "daily", current: true };
const props = { token: "synthetic", conversationId: "private", messageId: "message", patientId: "patient" };

function apiFailure(code: string, status = 422) {
  return { status, details: { error: { code, message: "safe server copy" } } };
}

it("does nothing until an explicit review click and opens the returned exact draft item", async () => {
  vi.mocked(careConversations.reviewActivity).mockResolvedValue({ patient_id: "patient", plan_id: "draft", item_id: "target" });
  render(<ConversationActivityReview activity={activity} {...props} />);
  expect(careConversations.reviewActivity).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Review activity in draft" }));
  await waitFor(() => expect(push).toHaveBeenCalledWith("/patients/patient?tab=care-plan#care-plan-item-target"));
  expect(careConversations.reviewActivity).toHaveBeenCalledExactlyOnceWith("synthetic", "private", "message");
});

it("disables review for a superseded activity", () => {
  render(<ConversationActivityReview activity={{ ...activity, current: false }} {...props} />);
  expect(screen.getByRole("button", { name: "Review activity in draft" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Open current care plan" }));
  expect(push).toHaveBeenCalledWith("/patients/patient?tab=care-plan");
  expect(careConversations.reviewActivity).not.toHaveBeenCalled();
});

it("keeps the message and approval boundary visible on failure", async () => {
  vi.mocked(careConversations.reviewActivity).mockRejectedValue(new Error("private database detail"));
  render(<ConversationActivityReview activity={activity} {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Review activity in draft" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not open");
  expect(screen.getByText(/A reply does not change/)).toBeVisible();
  expect(push).not.toHaveBeenCalled();
  expect(screen.queryByText(/private database detail/)).not.toBeInTheDocument();
});

it("announces that the draft is opening", async () => {
  let finish!: (value: { patient_id: string; plan_id: string; item_id: string }) => void;
  vi.mocked(careConversations.reviewActivity).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  render(<ConversationActivityReview activity={activity} {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Review activity in draft" }));
  expect(screen.getByRole("status")).toHaveTextContent("Opening the care-plan draft");
  finish({ patient_id: "patient", plan_id: "draft", item_id: "target" });
  await waitFor(() => expect(push).toHaveBeenCalled());
});

it.each([
  ["ACTIVITY_CONTEXT_STALE", "This activity is no longer", "Open current care plan"],
  ["CARE_PLAN_DRAFT_EXISTS", "already needs review", "Open current draft"],
] as const)("shows an actionable %s result", async (code, message, action) => {
  vi.mocked(careConversations.reviewActivity).mockRejectedValue(apiFailure(code));
  render(<ConversationActivityReview activity={activity} {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Review activity in draft" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(message);
  fireEvent.click(screen.getByRole("button", { name: action }));
  expect(push).toHaveBeenCalledWith("/patients/patient?tab=care-plan");
});

it("distinguishes revoked assignment without exposing the server detail", async () => {
  vi.mocked(careConversations.reviewActivity).mockRejectedValue(apiFailure("AUTHORIZATION_ERROR", 403));
  render(<ConversationActivityReview activity={activity} {...props} />);
  fireEvent.click(screen.getByRole("button", { name: "Review activity in draft" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("no longer have access");
  expect(screen.queryByText("safe server copy")).not.toBeInTheDocument();
});
