import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ConversationActivityContext, ConversationActivityPicker } from "@/components/features/conversation-activity";
import { api } from "@/services/api";
import { conversationSendFailure, getConversationCopy } from "../../../../packages/shared/src/utils/care-conversations";

vi.mock("@/services/api", () => ({ api: { get: vi.fn() } }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });

it("maps a stale attachment to localized editable recovery rather than uncertain retry", () => {
  const failure = conversationSendFailure({ status: 422, details: { error: { code: "ACTIVITY_CONTEXT_UNAVAILABLE" } } });
  expect(failure).toBe("activityUnavailable");
  expect(getConversationCopy("es-MX")[failure]).toContain("Quita la actividad");
});

it("attaches only an explicitly selected non-removed approved activity in Spanish", async () => {
  vi.mocked(api.get).mockResolvedValue({ items: [
    { id: "activity", title: "Hydration", frequency: "daily", wording: { "es-MX": { title: "Hidratación", frequency: "diaria" } } },
    { id: "removed", title: "Removed", is_removed: true },
  ] });
  const change = vi.fn();
  render(<ConversationActivityPicker token="synthetic" patientId="patient" locale="es-MX" disabled={false} onChange={change} />);
  await screen.findByRole("option", { name: "Hidratación" });
  expect(screen.queryByRole("option", { name: "Removed" })).not.toBeInTheDocument();
  expect(change).not.toHaveBeenCalled();
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "activity" } });
  expect(change).toHaveBeenCalledWith("activity");
});

it("keeps an attachment locked during an uncertain send", async () => {
  vi.mocked(api.get).mockResolvedValue(null);
  render(<ConversationActivityPicker token="synthetic" patientId="patient" locale="en-US" value="saved" disabled onChange={vi.fn()} />);
  await screen.findByRole("option", { name: "No activity attached" });
  expect(screen.getByRole("combobox")).toBeDisabled();
  expect(screen.getByText(/Your message does not change the plan/)).toBeVisible();
});

it("offers localized recovery instead of backend prose", async () => {
  vi.mocked(api.get).mockRejectedValueOnce(new Error("SQL private data"));
  render(<ConversationActivityPicker token="synthetic" patientId="patient" locale="es-MX" disabled={false} onChange={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("No se pudieron cargar");
  expect(screen.queryByText(/SQL/)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Reintentar actividades" })).toBeEnabled();
});

it("marks historical context without translating or changing clinical wording", () => {
  render(<ConversationActivityContext activity={{ item_id: "item", plan_id: "plan", title: "Approved text", frequency: "daily", current: false }} locale="es-MX" />);
  expect(screen.getByText("Approved text")).toBeVisible();
  expect(screen.getByText(/ya no pertenece/)).toBeVisible();
});
