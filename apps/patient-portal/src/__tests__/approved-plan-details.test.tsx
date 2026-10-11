import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApprovedPlanDetails } from "@/components/features/approved-plan-details";
import { api } from "@/services/api";
vi.mock("react-redux", () => ({ useSelector: (select: (state: unknown) => unknown) => select({ auth: { user: { id: "synthetic-patient" }, accessToken: "synthetic-token" } }) }));
vi.mock("@/services/api", () => ({ api: { get: vi.fn() } }));
const plan = { id: "plan", status: "approved", approved_at: "2026-10-10T12:00:00Z", version_number: 3, items: [
  { id: "item", title: "Reviewed source title", instructions: "Reviewed source instructions", frequency: "Daily", is_removed: false, source_locale: "en-US", wording_verified: true, wording: { "es-MX": { title: "Título revisado", instructions: "Instrucciones aprobadas", frequency: "Diario" } } },
  { id: "removed", title: "Removed instruction", is_removed: true },
] };
beforeEach(() => { vi.resetAllMocks(); vi.mocked(api.get).mockResolvedValue(plan); });
afterEach(cleanup);
describe("approved plan notification destination", () => {
  it("loads only the authenticated patient's approved plan and saved-language reviewed wording", async () => {
    render(<ApprovedPlanDetails locale="es-MX" />);
    await screen.findByText("Instrucciones aprobadas");
    expect(api.get).toHaveBeenCalledWith("/api/v1/care-plans/patients/synthetic-patient", { token: "synthetic-token", signal: expect.any(AbortSignal) });
    expect(screen.queryByText("Removed instruction")).not.toBeInTheDocument();
    expect(screen.queryByText("Reviewed source instructions")).not.toBeInTheDocument();
  });
  it("rejects a draft instead of claiming approval", async () => {
    vi.mocked(api.get).mockResolvedValue({ ...plan, status: "draft" });
    render(<ApprovedPlanDetails locale="en-US" />);
    await screen.findByRole("alert");
    expect(screen.queryByText("Reviewed source title")).not.toBeInTheDocument();
  });
  it("does not imply an empty plan when the authorized read fails", async () => {
    vi.mocked(api.get).mockRejectedValue(new TypeError());
    render(<ApprovedPlanDetails locale="en-US" />);
    await screen.findByRole("alert");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.queryByText("No approved plan is available.")).not.toBeInTheDocument();
  });
});
