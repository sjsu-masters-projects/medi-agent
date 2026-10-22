import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("react-redux", () => ({ useSelector: () => "local-clinician-token" }));
vi.mock("@/services/api", () => ({ api: { get, post } }));
import { SmartImportReviewPanel } from "@/components/features/smart-import-review-panel";

const fact = { id: "fact-1", fact_type: "medication", subject_type: "medication", value: { name: "Metformin" }, uncertainty: [], review_state: "pending_review", created_at: "2026-10-21T00:00:00Z" };
const review = { patient_id: "patient-1", review_state: "pending_review", facts: [fact], total_count: 1, state_counts: { pending_review: 1, approved: 0, rejected: 0 }, fact_type_counts: { medication: 1 }, offset: 0, limit: 25 };
const preview = { fact_id: "fact-1", fact_type: "medication", projectable: true, candidate_fields: { name: "Metformin" }, available_fields: ["name"], matches: [] };
const reference = {
  fact_id: "fact-1", status: "found", subject: "metformin", rxcui: "6809", retrieved_at: "2026-10-21T12:00:00Z",
  references: [{ source: "medlineplus", locale: "en-US", title: "Official Metformin reference", url: "https://medlineplus.gov/druginfo/meds/a696005.html", summary: "Bounded public text", checked_at: "2026-09-01T12:00:00Z", source_updated: "2026-08-31", source_version: "version-1", stale: true }],
};

beforeEach(() => {
  get.mockReset(); post.mockReset();
  get.mockImplementation((url: string) => Promise.resolve(url.endsWith("/reconciliation-preview") ? preview : url.endsWith("/medication-reference") ? reference : review));
});
afterEach(cleanup);

async function openPreview() {
  await screen.findByText("Metformin");
  fireEvent.click(screen.getByRole("button", { name: /review changes/i }));
  return screen.findByRole("region", { name: "Medication reference" });
}

describe("Medication reference in reconciliation preview", () => {
  it("returns focus to Review changes after an asynchronous preview closes", async () => {
    let resolve!: (value: typeof preview) => void;
    get.mockImplementation((url: string) => url.endsWith("/reconciliation-preview") ? new Promise((done) => { resolve = done; }) : Promise.resolve(review));
    render(<SmartImportReviewPanel patientId="patient-1" />);
    const opener = await screen.findByRole("button", { name: /review changes/i });
    opener.focus();
    fireEvent.click(opener);
    opener.blur();
    await act(async () => { resolve(preview); });
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(opener).toHaveFocus();
    expect(post).not.toHaveBeenCalled();
  });
  it("looks up only on explicit click, shows dates without timezone shifting and never applies fields", async () => {
    render(<SmartImportReviewPanel patientId="patient-1" />);
    const panel = await openPreview();
    expect(get.mock.calls.some(([url]) => url.endsWith("/medication-reference"))).toBe(false);
    expect(panel).toHaveTextContent("sends only the recorded drug name");
    expect(panel).toHaveTextContent("not an exact formulation match");
    expect(panel).toHaveTextContent("does not apply values");
    fireEvent.click(within(panel).getByRole("button", { name: "Medication reference" }));
    expect(within(panel).getByRole("status")).toHaveTextContent("Loading public");
    const link = await screen.findByRole("link", { name: "Official Metformin reference (en-US)" });
    expect(link).toHaveAttribute("href", reference.references[0]!.url);
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(panel.querySelector('time[datetime="2026-08-31"]')).toHaveTextContent("2026-08-31");
    expect(panel).toHaveTextContent("Stale cached reference");
    expect(panel).toHaveTextContent("not the last clinical review");
    expect(panel).toHaveTextContent("1,200 characters");
    expect(get).toHaveBeenCalledWith("/api/v1/smart/patients/patient-1/facts/fact-1/medication-reference", { token: "local-clinician-token" });
    expect(post).not.toHaveBeenCalled();
    expect(screen.queryByRole("checkbox", { name: /rxcui/i })).not.toBeInTheDocument();
  });

  it.each(["unavailable", "not_found"])("explains %s without inferring medication safety", async (status) => {
    get.mockImplementation((url: string) => Promise.resolve(url.endsWith("/reconciliation-preview") ? preview : url.endsWith("/medication-reference") ? { ...reference, status, references: [] } : review));
    render(<SmartImportReviewPanel patientId="patient-1" />);
    const panel = await openPreview();
    fireEvent.click(within(panel).getByRole("button", { name: "Medication reference" }));
    await screen.findByText(status === "unavailable" ? /Public reference lookup unavailable/ : /No public reference found/);
    expect(within(panel).getByRole("button", { name: "Retry medication reference" })).toBeEnabled();
    expect(post).not.toHaveBeenCalled();
  });

  it("shows a failed request and supports an explicit retry", async () => {
    let fail = true;
    get.mockImplementation((url: string) => url.endsWith("/medication-reference") ? fail ? Promise.reject(new Error("private provider text")) : Promise.resolve(reference) : Promise.resolve(url.endsWith("/reconciliation-preview") ? preview : review));
    render(<SmartImportReviewPanel patientId="patient-1" />);
    const panel = await openPreview();
    fireEvent.click(within(panel).getByRole("button", { name: "Medication reference" }));
    await screen.findByRole("alert");
    expect(panel).not.toHaveTextContent("private provider text");
    fail = false;
    fireEvent.click(within(panel).getByRole("button", { name: "Retry medication reference" }));
    await screen.findByRole("link", { name: "Official Metformin reference (en-US)" });
  });

  it("rejects a reference returned for a different fact", async () => {
    get.mockImplementation((url: string) => Promise.resolve(url.endsWith("/medication-reference") ? { ...reference, fact_id: "foreign" } : url.endsWith("/reconciliation-preview") ? preview : review));
    render(<SmartImportReviewPanel patientId="patient-1" />);
    const panel = await openPreview();
    fireEvent.click(within(panel).getByRole("button", { name: "Medication reference" }));
    await screen.findByRole("alert");
    expect(screen.queryByRole("link", { name: /Official Metformin/ })).not.toBeInTheDocument();
  });

  it("ignores a late reference after closing and reopening the preview", async () => {
    let resolve!: (value: typeof reference) => void;
    get.mockImplementation((url: string) => url.endsWith("/medication-reference") ? new Promise((done) => { resolve = done; }) : Promise.resolve(url.endsWith("/reconciliation-preview") ? preview : review));
    render(<SmartImportReviewPanel patientId="patient-1" />);
    const panel = await openPreview();
    fireEvent.click(within(panel).getByRole("button", { name: "Medication reference" }));
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    const reopened = await openPreview();
    await act(async () => { resolve(reference); });
    expect(within(reopened).getByRole("button", { name: "Medication reference" })).toBeEnabled();
    expect(screen.queryByRole("link", { name: /Official Metformin/ })).not.toBeInTheDocument();
  });
});
