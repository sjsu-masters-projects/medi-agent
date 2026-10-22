import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MedicationQuestionCards } from "@/components/features/medication-question-cards";
import { describeMedicine } from "@/content/medication-confirmation-copy";
import { ApiClientError } from "@/services/api";

const { state, answer, refresh } = vi.hoisted(() => ({
  state: { items: [] as unknown[] },
  answer: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("react-redux", () => ({ useSelector: () => "token" }));
vi.mock("@/hooks/use-medication-questions", () => ({
  useMedicationQuestions: () => ({ items: state.items, loaded: true, refresh }),
}));
vi.mock("@/services/medication-confirmations", async (original) => ({
  ...(await original<object>()),
  answerMedicationQuestion: answer,
}));

const question = {
  id: "q1",
  medicationName: "Metformin",
  dosage: "500 mg",
  frequency: "twice daily",
  frequencyLabelEn: "Twice daily",
  frequencyLabelEs: "Dos veces al día",
  status: "open",
  answer: null,
  answerNote: null,
  expiresAt: "2026-11-05T10:00:00Z",
  clinicianName: "Elena Park",
  specialty: "Cardiology",
  clinicName: "Cedar Grove",
};

describe("MedicationQuestionCards", () => {
  beforeEach(() => {
    state.items = [question];
    answer.mockReset();
    refresh.mockReset();
  });
  afterEach(cleanup);

  it("renders nothing when there is nothing to ask", () => {
    state.items = [{ ...question, status: "answered" }];
    const { container } = render(<MedicationQuestionCards locale="en-US" />);
    expect(container).toBeEmptyDOMElement();
  });

  it.each([
    ["en-US", "Are you still taking Metformin 500 mg twice daily?", "No, I stopped", "Send answer"],
    ["es-MX", "¿Sigues tomando Metformin 500 mg dos veces al día?", "No, lo dejé", "Enviar respuesta"],
  ] as const)("asks a plain question in %s", (locale, text, stopped, send) => {
    render(<MedicationQuestionCards locale={locale} />);
    expect(screen.getByText(text)).toBeInTheDocument();
    expect(screen.getAllByRole("radio")).toHaveLength(4);
    expect(screen.getByLabelText(stopped)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: send })).toBeDisabled();
  });

  it("sends the chosen answer once and thanks the patient", async () => {
    answer.mockResolvedValue({ ...question, status: "answered", answer: "stopped" });
    render(<MedicationQuestionCards locale="en-US" />);
    fireEvent.click(screen.getByLabelText("No, I stopped"));
    fireEvent.click(screen.getByRole("button", { name: "Send answer" }));
    expect(await screen.findByText("Your care team will see your answer.")).toBeInTheDocument();
    expect(answer).toHaveBeenCalledWith("token", "q1", "stopped", undefined);
    expect(refresh).toHaveBeenCalled();
  });

  it("requires a description for It changed and sends it", async () => {
    answer.mockResolvedValue({ ...question, status: "answered" });
    render(<MedicationQuestionCards locale="en-US" />);
    fireEvent.click(screen.getByLabelText("It changed"));
    const send = screen.getByRole("button", { name: "Send answer" });
    expect(send).toBeDisabled();
    fireEvent.change(screen.getByLabelText("What changed?"), { target: { value: "250 mg now" } });
    expect(send).toBeEnabled();
    fireEvent.click(send);
    await waitFor(() => expect(answer).toHaveBeenCalledWith("token", "q1", "changed", "250 mg now"));
  });

  it("says plainly that the answer changes nothing", () => {
    render(<MedicationQuestionCards locale="en-US" />);
    expect(screen.getByText(/does not change your medicines or your reminders/)).toBeInTheDocument();
  });

  it("keeps the question and explains when sending fails", async () => {
    answer.mockRejectedValue(new ApiClientError("x", 409, { error: { code: "MEDCONFIRM_ALREADY_ANSWERED" } }));
    render(<MedicationQuestionCards locale="en-US" />);
    fireEvent.click(screen.getByLabelText("Yes"));
    fireEvent.click(screen.getByRole("button", { name: "Send answer" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already answered");
    expect(screen.getByRole("button", { name: "Send answer" })).toBeDisabled();
  });
});

describe("describeMedicine", () => {
  it("leaves an unrecognised cadence as written", () => {
    expect(
      describeMedicine({ ...question, frequency: "Every other Tuesday", frequencyLabelEn: null, frequencyLabelEs: null }, "es-MX"),
    ).toBe("Metformin 500 mg Every other Tuesday");
  });
});
