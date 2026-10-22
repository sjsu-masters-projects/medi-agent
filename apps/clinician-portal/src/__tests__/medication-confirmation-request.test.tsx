import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("@/services/api", () => ({ api: { get, post } }));

import { MedicationConfirmationRequest } from "@/components/features/medication-confirmation-request";

const base = {
  id: "r1",
  fact_id: "f1",
  care_team_id: "t1",
  subject_kind: "imported",
  medication_name: "Metformin",
  dosage: "500 mg",
  frequency: "twice daily",
  created_at: "2026-10-22T10:00:00Z",
  expires_at: "2026-11-05T10:00:00Z",
  answered_at: null,
  answer: null,
  answer_note: null,
};
const props = {
  patientId: "p1",
  factId: "f1",
  token: "t",
  candidate: { name: "Metformin", dosage: "500 mg", frequency: "twice daily" },
  matches: [{ target_id: "m1", match_reason: "Same name", record: { name: "Metformin ER", dosage: "1000 mg", frequency: "once daily" } }],
};

describe("MedicationConfirmationRequest", () => {
  beforeEach(() => { get.mockReset(); post.mockReset(); });
  afterEach(cleanup);

  it("asks about the imported record with one retry-safe key", async () => {
    get.mockResolvedValue([]);
    post.mockRejectedValueOnce(new Error("offline")).mockResolvedValue({ ...base, status: "open" });
    render(<MedicationConfirmationRequest {...props} />);
    const ask = await screen.findByRole("button", { name: "Ask the patient to confirm" });
    fireEvent.click(ask);
    await screen.findByText("offline");
    fireEvent.click(ask);
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    const [, first] = post.mock.calls[0];
    const [, second] = post.mock.calls[1];
    expect(first.subject).toBe("imported");
    expect(second.client_request_id).toBe(first.client_request_id);
  });

  it("can ask about a matched approved medication", async () => {
    get.mockResolvedValue([]);
    post.mockResolvedValue({ ...base, status: "open" });
    render(<MedicationConfirmationRequest {...props} />);
    fireEvent.click(await screen.findByLabelText(/On the approved list/));
    fireEvent.click(screen.getByRole("button", { name: "Ask the patient to confirm" }));
    await waitFor(() => expect(post).toHaveBeenCalled());
    expect(post.mock.calls[0][1]).toMatchObject({ subject: "approved", medication_id: "m1" });
  });

  it("shows a waiting state instead of a second ask while one is open", async () => {
    get.mockResolvedValue([{ ...base, status: "open" }]);
    render(<MedicationConfirmationRequest {...props} />);
    expect(await screen.findByText(/Waiting for the patient/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask the patient to confirm" })).not.toBeInTheDocument();
  });

  it("shows the answer as unverified patient testimony, never as an applied change", async () => {
    get.mockResolvedValue([{ ...base, status: "answered", answer: "changed", answer_note: "Now 250 mg", answered_at: "2026-10-23T10:00:00Z" }]);
    render(<MedicationConfirmationRequest {...props} />);
    const card = await screen.findByTestId("patient-answer");
    expect(card).toHaveTextContent("It changed");
    expect(card).toHaveTextContent("Now 250 mg");
    expect(card).toHaveTextContent("Not verified and not applied to the chart");
    expect(post).not.toHaveBeenCalled();
  });

  it("tolerates a failed load", async () => {
    get.mockRejectedValue(new Error("x"));
    render(<MedicationConfirmationRequest {...props} />);
    expect(await screen.findByText(/could not be loaded/)).toBeInTheDocument();
  });
});
