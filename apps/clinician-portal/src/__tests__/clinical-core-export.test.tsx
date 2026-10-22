import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ClinicalCoreExport } from "@/components/features/clinical-core-export";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/services/api", () => ({ api: { get } }));

beforeEach(() => {
  get.mockReset();
  URL.createObjectURL = vi.fn(() => "blob:synthetic");
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("downloads the authorized core without presenting it as a complete chart", async () => {
  get.mockResolvedValue({
    resourceType: "Bundle",
    type: "collection",
    entry: [],
  });
  render(
    <ClinicalCoreExport
      patientId="synthetic-patient"
      token="synthetic-session"
    />,
  );
  expect(screen.getByText(/not the complete chart/)).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "Download clinical record (FHIR)" }),
  );
  await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalledOnce());
  expect(get).toHaveBeenCalledWith(
    "/api/v1/smart/patients/synthetic-patient/record-export",
    { token: "synthetic-session" },
  );
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:synthetic");
});

it("retains a retry action after failure and downloads no partial file", async () => {
  get.mockRejectedValue(new Error("unavailable"));
  render(
    <ClinicalCoreExport
      patientId="synthetic-patient"
      token="synthetic-session"
    />,
  );
  fireEvent.click(screen.getByRole("button"));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "No partial file was downloaded",
  );
  expect(URL.createObjectURL).not.toHaveBeenCalled();
  get.mockResolvedValue({
    resourceType: "Bundle",
    type: "collection",
    entry: [],
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Retry clinical record export" }),
  );
  await waitFor(() => expect(URL.createObjectURL).toHaveBeenCalledOnce());
});

it("does not download a previous patient's result after changing scope", async () => {
  let resolve!: (value: unknown) => void;
  get.mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  const { rerender } = render(
    <ClinicalCoreExport patientId="old" token="synthetic-session" />,
  );
  fireEvent.click(screen.getByRole("button"));
  rerender(<ClinicalCoreExport patientId="new" token="synthetic-session" />);
  await act(async () => {
    resolve({ resourceType: "Bundle" });
  });
  expect(URL.createObjectURL).not.toHaveBeenCalled();
});

it("disables export without authentication", () => {
  render(<ClinicalCoreExport patientId="synthetic-patient" token={null} />);
  expect(screen.getByRole("button")).toBeDisabled();
  expect(get).not.toHaveBeenCalled();
});
